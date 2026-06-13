import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from cafe_pos.models import (
    CafeTable,
    Customer,
    Floor,
    Order,
    OrderLineItem,
    OrderReview,
    PaymentMethod,
    PaymentRecord,
    Product,
    ProductCategory,
    PaymentSettings,
    Coupon,
    LoyaltySettings,
    Promotion,
)
from dashboard.mixins import cafe_admin_required, cafe_kds_required
from tenants.utils import log_action

from . import services
from .kds import broadcast_order_status, broadcast_order_to_kds, kds_group_name
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

EDITABLE_STATUSES = {Order.OrderStatus.DRAFT, Order.OrderStatus.SENT_TO_KITCHEN, Order.OrderStatus.READY}


def _send_chat_invite(order, request):
    """Create a ChatSession for the order and email the customer a chat link (best-effort)."""
    if not order.customer_id or not order.customer.email:
        return
    try:
        from cafe_pos.models import ChatAssistantSettings, ChatSession
        assistant = ChatAssistantSettings.objects.filter(cafe=order.cafe).first()
        if not assistant or not assistant.is_enabled:
            return
        session = ChatSession.objects.create(
            cafe=order.cafe,
            order=order,
            customer_name=order.customer.name,
            customer_email=order.customer.email,
        )
        from cafe_pos.receipts import email_chat_invite
        email_chat_invite(order, order.customer.email, session.session_token, request=request)
    except Exception:
        pass


def _data(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or "{}")
        except (ValueError, TypeError):
            return {}
    return request.POST


def _decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _get_order(request, pk):
    return get_object_or_404(Order, pk=pk, cafe=request.cafe)


def _editable_or_400(order):
    if order.status not in EDITABLE_STATUSES:
        return JsonResponse({"error": "This order can no longer be edited."}, status=400)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Terminal shell + session
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required(require_admin=False)
@ensure_csrf_cookie
def terminal(request):
    # Kitchen-display-only users go straight to KDS, not POS
    profile = getattr(request.user, "profile", None)
    if profile and profile.role == "kitchen":
        return redirect("pos:kds")

    cafe = request.cafe
    services.ensure_payment_methods(cafe)
    session = services.current_session(cafe)

    if session is None:
        last = cafe.pos_sessions.order_by("-opened_at").first()
        return render(request, "pos/session.html", {"mode": "open", "last_session": last})

    context = {
        "session": session,
        "categories": ProductCategory.objects.filter(cafe=cafe).order_by("name"),
        "products": Product.objects.filter(cafe=cafe, is_active=True).select_related("category"),
        "payment_methods": PaymentMethod.objects.filter(cafe=cafe, is_enabled=True).order_by("type"),
        "is_admin": request.user.is_superuser or (
            getattr(request.user, "profile", None) and request.user.profile.role == "admin"
        ),
        "payment_settings": PaymentSettings.objects.filter(cafe=cafe).first(),
        "coupons": Coupon.objects.filter(cafe=cafe, is_active=True),
        "promotions": Promotion.objects.filter(cafe=cafe, is_active=True).select_related("product"),
    }
    return render(request, "pos/terminal.html", context)


@cafe_kds_required
@ensure_csrf_cookie
def kds_display(request):
    """Standalone Kitchen Display panel — no admin sidebar."""
    cafe = request.cafe
    profile = getattr(request.user, "profile", None)
    is_admin = request.user.is_superuser or (profile and profile.role == "admin")
    return render(request, "pos/kds.html", {
        "is_admin": is_admin,
        "categories": list(cafe.product_categories.values("id", "name", "color")),
        "kds_products": list(
            Product.objects.filter(cafe=cafe, is_active=True, show_in_kds=True)
            .values("id", "name")
            .order_by("name")
        ),
    })


@cafe_admin_required(require_admin=False)
@ensure_csrf_cookie
def pds_display(request):
    """Pickup Display Screen for announcing ready orders."""
    cafe = request.cafe
    profile = getattr(request.user, "profile", None)
    is_admin = request.user.is_superuser or (profile and profile.role == "admin")
    return render(request, "pos/pds.html", {"is_admin": is_admin})


@cafe_admin_required(require_admin=False)
@require_POST
def session_open(request):
    services.open_session(request.cafe, request.user)
    log_action("other", cafe=request.cafe, request=request, message="Opened a POS session.")
    return redirect("pos:terminal")


@cafe_admin_required(require_admin=False)
@require_POST
def session_close(request):
    cafe = request.cafe
    session = services.current_session(cafe)
    summary = None
    if session is not None:
        paid = session.orders.filter(status=Order.OrderStatus.PAID)
        total = sum((o.total for o in paid), Decimal("0"))
        session.closing_sale_amount = total
        session.closed_at = timezone.now()
        session.status = "closed"
        session.save(update_fields=["closing_sale_amount", "closed_at", "status"])
        summary = {"orders": paid.count(), "revenue": total}
        log_action("other", cafe=cafe, request=request, target=session,
                   message=f"Closed POS session — {paid.count()} orders, ₹{total}.")
    last = cafe.pos_sessions.order_by("-opened_at").first()
    return render(request, "pos/session.html", {"mode": "closed", "summary": summary, "last_session": last})


# ─────────────────────────────────────────────────────────────────────────────
# Tables / floor popup
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required(require_admin=False)
def tables(request):
    cafe = request.cafe
    floors = Floor.objects.filter(cafe=cafe).prefetch_related("tables")
    open_orders = {
        o.table_id: o.id
        for o in Order.objects.filter(cafe=cafe, status__in=EDITABLE_STATUSES, table__isnull=False)
    }
    
    # Get last order email and review status per table
    table_emails = {}
    table_reviewed = {}
    for table_id in cafe.tables.values_list('id', flat=True):
        last_order = Order.objects.filter(cafe=cafe, table_id=table_id).order_by('-created_at').first()
        if last_order:
            if hasattr(last_order, 'review') and last_order.review:
                table_reviewed[table_id] = True
            elif hasattr(last_order, 'reviews') and last_order.reviews.exists():
                table_reviewed[table_id] = True
            if last_order.customer and last_order.customer.email:
                table_emails[table_id] = last_order.customer.email

    data = []
    for floor in floors:
        data.append({
            "id": floor.id,
            "name": floor.name,
            "canvas_mode": floor.canvas_mode,
            "tables": [
                {
                    "id": t.id,
                    "number": t.table_number,
                    "seats": t.seats,
                    "is_active": t.is_active,
                    "order_id": open_orders.get(t.id),
                    "occupied": t.is_occupied or (t.id in open_orders),
                    "locked": t.is_occupied,
                    "customer_email": table_emails.get(t.id, ""),
                    "has_reviewed": table_reviewed.get(t.id, False),
                    "pos_x": t.pos_x,
                    "pos_y": t.pos_y,
                    "width": t.width,
                    "height": t.height,
                    "shape": t.shape,
                }
                for t in floor.tables.all() if t.is_active
            ],
        })
    return JsonResponse({"floors": data})


@cafe_admin_required(require_admin=False)
@require_POST
def table_release(request, pk):
    """Manually mark a table as empty (unlocks it after guests leave)."""
    table = get_object_or_404(CafeTable, pk=pk, cafe=request.cafe)
    wants_json = "application/json" in (request.content_type or "")
    active = Order.objects.filter(cafe=request.cafe, table=table, status__in=EDITABLE_STATUSES).exists()
    
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'admin')
    
    if active and not is_admin:
        if wants_json:
            return JsonResponse({"error": "There is still an open order on this table."}, status=400)
        from django.contrib import messages
        messages.error(request, f"Table {table.table_number} still has an open order. Complete or cancel it first.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
        
    table.is_occupied = False
    table.save(update_fields=["is_occupied"])
    log_action("update", cafe=request.cafe, request=request, target=table,
               message=f"Marked table {table.table_number} as empty.")
               
    email_customer = request.POST.get("email_customer")
    if email_customer:
        # Find the most recent order for this table
        last_order = Order.objects.filter(cafe=request.cafe, table=table).order_by("-created_at").first()
        if last_order:
            from cafe_pos.receipts import email_feedback
            email_feedback(last_order, email_customer, request=request)

    if wants_json:
        return JsonResponse({"ok": True, "table_id": pk})
    from django.contrib import messages
    messages.success(request, f"Table {table.table_number} marked as empty.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


# ─────────────────────────────────────────────────────────────────────────────
# Order lifecycle (JSON)
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required(require_admin=False)
@require_POST
def order_start(request):
    cafe = request.cafe
    session = services.current_session(cafe)
    if session is None:
        return JsonResponse({"error": "No open POS session."}, status=400)
    data = _data(request)
    table_id = data.get("table")
    current_order_id = data.get("current_order")
    table = get_object_or_404(CafeTable, pk=table_id, cafe=cafe)

    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(cafe=cafe, table=table, status__in=EDITABLE_STATUSES)
            .first()
        )
        current_order = None
        if current_order_id:
            current_order = (
                Order.objects.select_for_update()
                .filter(
                    pk=current_order_id,
                    cafe=cafe,
                    session=session,
                    status=Order.OrderStatus.DRAFT,
                )
                .first()
            )

        if (
            current_order is not None
            and current_order.id != getattr(order, "id", None)
            and not current_order.line_items.exists()
        ):
            if order is None:
                current_order.table = table
                current_order.save(update_fields=["table"])
                order = current_order
            elif current_order.table_id is not None:
                current_order.table = None
                current_order.save(update_fields=["table"])

        if order is None:
            order = Order.objects.create(
                cafe=cafe, session=session, table=table, employee=request.user,
                status=Order.OrderStatus.DRAFT, order_number=services.next_order_number(cafe),
                subtotal=0, tax_amount=0, discount_amount=0, total=0,
            )
        # Lock the table so it shows as occupied even after payment
        if not table.is_occupied:
            table.is_occupied = True
            table.save(update_fields=["is_occupied"])
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
def order_detail(request, pk):
    return JsonResponse(services.order_json(_get_order(request, pk)))


@cafe_admin_required(require_admin=False)
def orders_page(request):
    """Full orders management page."""
    cafe = request.cafe
    session = services.current_session(cafe)
    return render(request, "pos/orders.html", {
        "session": session,
        "is_admin": request.user.is_superuser or (
            getattr(request.user, "profile", None) and request.user.profile.role == "admin"
        ),
    })


@cafe_admin_required(require_admin=False)
def orders_data(request):
    """JSON — orders in the current session for the orders page."""
    cafe = request.cafe
    session = services.current_session(cafe)
    qs = Order.objects.filter(cafe=cafe)
    if session is not None:
        qs = qs.filter(session=session)
    qs = qs.select_related("table", "customer").order_by("-created_at")[:100]
    data = [{
        "id": o.id,
        "number": o.order_number,
        "table": o.table.table_number if o.table_id else None,
        "total": float(o.total),
        "status": o.status,
        "date": o.created_at.strftime("%d/%m %H:%M"),
        "customer": o.customer.name if o.customer_id else None,
    } for o in qs]
    return JsonResponse({"orders": data})


@cafe_admin_required(require_admin=False)
@require_POST
def order_add_line(request, pk):
    order = _get_order(request, pk)
    if (resp := _editable_or_400(order)):
        return resp
    product = get_object_or_404(Product, pk=_data(request).get("product"), cafe=request.cafe, is_active=True)
    line = order.line_items.filter(product=product).first()
    if line is None:
        line = OrderLineItem(order=order, product=product, quantity=0,
                             unit_price=product.price, line_discount=0, line_total=0)
    line.quantity += 1
    line.line_total = line.unit_price * line.quantity - line.line_discount
    line.save()
    services.recalc_order(order)
    if order.status in {Order.OrderStatus.SENT_TO_KITCHEN, Order.OrderStatus.READY, Order.OrderStatus.PAID}:
        broadcast_order_to_kds(order, event_type="order_updated")
        broadcast_order_status(order)
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
@require_POST
def order_update_line(request, pk, lid):
    order = _get_order(request, pk)
    if (resp := _editable_or_400(order)):
        return resp
    line = get_object_or_404(OrderLineItem, pk=lid, order=order)
    try:
        qty = int(_data(request).get("quantity"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid quantity."}, status=400)
    if qty <= 0:
        line.delete()
    else:
        line.quantity = qty
        line.line_total = line.unit_price * line.quantity - line.line_discount
        line.save()
    services.recalc_order(order)
    if order.status in {Order.OrderStatus.SENT_TO_KITCHEN, Order.OrderStatus.READY, Order.OrderStatus.PAID}:
        broadcast_order_to_kds(order, event_type="order_updated")
        broadcast_order_status(order)
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
@require_POST
def order_discount(request, pk):
    order = _get_order(request, pk)
    if (resp := _editable_or_400(order)):
        return resp
    data = _data(request)
    coupon_code = data.get("coupon_code", "").strip()
    promotion_id = data.get("promotion_id")

    order.coupon = None
    order.promotion = None
    order.discount_amount = Decimal("0")
    services.recalc_order(order)

    if coupon_code:
        coupon = Coupon.objects.filter(cafe=request.cafe, code__iexact=coupon_code, is_active=True).first()
        if not coupon:
            return JsonResponse({"error": f"Invalid or expired coupon: {coupon_code}"}, status=400)
        order.coupon = coupon
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            amount = order.subtotal * (coupon.discount_value / Decimal("100"))
        else:
            amount = coupon.discount_value

    elif promotion_id:
        promo = Promotion.objects.filter(cafe=request.cafe, pk=promotion_id, is_active=True).first()
        if not promo:
            return JsonResponse({"error": "Promotion not found or inactive."}, status=400)
        if promo.apply_to == Promotion.ApplyTo.ORDER:
            if order.subtotal < (promo.min_order_amount or Decimal("0")):
                return JsonResponse(
                    {"error": f"Order total must be at least ₹{promo.min_order_amount} for this promotion."},
                    status=400,
                )
        elif promo.apply_to == Promotion.ApplyTo.PRODUCT:
            qty = sum(
                li.quantity for li in order.line_items.all() if li.product_id == promo.product_id
            )
            if qty < (promo.min_quantity or 1):
                return JsonResponse(
                    {"error": f"Need at least {promo.min_quantity}× {promo.product.name} for this promotion."},
                    status=400,
                )
        order.promotion = promo
        if promo.discount_type == Promotion.DiscountType.PERCENTAGE:
            amount = order.subtotal * (promo.discount_value / Decimal("100"))
        else:
            amount = promo.discount_value

    else:
        amount = _decimal(data.get("amount"))

    amount = max(amount, Decimal("0"))
    order.discount_amount = amount
    order.save(update_fields=["discount_amount", "coupon", "promotion"])
    services.recalc_order(order)
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
@require_POST
def order_customer(request, pk):
    order = _get_order(request, pk)
    if (resp := _editable_or_400(order)):
        return resp
    data = _data(request)
    cafe = request.cafe
    if "customer_id" in data and not data.get("customer_id"):
        order.customer = None
        order.save(update_fields=["customer"])
        broadcast_order_status(order)
        return JsonResponse(services.order_json(order))
        
    if data.get("customer_id"):
        customer = get_object_or_404(Customer, pk=data["customer_id"], cafe=cafe)
        if customer.is_banned:
            return JsonResponse({"error": "This customer is banned and cannot be assigned to orders."}, status=400)
    else:
        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "Customer name is required."}, status=400)
        email = (data.get("email") or "").strip().lower() or None
        if not email:
            return JsonResponse({"error": "Customer email is required for receipts."}, status=400)
        customer = None
        if email:
            customer = Customer.objects.filter(cafe=cafe, email=email).first()
            if customer and customer.is_banned:
                return JsonResponse({"error": "This customer is banned and cannot be assigned to orders."}, status=400)
        if customer is None:
            customer = Customer.objects.create(
                cafe=cafe, name=name, email=email, phone=(data.get("phone") or "").strip() or None
            )
    order.customer = customer
    order.save(update_fields=["customer"])
    broadcast_order_status(order)
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
@require_POST
def order_send_kitchen(request, pk):
    order = _get_order(request, pk)
    if (resp := _editable_or_400(order)):
        return resp
    if not order.line_items.exists():
        return JsonResponse({"error": "Cart is empty."}, status=400)
    order.status = Order.OrderStatus.SENT_TO_KITCHEN
    order.save(update_fields=["status"])
    order.line_items.update(kds_status=OrderLineItem.KDSStatus.TO_COOK)
    log_action("update", cafe=request.cafe, request=request, target=order,
               message=f"Sent {order.order_number} to kitchen.")
    broadcast_order_to_kds(order, event_type="new_order")
    broadcast_order_status(order)
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
@require_POST
def order_pay(request, pk):
    order = _get_order(request, pk)
    if order.status == Order.OrderStatus.PAID:
        return JsonResponse({"error": "Order already paid."}, status=400)
    if not order.line_items.exists():
        return JsonResponse({"error": "Cart is empty."}, status=400)
    if not order.customer_id or not order.customer.email:
        return JsonResponse({"error": "Customer name and email are mandatory for receipts."}, status=400)
    if order.customer.is_banned:
        return JsonResponse({"error": "This customer is banned and cannot be paid on an order."}, status=400)

    data = _data(request)
    method = data.get("method_type")
    if method not in {m.value for m in PaymentRecord.MethodType}:
        return JsonResponse({"error": "Invalid payment method."}, status=400)

    total = order.total
    if method == PaymentRecord.MethodType.CASH:
        tendered = _decimal(data.get("amount_tendered"), default="0")
        if tendered < total:
            return JsonResponse({"error": "Amount tendered is less than the total."}, status=400)
    else:
        tendered = total
    change = tendered - total

    with transaction.atomic():
        PaymentRecord.objects.create(
            order=order,
            method_type=method,
            amount_tendered=tendered,
            change_due=change if change > 0 else Decimal("0"),
            transaction_ref=(data.get("transaction_ref") or "").strip() or None,
            paid_at=timezone.now(),
        )
        order.status = Order.OrderStatus.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at"])

    log_action("other", cafe=request.cafe, request=request, target=order,
               message=f"Payment for {order.order_number}: {method} ₹{total}.")
    broadcast_order_to_kds(order, event_type="order_updated")
    broadcast_order_status(order)

    # Auto-email the receipt to the customer if we have their address (best-effort).
    receipt_emailed = False
    if order.customer_id and order.customer.email:
        from cafe_pos.receipts import email_receipt
        receipt_emailed = email_receipt(order, order.customer.email, request=request)

    # Send chat invite email if the assistant is enabled for this cafe.
    _send_chat_invite(order, request)

    return JsonResponse({
        "ok": True,
        "order_number": order.order_number,
        "method": method,
        "total": float(total),
        "amount_tendered": float(tendered),
        "change_due": float(change if change > 0 else 0),
        "customer_email": (order.customer.email if order.customer_id else "") or "",
        "receipt_emailed": receipt_emailed,
    })



@cafe_admin_required(require_admin=False)
@require_POST
def order_razorpay_create(request, pk):
    import razorpay
    from cafe_pos.models import PaymentSettings
    
    order = _get_order(request, pk)
    if order.status == Order.OrderStatus.PAID:
        return JsonResponse({"error": "Order already paid."}, status=400)
    if not order.line_items.exists():
        return JsonResponse({"error": "Cart is empty."}, status=400)
    if not order.customer_id or not order.customer.email:
        return JsonResponse({"error": "Customer name and email are mandatory for receipts."}, status=400)
    if order.customer.is_banned:
        return JsonResponse({"error": "This customer is banned and cannot be paid on an order."}, status=400)
        
    settings_obj = PaymentSettings.objects.filter(cafe=request.cafe).first()
    if not settings_obj or not settings_obj.razorpay_enabled or not settings_obj.razorpay_key_id or not settings_obj.razorpay_key_secret:
        return JsonResponse({"error": "Razorpay is not configured for this cafe."}, status=400)
        
    client = razorpay.Client(auth=(settings_obj.razorpay_key_id, settings_obj.razorpay_key_secret))
    
    amount_in_paise = int(order.total * 100)
    
    try:
        rzp_order = client.order.create({
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": order.order_number,
        })
        return JsonResponse({"razorpay_order_id": rzp_order["id"], "amount": amount_in_paise, "currency": "INR"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@cafe_admin_required(require_admin=False)
@require_POST
def order_razorpay_verify(request, pk):
    import razorpay
    from cafe_pos.models import PaymentSettings
    
    order = _get_order(request, pk)
    if order.status == Order.OrderStatus.PAID:
        return JsonResponse({"error": "Order already paid."}, status=400)
    if order.customer_id and order.customer.is_banned:
        return JsonResponse({"error": "This customer is banned and cannot be paid on an order."}, status=400)

    data = _data(request)
    rzp_payment_id = data.get("razorpay_payment_id")
    rzp_order_id = data.get("razorpay_order_id")
    rzp_signature = data.get("razorpay_signature")
    
    settings_obj = PaymentSettings.objects.filter(cafe=request.cafe).first()
    if not settings_obj or not settings_obj.razorpay_enabled:
        return JsonResponse({"error": "Razorpay is not configured for this cafe."}, status=400)

    client = razorpay.Client(auth=(settings_obj.razorpay_key_id, settings_obj.razorpay_key_secret))
    
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': rzp_order_id,
            'razorpay_payment_id': rzp_payment_id,
            'razorpay_signature': rzp_signature
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({"error": "Invalid payment signature."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    with transaction.atomic():
        PaymentRecord.objects.create(
            order=order,
            method_type=PaymentRecord.MethodType.RAZORPAY,
            amount_tendered=order.total,
            change_due=Decimal("0"),
            transaction_ref=rzp_payment_id,
            paid_at=timezone.now(),
        )
        order.status = Order.OrderStatus.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at"])

    log_action("other", cafe=request.cafe, request=request, target=order,
               message=f"Payment for {order.order_number}: Razorpay ₹{order.total}.")
    broadcast_order_to_kds(order, event_type="order_updated")
    broadcast_order_status(order)

    receipt_emailed = False
    if order.customer_id and order.customer.email:
        from cafe_pos.receipts import email_receipt
        receipt_emailed = email_receipt(order, order.customer.email, request=request)

    _send_chat_invite(order, request)

    return JsonResponse({
        "ok": True,
        "order_number": order.order_number,
        "method": "razorpay",
        "total": float(order.total),
        "amount_tendered": float(order.total),
        "change_due": 0,
        "customer_email": (order.customer.email if order.customer_id else "") or "",
        "receipt_emailed": receipt_emailed,
    })


@cafe_admin_required(require_admin=False)
@require_POST
def order_email_receipt(request, pk):
    """Manually email the receipt for an order (POS 'Email receipt' action)."""
    from cafe_pos.receipts import email_receipt

    order = _get_order(request, pk)
    to = (_data(request).get("email") or "").strip()
    if not to and order.customer_id:
        to = order.customer.email or ""
    if not to:
        return JsonResponse({"error": "No email address to send to."}, status=400)
    if email_receipt(order, to, request=request):
        return JsonResponse({"ok": True, "sent_to": to})
    return JsonResponse({"error": "Could not send the receipt (check SMTP settings)."}, status=500)


@cafe_admin_required(require_admin=False)
@require_POST
def order_email_feedback(request, pk):
    order = get_object_or_404(Order, pk=pk, cafe=request.cafe)
    if order.status != Order.OrderStatus.PAID:
        return JsonResponse({"error": "Cannot send feedback request for unpaid order."}, status=400)
    import json
    try:
        data = json.loads(request.body)
        email = data.get("email")
    except Exception:
        email = request.POST.get("email")
        
    if not email:
        return JsonResponse({"error": "Email address required"}, status=400)
        
    from cafe_pos.receipts import email_feedback
    if email_feedback(order, email.strip(), request=request):
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "Failed to send feedback email"}, status=500)


@cafe_admin_required(require_admin=False)
def order_upi_qr(request, pk):
    """PNG QR for the order's UPI payment (built from the cafe's UPI id + total)."""
    import io

    import qrcode

    from cafe_pos.models import PaymentSettings

    order = _get_order(request, pk)
    ps = PaymentSettings.objects.filter(cafe=request.cafe).first()
    upi_id = (ps.upi_id if ps and ps.upi_id else "")
    if not upi_id:
        upi = PaymentMethod.objects.filter(cafe=request.cafe, type="upi").first()
        upi_id = (upi.upi_id if upi else "") or "cafe@upi"
    payee = (ps.upi_payee_name if ps and ps.upi_payee_name else request.cafe.name)
    payload = services.upi_qr_payload(upi_id, order.total, name=payee)
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


@cafe_admin_required(require_admin=False)
@require_POST
def order_cancel(request, pk):
    """Cancel (soft-delete) a draft order."""
    order = _get_order(request, pk)
    if order.status != Order.OrderStatus.DRAFT:
        return JsonResponse({"error": "Only draft orders can be cancelled."}, status=400)
    order.status = Order.OrderStatus.CANCELLED
    order.save(update_fields=["status"])
    log_action("delete", cafe=request.cafe, request=request, target=order,
               message=f"Cancelled order {order.order_number}.")
    broadcast_order_status(order, event_type="order_removed")
    return JsonResponse({"ok": True, "order_number": order.order_number})


@cafe_admin_required(require_admin=False)
def customer_list(request):
    """JSON list of customers in this cafe. Supports search query 'q'."""
    cafe = request.cafe
    q = request.GET.get("q", "").strip().lower()
    loyalty_settings, _ = LoyaltySettings.objects.get_or_create(cafe=cafe)
    qs = Customer.objects.filter(cafe=cafe).annotate(
        paid_orders=Count("orders", filter=Q(orders__status=Order.OrderStatus.PAID))
    )
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    qs = qs.order_by("name")[:100]
    data = []
    for c in qs:
        loyalty = c.loyalty_snapshot(settings_obj=loyalty_settings, paid_orders=c.paid_orders)
        data.append({
            "id": c.id,
            "name": c.name,
            "email": c.email or "",
            "phone": c.phone or "",
            "is_banned": c.is_banned,
            "ban_reason": c.ban_reason,
            "loyalty": loyalty,
        })
    return JsonResponse({"customers": data})


@cafe_admin_required(require_admin=False)
@require_POST
def customer_create_update(request, pk=None):
    """Create a new customer or update an existing one."""
    data = _data(request)
    cafe = request.cafe
    
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Customer name is required."}, status=400)
    
    email = (data.get("email") or "").strip().lower() or None
    phone = (data.get("phone") or "").strip() or None
    
    if pk:
        customer = get_object_or_404(Customer, pk=pk, cafe=cafe)
        if email:
            dup = Customer.objects.filter(cafe=cafe, email=email).exclude(pk=pk).exists()
            if dup:
                return JsonResponse({"error": "A customer with this email already exists."}, status=400)
        customer.name = name
        customer.email = email
        customer.phone = phone
        customer.save()
    else:
        if email:
            dup = Customer.objects.filter(cafe=cafe, email=email).first()
            if dup:
                return JsonResponse({"error": "A customer with this email already exists."}, status=400)
        customer = Customer.objects.create(
            cafe=cafe, name=name, email=email, phone=phone
        )
        
    loyalty_settings, _ = LoyaltySettings.objects.get_or_create(cafe=cafe)
    loyalty = customer.loyalty_snapshot(settings_obj=loyalty_settings)
    return JsonResponse({
        "id": customer.id,
        "name": customer.name,
        "email": customer.email or "",
        "phone": customer.phone or "",
        "is_banned": customer.is_banned,
        "ban_reason": customer.ban_reason,
        "loyalty": loyalty,
    })


@cafe_admin_required(require_admin=False)
@require_POST
def customer_delete(request, pk):
    """Delete a customer record."""
    customer = get_object_or_404(Customer, pk=pk, cafe=request.cafe)
    customer.delete()
    return JsonResponse({"ok": True})


def order_review(request, token):
    order = get_object_or_404(
        Order.objects.select_related("cafe", "customer", "employee").prefetch_related("line_items__prepared_by"),
        review_token=token,
    )
    existing = getattr(order, "review", None)
    from cafe_pos.models import FeedbackQuestion
    questions = FeedbackQuestion.objects.filter(cafe=order.cafe).order_by("sort_order")
    return render(request, "pos/review.html", {"order": order, "existing_review": existing, "questions": questions})


@require_POST
def order_review_submit(request, token):
    order = get_object_or_404(
        Order.objects.select_related("cafe", "customer", "employee").prefetch_related("line_items__prepared_by"),
        review_token=token,
    )
    try:
        rating_str = request.POST.get("rating")
        rating = int(rating_str) if rating_str else None
    except (TypeError, ValueError):
        rating = None
    if rating is not None and (rating < 1 or rating > 5):
        from cafe_pos.models import FeedbackQuestion
        questions = FeedbackQuestion.objects.filter(cafe=order.cafe).order_by("sort_order")
        return render(request, "pos/review.html", {
            "order": order,
            "error": "Please select a rating from 1 to 5.",
            "questions": questions,
        }, status=400)

    review, created = OrderReview.objects.get_or_create(
        order=order,
        defaults={
            "cafe": order.cafe,
            "customer": order.customer,
            "cashier": order.employee,
            "customer_name": order.customer.name if order.customer_id else "",
            "customer_email": order.customer.email if order.customer_id else "",
        },
    )
    if not created:
        return render(request, "pos/review.html", {"order": order, "existing_review": review})

    review.rating = rating
    review.comment = (request.POST.get("comment") or "").strip()
    review.save(update_fields=["rating", "comment"])
    
    # Save dynamic responses
    from cafe_pos.models import FeedbackQuestion, FeedbackResponse
    questions = FeedbackQuestion.objects.filter(cafe=order.cafe)
    for q in questions:
        key = f"q_{q.id}"
        val = request.POST.get(key, "").strip()
        if val:
            if q.type == "rating":
                try:
                    r_val = int(val)
                    FeedbackResponse.objects.create(review=review, question=q, rating_value=r_val)
                except ValueError:
                    pass
            else:
                FeedbackResponse.objects.create(review=review, question=q, text_value=val)

    staff_ids = {
        line.prepared_by_id
        for line in order.line_items.all()
        if line.prepared_by_id
    }
    if staff_ids:
        review.kitchen_staff.set(staff_ids)
    return render(request, "pos/review_thanks.html", {"order": order, "review": review})


@cafe_kds_required
@require_POST
def kds_update_line_status(request, pk, lid):
    order = _get_order(request, pk)
    line = get_object_or_404(OrderLineItem, pk=lid, order=order)
    data = _data(request)
    new_status = data.get("kds_status")
    
    if new_status in {s.value for s in OrderLineItem.KDSStatus}:
        line.kds_status = new_status
        update_fields = ["kds_status"]
        if new_status == OrderLineItem.KDSStatus.COMPLETED and request.user.is_authenticated:
            line.prepared_by = request.user
            update_fields.append("prepared_by")
        line.save(update_fields=update_fields)
        
        all_completed = not order.line_items.exclude(kds_status=OrderLineItem.KDSStatus.COMPLETED).exists()
        if all_completed:
            if order.status == Order.OrderStatus.SENT_TO_KITCHEN:
                order.status = Order.OrderStatus.READY
                order.save(update_fields=["status"])
                broadcast_order_status(order)
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    kds_group_name(order.cafe_id),
                    {
                        "type": "kds.order",
                        "event": "order_removed",
                        "order": {"id": order.id},
                    },
                )
            return JsonResponse({"ok": True, "kds_status": new_status, "order_status": order.status})

        broadcast_order_to_kds(order, event_type="order_updated")
        broadcast_order_status(order)
        return JsonResponse({"ok": True, "kds_status": new_status})
    
    return JsonResponse({"error": "Invalid status."}, status=400)
