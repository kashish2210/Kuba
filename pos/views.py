import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
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
    PaymentMethod,
    PaymentRecord,
    Product,
    ProductCategory,
    PaymentSettings,
    Coupon,
)
from dashboard.mixins import cafe_admin_required
from tenants.utils import log_action

from . import services

EDITABLE_STATUSES = {Order.OrderStatus.DRAFT, Order.OrderStatus.SENT_TO_KITCHEN}


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
    }
    return render(request, "pos/terminal.html", context)


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
    data = []
    for floor in floors:
        data.append({
            "id": floor.id,
            "name": floor.name,
            "tables": [
                {
                    "id": t.id,
                    "number": t.table_number,
                    "seats": t.seats,
                    "is_active": t.is_active,
                    "order_id": open_orders.get(t.id),
                    "occupied": t.id in open_orders,
                }
                for t in floor.tables.all() if t.is_active
            ],
        })
    return JsonResponse({"floors": data})


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
    return JsonResponse(services.order_json(order))


@cafe_admin_required(require_admin=False)
@require_POST
def order_discount(request, pk):
    order = _get_order(request, pk)
    if (resp := _editable_or_400(order)):
        return resp
    data = _data(request)
    coupon_code = data.get("coupon_code")
    
    if coupon_code:
        coupon = Coupon.objects.filter(cafe=request.cafe, code__iexact=coupon_code, is_active=True).first()
        if not coupon:
            return JsonResponse({"error": f"Invalid or expired coupon: {coupon_code}"}, status=400)
        order.coupon = coupon
        order.discount_amount = Decimal("0") # temp clear to calc subtotal
        services.recalc_order(order)
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            amount = order.subtotal * (coupon.discount_value / Decimal("100"))
        else:
            amount = coupon.discount_value
    else:
        order.coupon = None
        amount = _decimal(data.get("amount"))

    if amount < 0:
        amount = Decimal("0")
        
    order.discount_amount = amount
    order.save(update_fields=["discount_amount", "coupon"])
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
        return JsonResponse(services.order_json(order))
        
    if data.get("customer_id"):
        customer = get_object_or_404(Customer, pk=data["customer_id"], cafe=cafe)
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
        if customer is None:
            customer = Customer.objects.create(
                cafe=cafe, name=name, email=email, phone=(data.get("phone") or "").strip() or None
            )
    order.customer = customer
    order.save(update_fields=["customer"])
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

    # Auto-email the receipt to the customer if we have their address (best-effort).
    receipt_emailed = False
    if order.customer_id and order.customer.email:
        from cafe_pos.receipts import email_receipt
        receipt_emailed = email_receipt(order, order.customer.email)

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

    receipt_emailed = False
    if order.customer_id and order.customer.email:
        from cafe_pos.receipts import email_receipt
        receipt_emailed = email_receipt(order, order.customer.email)

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
    if email_receipt(order, to):
        return JsonResponse({"ok": True, "sent_to": to})
    return JsonResponse({"error": "Could not send the receipt (check SMTP settings)."}, status=500)


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
    return JsonResponse({"ok": True, "order_number": order.order_number})


@cafe_admin_required(require_admin=False)
def customer_list(request):
    """JSON list of customers in this cafe. Supports search query 'q'."""
    cafe = request.cafe
    q = request.GET.get("q", "").strip().lower()
    qs = Customer.objects.filter(cafe=cafe)
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    qs = qs.order_by("name")[:100]
    data = [{
        "id": c.id,
        "name": c.name,
        "email": c.email or "",
        "phone": c.phone or "",
    } for c in qs]
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
        
    return JsonResponse({
        "id": customer.id,
        "name": customer.name,
        "email": customer.email or "",
        "phone": customer.phone or "",
    })


@cafe_admin_required(require_admin=False)
@require_POST
def customer_delete(request, pk):
    """Delete a customer record."""
    customer = get_object_or_404(Customer, pk=pk, cafe=request.cafe)
    customer.delete()
    return JsonResponse({"ok": True})
