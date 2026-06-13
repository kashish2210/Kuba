from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cafe_pos.models import CafeTable, Floor, Product, ProductCategory, Profile
from tenants.models import AuditLog
from tenants.utils import log_action

from .forms import (
    CafeCustomizeForm,
    CategoryForm,
    EmployeeForm,
    FloorForm,
    ProductForm,
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
        # Public / marketing host.
        if request.user.is_authenticated:
            cafe = _user_cafe(request.user)
            if cafe is not None:
                return redirect(cafe.dashboard_url(request))
        return render(request, "landing.html")
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
    form = TableForm(request.POST, instance=table, cafe=request.cafe)
    if form.is_valid():
        form.save()
        log_action("update", cafe=request.cafe, request=request, target=table,
                   message=f"Updated table '{table.table_number}'.")
        messages.success(request, "Table updated.")
    else:
        messages.error(request, "Could not update table.")
    return redirect(f"{_floors_url(request)}?floor={table.floor_id}")


@cafe_admin_required
@require_POST
def table_delete(request, pk):
    table = get_object_or_404(CafeTable, pk=pk, cafe=request.cafe)
    floor_id = table.floor_id
    number = table.table_number
    table.delete()
    log_action("delete", cafe=request.cafe, request=request, target=None,
               message=f"Deleted table '{number}'.")
    messages.success(request, f"Table {number} deleted.")
    return redirect(f"{_floors_url(request)}?floor={floor_id}")


def _floors_url(request):
    from django.urls import reverse
    return reverse("dashboard:floors")


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
        form = ProductForm(request.POST, cafe=cafe)
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
        form = ProductForm(request.POST, instance=product, cafe=cafe)
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
