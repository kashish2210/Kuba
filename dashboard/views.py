import json
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
import json

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cafe_pos.models import (
    CafeTable,
    Coupon,
    Floor,
    Order,
    PaymentMethod,
    PaymentSettings,
    Product,
    ProductCategory,
    Profile,
    ReceiptSettings,
)
from tenants.models import AuditLog
from tenants.utils import log_action

from .forms import (
    CafeCustomizeForm,
    CategoryForm,
    CouponForm,
    EmployeeForm,
    FloorForm,
    PaymentSettingsForm,
    ProductForm,
    ReceiptSettingsForm,
    SetPasswordForm,
    TableForm,
)
from .mixins import cafe_admin_required


def _user_cafe(user):
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "cafe_id", None):
        return profile.cafe
    return user.owned_cafes.first()


# ─────────────────────────────────────────────────────────────────────────────
# Host dispatcher
# ─────────────────────────────────────────────────────────────────────────────
def home(request):
    """Route the root URL based on the host: admin / public landing / cafe panel."""
    if getattr(request, "is_admin_host", False):
        return redirect("/admin/")
    if getattr(request, "cafe", None) is None:
        # Public / marketing host. Login is subdomain-locked, so we never auto-jump
        # a logged-in user to their cafe from here — they navigate to their own host.
        return render(request, "landing.html")
    # Cashiers go straight to the POS terminal; admins/superusers get the admin panel.
    if request.user.is_authenticated and not request.user.is_superuser:
        profile = getattr(request.user, "profile", None)
        if profile is not None and profile.cafe_id == request.cafe.id and profile.role == "cashier":
            return redirect("pos:terminal")
    return cafe_dashboard(request)


@cafe_admin_required(require_admin=False)
def cafe_dashboard(request):
    cafe = request.cafe
    context = {
        "stat_products": Product.objects.filter(cafe=cafe).count(),
        "stat_categories": ProductCategory.objects.filter(cafe=cafe).count(),
        "stat_floors": Floor.objects.filter(cafe=cafe).count(),
        "stat_tables": CafeTable.objects.filter(cafe=cafe).count(),
        "stat_team": Profile.objects.filter(cafe=cafe, is_archived=False).count(),
        "recent_audit": AuditLog.objects.filter(cafe=cafe)[:8],
    }
    return render(request, "dashboard/index.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# Floors & tables  (the Table View screen)
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def floors(request):
    cafe = request.cafe
    floor_list = list(Floor.objects.filter(cafe=cafe))
    active_id = request.GET.get("floor")
    active_floor = None
    if active_id:
        active_floor = next((f for f in floor_list if str(f.id) == active_id), None)
    if active_floor is None and floor_list:
        active_floor = floor_list[0]

    tables = []
    if active_floor is not None:
        tables = list(CafeTable.objects.filter(floor=active_floor))

    edit_table = None
    edit_table_id = request.GET.get("edit_table")
    if edit_table_id:
        edit_table = get_object_or_404(CafeTable, pk=edit_table_id, cafe=cafe)

    context = {
        "floors": floor_list,
        "active_floor": active_floor,
        "tables": tables,
        "edit_floor": request.GET.get("edit_floor") == "1",
        "edit_table": edit_table,
        "floor_form": FloorForm(instance=active_floor if request.GET.get("edit_floor") == "1" else None),
        "table_form": TableForm(cafe=cafe, instance=edit_table),
    }
    return render(request, "dashboard/floors.html", context)


@cafe_admin_required
@require_POST
def floor_create(request):
    form = FloorForm(request.POST)
    if form.is_valid():
        floor = form.save(commit=False)
        floor.cafe = request.cafe
        floor.save()
        log_action("create", cafe=request.cafe, request=request, target=floor,
                   message=f"Added floor '{floor.name}'.")
        messages.success(request, f"Floor '{floor.name}' added.")
        return redirect(f"{_floors_url(request)}?floor={floor.id}")
    messages.error(request, "Could not add floor. Please check the name.")
    return redirect("dashboard:floors")


@cafe_admin_required
@require_POST
def floor_update(request, pk):
    floor = get_object_or_404(Floor, pk=pk, cafe=request.cafe)
    form = FloorForm(request.POST, instance=floor)
    if form.is_valid():
        form.save()
        log_action("update", cafe=request.cafe, request=request, target=floor,
                   message=f"Renamed floor to '{floor.name}'.")
        messages.success(request, "Floor updated.")
    return redirect(f"{_floors_url(request)}?floor={floor.id}")


@cafe_admin_required
@require_POST
def floor_delete(request, pk):
    floor = get_object_or_404(Floor, pk=pk, cafe=request.cafe)
    name = floor.name
    floor.delete()
    log_action("delete", cafe=request.cafe, request=request, target=None,
               message=f"Deleted floor '{name}' and its tables.")
    messages.success(request, f"Floor '{name}' deleted.")
    return redirect("dashboard:floors")


@cafe_admin_required
@require_POST
def table_create(request):
    form = TableForm(request.POST, cafe=request.cafe)
    if form.is_valid():
        table = form.save(commit=False)
        # Guard: the chosen floor must belong to this cafe.
        if table.floor.cafe_id != request.cafe.id:
            raise PermissionDenied("Invalid floor.")
        table.cafe = request.cafe
        table.sort_order = _next_table_sort_order(request.cafe, table.floor)
        table.save()
        log_action("create", cafe=request.cafe, request=request, target=table,
                   message=f"Added table '{table.table_number}' on {table.floor.name}.")
        messages.success(request, f"Table {table.table_number} added.")
        return redirect(f"{_floors_url(request)}?floor={table.floor_id}")
    messages.error(request, "Could not add table: " + "; ".join(
        f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    floor_id = request.POST.get("floor", "")
    return redirect(f"{_floors_url(request)}?floor={floor_id}")


@cafe_admin_required
@require_POST
def table_update(request, pk):
    table = get_object_or_404(CafeTable, pk=pk, cafe=request.cafe)
    previous_floor_id = table.floor_id
    form = TableForm(request.POST, instance=table, cafe=request.cafe)
    if form.is_valid():
        table = form.save(commit=False)
        table.save()
        if table.floor_id != previous_floor_id:
            table.sort_order = _next_table_sort_order(request.cafe, table.floor, exclude_table_id=table.pk)
            table.save(update_fields=["sort_order"])
        log_action("update", cafe=request.cafe, request=request, target=table,
                   message=f"Updated table '{table.table_number}'.")
        messages.success(request, "Table updated.")
    else:
        messages.error(request, "Could not update table.")
    return redirect(f"{_floors_url(request)}?floor={table.floor_id}")


@cafe_admin_required
@require_POST
def table_move(request):
    cafe = request.cafe
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "Invalid payload."}, status=400)

    try:
        table_id = int(payload.get("table_id"))
        target_floor_id = int(payload.get("target_floor_id"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "table_id and target_floor_id must be valid IDs."}, status=400)

    swap_table_id = payload.get("swap_table_id") or payload.get("before_table_id")
    try:
        swap_table_id = int(swap_table_id) if swap_table_id else None
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "swap_table_id must be a valid ID."}, status=400)

    if not table_id or not target_floor_id:
        return JsonResponse({"ok": False, "message": "table_id and target_floor_id are required."}, status=400)

    table = get_object_or_404(CafeTable, pk=table_id, cafe=cafe)
    target_floor = get_object_or_404(Floor, pk=target_floor_id, cafe=cafe)
    swap_table = None
    if swap_table_id:
        swap_table = CafeTable.objects.filter(pk=swap_table_id, cafe=cafe, floor=target_floor).first()
        if swap_table is None:
            return JsonResponse({"ok": False, "message": "Target table was not found."}, status=404)

    with transaction.atomic():
        if swap_table is not None:
            source_floor = table.floor
            source_sort_order = table.sort_order

            table.floor = swap_table.floor
            table.sort_order = swap_table.sort_order
            swap_table.floor = source_floor
            swap_table.sort_order = source_sort_order

            if table.floor_id == swap_table.floor_id:
                table.save(update_fields=["sort_order"])
                swap_table.save(update_fields=["sort_order"])
                _resequence_floor_tables(cafe, table.floor_id)
            else:
                table.save(update_fields=["floor", "sort_order"])
                swap_table.save(update_fields=["floor", "sort_order"])
                _resequence_floor_tables(cafe, source_floor.id)
                _resequence_floor_tables(cafe, target_floor.id)

            from django.urls import reverse
            return JsonResponse({
                "ok": True,
                "floor_id": target_floor.id,
                "redirect_url": f"{reverse('dashboard:floors')}?floor={target_floor.id}",
            })

        source_floor_id = table.floor_id
        source_ids = list(
            CafeTable.objects.filter(cafe=cafe, floor_id=source_floor_id)
            .exclude(pk=table.pk)
            .order_by("sort_order", "id")
            .values_list("id", flat=True)
        )

        target_ids = []
        if target_floor_id == source_floor_id:
            target_ids = source_ids.copy()
        else:
            target_ids = list(
                CafeTable.objects.filter(cafe=cafe, floor_id=target_floor_id)
                .order_by("sort_order", "id")
                .values_list("id", flat=True)
            )

        target_ids.append(table.id)

        source_id_set = set(source_ids)
        target_id_set = set(target_ids)

        if source_floor_id == target_floor_id:
            moved_ids = target_ids
            tables_by_id = {
                item.id: item
                for item in CafeTable.objects.filter(cafe=cafe, id__in=moved_ids)
            }
            for sort_order, table_id_value in enumerate(moved_ids):
                row = tables_by_id[table_id_value]
                row.sort_order = sort_order
                row.save(update_fields=["sort_order"])
        else:
            source_tables_by_id = {
                item.id: item
                for item in CafeTable.objects.filter(cafe=cafe, id__in=source_id_set)
            }
            for sort_order, table_id_value in enumerate(source_ids):
                row = source_tables_by_id[table_id_value]
                row.sort_order = sort_order
                row.save(update_fields=["sort_order"])

            target_tables_by_id = {
                item.id: item
                for item in CafeTable.objects.filter(cafe=cafe, id__in=target_id_set)
            }
            for sort_order, table_id_value in enumerate(target_ids):
                row = target_tables_by_id[table_id_value]
                row.sort_order = sort_order
                if row.id == table.id:
                    row.floor = target_floor
                    row.save(update_fields=["floor", "sort_order"])
                else:
                    row.save(update_fields=["sort_order"])

    from django.urls import reverse
    return JsonResponse({
        "ok": True,
        "floor_id": target_floor.id,
        "redirect_url": f"{reverse('dashboard:floors')}?floor={target_floor.id}",
    })


@cafe_admin_required
@require_POST
def table_delete(request, pk):
    table = get_object_or_404(CafeTable, pk=pk, cafe=request.cafe)
    floor_id = table.floor_id
    number = table.table_number
    table.delete()
    _resequence_floor_tables(request.cafe, floor_id)
    log_action("delete", cafe=request.cafe, request=request, target=None,
               message=f"Deleted table '{number}'.")
    messages.success(request, f"Table {number} deleted.")
    return redirect(f"{_floors_url(request)}?floor={floor_id}")


def _floors_url(request):
    from django.urls import reverse
    return reverse("dashboard:floors")


def _next_table_sort_order(cafe, floor, exclude_table_id=None):
    queryset = CafeTable.objects.filter(cafe=cafe, floor=floor)
    if exclude_table_id is not None:
        queryset = queryset.exclude(pk=exclude_table_id)
    return (queryset.aggregate(max_sort=Max("sort_order"))["max_sort"] or -1) + 1


def _resequence_floor_tables(cafe, floor_id):
    tables = list(CafeTable.objects.filter(cafe=cafe, floor_id=floor_id).order_by("sort_order", "id"))
    changed = False
    for index, table in enumerate(tables):
        if table.sort_order != index:
            table.sort_order = index
            changed = True
    if changed:
        CafeTable.objects.bulk_update(tables, ["sort_order"])


# ─────────────────────────────────────────────────────────────────────────────
# Products & categories
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def products(request):
    cafe = request.cafe
    product_list = Product.objects.filter(cafe=cafe).select_related("category")
    return render(request, "dashboard/products.html", {
        "products": product_list,
        "has_categories": ProductCategory.objects.filter(cafe=cafe).exists(),
    })


@cafe_admin_required
def product_create(request):
    cafe = request.cafe
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, cafe=cafe)
        if form.is_valid():
            product = form.save(commit=False)
            product.cafe = cafe
            product.save()
            log_action("create", cafe=cafe, request=request, target=product,
                       message=f"Added product '{product.name}'.")
            messages.success(request, f"Product '{product.name}' added.")
            return redirect("dashboard:products")
    else:
        form = ProductForm(cafe=cafe)
    return render(request, "dashboard/product_form.html", {"form": form, "mode": "Add"})


@cafe_admin_required
def product_update(request, pk):
    cafe = request.cafe
    product = get_object_or_404(Product, pk=pk, cafe=cafe)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product, cafe=cafe)
        if form.is_valid():
            form.save()
            log_action("update", cafe=cafe, request=request, target=product,
                       message=f"Updated product '{product.name}'.")
            messages.success(request, "Product updated.")
            return redirect("dashboard:products")
    else:
        form = ProductForm(instance=product, cafe=cafe)
    return render(request, "dashboard/product_form.html", {"form": form, "mode": "Edit", "product": product})


@cafe_admin_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, cafe=request.cafe)
    name = product.name
    product.delete()
    log_action("delete", cafe=request.cafe, request=request, target=None,
               message=f"Deleted product '{name}'.")
    messages.success(request, f"Product '{name}' deleted.")
    return redirect("dashboard:products")


@cafe_admin_required
def categories(request):
    cafe = request.cafe
    edit_id = request.GET.get("edit")
    instance = None
    if edit_id:
        instance = get_object_or_404(ProductCategory, pk=edit_id, cafe=cafe)
    form = CategoryForm(instance=instance)
    return render(request, "dashboard/categories.html", {
        "categories": ProductCategory.objects.filter(cafe=cafe),
        "form": form,
        "edit_instance": instance,
    })


@cafe_admin_required
@require_POST
def category_create(request):
    cafe = request.cafe
    form = CategoryForm(request.POST)
    if form.is_valid():
        category = form.save(commit=False)
        category.cafe = cafe
        category.save()
        log_action("create", cafe=cafe, request=request, target=category,
                   message=f"Added category '{category.name}'.")
        messages.success(request, f"Category '{category.name}' added.")
    else:
        messages.error(request, "Could not add category (name may already exist).")
    return redirect("dashboard:categories")


@cafe_admin_required
@require_POST
def category_update(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk, cafe=request.cafe)
    form = CategoryForm(request.POST, instance=category)
    if form.is_valid():
        form.save()
        log_action("update", cafe=request.cafe, request=request, target=category,
                   message=f"Updated category '{category.name}'.")
        messages.success(request, "Category updated.")
    return redirect("dashboard:categories")


@cafe_admin_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk, cafe=request.cafe)
    name = category.name
    if category.products.exists():
        messages.error(request, f"Cannot delete '{name}' — it still has products.")
        return redirect("dashboard:categories")
    category.delete()
    log_action("delete", cafe=request.cafe, request=request, target=None,
               message=f"Deleted category '{name}'.")
    messages.success(request, f"Category '{name}' deleted.")
    return redirect("dashboard:categories")


# ─────────────────────────────────────────────────────────────────────────────
# Coupons
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def coupons(request):
    cafe = request.cafe
    edit_id = request.GET.get("edit")
    instance = get_object_or_404(Coupon, pk=edit_id, cafe=cafe) if edit_id else None
    return render(request, "dashboard/coupons.html", {
        "coupons": Coupon.objects.filter(cafe=cafe).order_by("code"),
        "form": CouponForm(instance=instance, cafe=cafe),
        "edit_instance": instance,
    })


@cafe_admin_required
@require_POST
def coupon_create(request):
    form = CouponForm(request.POST, cafe=request.cafe)
    if form.is_valid():
        coupon = form.save(commit=False)
        coupon.cafe = request.cafe
        coupon.save()
        log_action("create", cafe=request.cafe, request=request, target=coupon,
                   message=f"Created coupon '{coupon.code}'.")
        messages.success(request, f"Coupon '{coupon.code}' created.")
    else:
        messages.error(request, "Could not create coupon: " + "; ".join(
            f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return redirect("dashboard:coupons")


@cafe_admin_required
@require_POST
def coupon_update(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk, cafe=request.cafe)
    form = CouponForm(request.POST, instance=coupon, cafe=request.cafe)
    if form.is_valid():
        form.save()
        log_action("update", cafe=request.cafe, request=request, target=coupon,
                   message=f"Updated coupon '{coupon.code}'.")
        messages.success(request, "Coupon updated.")
    else:
        messages.error(request, "Could not update coupon.")
    return redirect("dashboard:coupons")


@cafe_admin_required
@require_POST
def coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk, cafe=request.cafe)
    code = coupon.code
    coupon.delete()
    log_action("delete", cafe=request.cafe, request=request, target=None,
               message=f"Deleted coupon '{code}'.")
    messages.success(request, f"Coupon '{code}' deleted.")
    return redirect("dashboard:coupons")


# ─────────────────────────────────────────────────────────────────────────────
# Team / employees
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def users(request):
    cafe = request.cafe
    form = EmployeeForm()
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            Profile.objects.update_or_create(
                user=user,
                defaults={"cafe": cafe, "role": form.cleaned_data["role"], "is_archived": False},
            )
            log_action("create", cafe=cafe, request=request, target=user,
                       message=f"Added team member '{user.username}' ({form.cleaned_data['role']}).")
            messages.success(request, f"Team member '{user.username}' added.")
            return redirect("dashboard:users")
    members = Profile.objects.filter(cafe=cafe).select_related("user").order_by("is_archived", "user__username")
    return render(request, "dashboard/users.html", {"members": members, "form": form})


@cafe_admin_required
@require_POST
def user_archive(request, pk):
    profile = get_object_or_404(Profile, pk=pk, cafe=request.cafe)
    if profile.user_id == request.user.id:
        messages.error(request, "You cannot archive your own account.")
        return redirect("dashboard:users")
    profile.is_archived = not profile.is_archived
    profile.user.is_active = not profile.is_archived
    profile.user.save(update_fields=["is_active"])
    profile.save(update_fields=["is_archived"])
    log_action("update", cafe=request.cafe, request=request, target=profile.user,
               message=f"{'Archived' if profile.is_archived else 'Restored'} '{profile.user.username}'.")
    messages.success(request, f"{'Archived' if profile.is_archived else 'Restored'} {profile.user.username}.")
    return redirect("dashboard:users")


@cafe_admin_required
@require_POST
def user_password(request, pk):
    profile = get_object_or_404(Profile, pk=pk, cafe=request.cafe)
    form = SetPasswordForm(request.POST)
    if form.is_valid():
        profile.user.set_password(form.cleaned_data["password"])
        profile.user.save(update_fields=["password"])
        log_action("update", cafe=request.cafe, request=request, target=profile.user,
                   message=f"Reset password for '{profile.user.username}'.")
        messages.success(request, f"Password updated for {profile.user.username}.")
    else:
        messages.error(request, "Password too weak (min 8 characters).")
    return redirect("dashboard:users")


# ─────────────────────────────────────────────────────────────────────────────
# Customize cafe
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def customize(request):
    cafe = request.cafe
    if request.method == "POST":
        form = CafeCustomizeForm(request.POST, request.FILES, instance=cafe)
        if form.is_valid():
            form.save()
            log_action("update", cafe=cafe, request=request, target=cafe,
                       message="Updated cafe branding/details.")
            messages.success(request, "Cafe details saved.")
            return redirect("dashboard:customize")
    else:
        form = CafeCustomizeForm(instance=cafe)
    return render(request, "dashboard/customize.html", {"form": form})


# ─────────────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def audit_log(request):
    logs = AuditLog.objects.filter(cafe=request.cafe).select_related("actor")
    paginator = Paginator(logs, 30)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "dashboard/audit_log.html", {"page_obj": page})


# ─────────────────────────────────────────────────────────────────────────────
# Payment settings (Razorpay / Stripe / UPI config)
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def payment_settings(request):
    from pos.services import ensure_payment_methods

    cafe = request.cafe
    ensure_payment_methods(cafe)
    settings_obj, _ = PaymentSettings.objects.get_or_create(cafe=cafe)
    if request.method == "POST":
        form = PaymentSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            for t in ("cash", "card", "upi"):
                pm = PaymentMethod.objects.filter(cafe=cafe, type=t).first()
                if pm:
                    pm.is_enabled = bool(request.POST.get(f"enable_{t}"))
                    if t == "upi" and form.cleaned_data.get("upi_id"):
                        pm.upi_id = form.cleaned_data["upi_id"]
                    pm.save()
            log_action("update", cafe=cafe, request=request, target=settings_obj,
                       message="Updated payment settings.")
            messages.success(request, "Payment settings saved.")
            return redirect("dashboard:payment-methods")
    else:
        form = PaymentSettingsForm(instance=settings_obj)
    methods = {m.type: m for m in PaymentMethod.objects.filter(cafe=cafe)}
    return render(request, "dashboard/payment_settings.html", {"form": form, "methods": methods})


# ─────────────────────────────────────────────────────────────────────────────
# Receipts (default + custom HTML with data pills + per-cafe SMTP)
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required
def receipt_settings(request):
    from cafe_pos.receipts import DATA_PILLS

    cafe = request.cafe
    rs, _ = ReceiptSettings.objects.get_or_create(cafe=cafe)
    if request.method == "POST":
        form = ReceiptSettingsForm(request.POST, instance=rs)
        if form.is_valid():
            form.save()
            log_action("update", cafe=cafe, request=request, target=rs,
                       message="Updated receipt settings.")
            messages.success(request, "Receipt settings saved.")
            return redirect("dashboard:receipts")
    else:
        form = ReceiptSettingsForm(instance=rs)
    return render(request, "dashboard/receipt_settings.html",
                  {"form": form, "pills": DATA_PILLS, "settings": rs})


@cafe_admin_required
@require_POST
def receipt_preview(request):
    """Render the receipt against the latest order, using the POSTed (unsaved) HTML."""
    from cafe_pos.receipts import order_context
    from django.template import Context, Template
    from django.template.loader import render_to_string
    from django.utils.safestring import mark_safe

    order = Order.objects.filter(cafe=request.cafe).order_by("-created_at").first()
    if order is None:
        return HttpResponse("<p style='padding:24px;font-family:sans-serif;color:#888'>"
                            "No orders yet — take one in the POS to preview a receipt.</p>")
    html_template = (request.POST.get("template_html") or "").strip()
    use_default = request.POST.get("use_default") == "on" or not html_template
    if use_default:
        return HttpResponse(render_to_string("receipts/default_receipt.html", order_context(order)))
    ctx = order_context(order)
    ctx["items_table"] = mark_safe(ctx["items_table"])
    ctx["logo"] = mark_safe(ctx["logo"])
    try:
        html = Template(html_template).render(Context(ctx))
    except Exception as exc:  # show template errors inline in the preview
        html = f"<p style='color:#c0392b;padding:24px;font-family:sans-serif'>Template error: {exc}</p>"
    return HttpResponse(html)


@cafe_admin_required
@require_POST
def receipt_test(request):
    from cafe_pos.receipts import email_receipt

    cafe = request.cafe
    order = Order.objects.filter(cafe=cafe).order_by("-created_at").first()
    to = (request.POST.get("email") or request.user.email or "").strip()
    if order is None:
        messages.error(request, "No orders yet to use as a sample receipt.")
    elif not to:
        messages.error(request, "Add an email address to send the test to.")
    elif email_receipt(order, to):
        messages.success(request, f"Test receipt sent to {to}.")
    else:
        messages.error(request, "Could not send the test — check the SMTP settings.")
    return redirect("dashboard:receipts")


# ─────────────────────────────────────────────────────────────────────────────
# Placeholders for deferred POS modules
# ─────────────────────────────────────────────────────────────────────────────
@cafe_admin_required(require_admin=False)
def coming_soon(request):
    label = {
        "pos-session": "POS Terminal",
        "kds": "Kitchen Display",
        "reports": "Reports",
        "bookings": "Bookings",
        "payment-methods": "Payment Methods",
        "coupons": "Coupons & Promotions",
    }.get(request.resolver_match.url_name, "This module")
    return render(request, "dashboard/coming_soon.html", {"label": label})
