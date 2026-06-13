from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.utils import timezone


def seed_demo_cafe(apps, schema_editor):
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")

    User = apps.get_model(user_app_label, user_model_name)
    Cafe = apps.get_model("tenants", "Cafe")
    Profile = apps.get_model("cafe_pos", "Profile")
    ProductCategory = apps.get_model("cafe_pos", "ProductCategory")
    Product = apps.get_model("cafe_pos", "Product")
    Floor = apps.get_model("cafe_pos", "Floor")
    CafeTable = apps.get_model("cafe_pos", "CafeTable")
    PaymentMethod = apps.get_model("cafe_pos", "PaymentMethod")
    Coupon = apps.get_model("cafe_pos", "Coupon")
    Promotion = apps.get_model("cafe_pos", "Promotion")
    Customer = apps.get_model("cafe_pos", "Customer")
    POSSession = apps.get_model("cafe_pos", "POSSession")
    Order = apps.get_model("cafe_pos", "Order")
    OrderLineItem = apps.get_model("cafe_pos", "OrderLineItem")
    PaymentRecord = apps.get_model("cafe_pos", "PaymentRecord")

    # ── Cafe admin & cashier (cafe members, NOT platform superusers) ──────────
    admin_user, created = User.objects.get_or_create(
        username="demo_admin",
        defaults={
            "email": "demo_admin@cafe.com",
            "first_name": "Demo",
            "last_name": "Admin",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        },
    )
    if created:
        admin_user.password = make_password("Admin@123")
        admin_user.save(update_fields=["password"])

    cashier_user, created = User.objects.get_or_create(
        username="demo_cashier",
        defaults={
            "email": "demo_cashier@cafe.com",
            "first_name": "Demo",
            "last_name": "Cashier",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        },
    )
    if created:
        cashier_user.password = make_password("Cashier@123")
        cashier_user.save(update_fields=["password"])

    # ── The demo cafe (tenant) ────────────────────────────────────────────────
    cafe, _ = Cafe.objects.get_or_create(
        subdomain="demo",
        defaults={
            "name": "Demo Cafe",
            "slug": "demo-cafe",
            "owner": admin_user,
            "is_active": True,
            "logo_svg": "",
        },
    )

    Profile.objects.get_or_create(
        user=admin_user, defaults={"cafe": cafe, "role": "admin", "is_archived": False}
    )
    Profile.objects.get_or_create(
        user=cashier_user, defaults={"cafe": cafe, "role": "cashier", "is_archived": False}
    )

    beverages, _ = ProductCategory.objects.get_or_create(
        cafe=cafe, name="Beverages", defaults={"color": "#FF6B6B"}
    )
    snacks, _ = ProductCategory.objects.get_or_create(
        cafe=cafe, name="Snacks", defaults={"color": "#4ECDC4"}
    )

    espresso, _ = Product.objects.get_or_create(
        cafe=cafe, name="Espresso",
        defaults={
            "category": beverages, "price": Decimal("120.00"), "unit_of_measure": "per cup",
            "tax_percentage": Decimal("5.00"), "description": "Strong espresso shot",
            "show_in_kds": True, "is_active": True,
        },
    )
    cappuccino, _ = Product.objects.get_or_create(
        cafe=cafe, name="Cappuccino",
        defaults={
            "category": beverages, "price": Decimal("180.00"), "unit_of_measure": "per cup",
            "tax_percentage": Decimal("5.00"), "description": "Classic cappuccino",
            "show_in_kds": True, "is_active": True,
        },
    )
    croissant, _ = Product.objects.get_or_create(
        cafe=cafe, name="Butter Croissant",
        defaults={
            "category": snacks, "price": Decimal("95.00"), "unit_of_measure": "per piece",
            "tax_percentage": Decimal("5.00"), "description": "Freshly baked croissant",
            "show_in_kds": True, "is_active": True,
        },
    )

    ground_floor, _ = Floor.objects.get_or_create(cafe=cafe, name="Ground Floor", defaults={"sort_order": 0})
    terrace, _ = Floor.objects.get_or_create(cafe=cafe, name="Terrace", defaults={"sort_order": 1})

    # 16 numbered tables on the ground floor (matches the Table View grid).
    for n in range(1, 17):
        CafeTable.objects.get_or_create(
            floor=ground_floor, table_number=str(n),
            defaults={"cafe": cafe, "seats": 4, "is_active": True},
        )
    table_g1 = CafeTable.objects.filter(floor=ground_floor, table_number="1").first()
    CafeTable.objects.get_or_create(
        floor=terrace, table_number="1", defaults={"cafe": cafe, "seats": 6, "is_active": True}
    )

    PaymentMethod.objects.update_or_create(
        cafe=cafe, type="cash", defaults={"is_enabled": True, "upi_id": None}
    )
    PaymentMethod.objects.update_or_create(
        cafe=cafe, type="card", defaults={"is_enabled": True, "upi_id": None}
    )
    PaymentMethod.objects.update_or_create(
        cafe=cafe, type="upi", defaults={"is_enabled": True, "upi_id": "demo.cafe@upi"}
    )

    save10, _ = Coupon.objects.get_or_create(
        cafe=cafe, code="SAVE10",
        defaults={"discount_type": "percentage", "discount_value": Decimal("10.00"), "is_active": True},
    )
    Coupon.objects.get_or_create(
        cafe=cafe, code="FLAT50",
        defaults={"discount_type": "fixed", "discount_value": Decimal("50.00"), "is_active": True},
    )

    espresso_promo, _ = Promotion.objects.get_or_create(
        cafe=cafe, name="Espresso 3+ Deal",
        defaults={
            "apply_to": "product", "product": espresso, "min_quantity": 3, "min_order_amount": None,
            "discount_type": "percentage", "discount_value": Decimal("15.00"), "is_active": True,
        },
    )
    Promotion.objects.get_or_create(
        cafe=cafe, name="Order 500 Flat 75",
        defaults={
            "apply_to": "order", "product": None, "min_quantity": None,
            "min_order_amount": Decimal("500.00"), "discount_type": "fixed",
            "discount_value": Decimal("75.00"), "is_active": True,
        },
    )

    customer_anita, _ = Customer.objects.get_or_create(
        cafe=cafe, email="anita@example.com",
        defaults={"name": "Anita Sharma", "phone": "+919876543210"},
    )
    Customer.objects.get_or_create(
        cafe=cafe, email="rahul@example.com",
        defaults={"name": "Rahul Verma", "phone": "+919123456789"},
    )

    now = timezone.now()

    closed_session, _ = POSSession.objects.get_or_create(
        cafe=cafe, opened_by=admin_user, opened_at=now - timezone.timedelta(days=1),
        defaults={
            "closed_at": now - timezone.timedelta(days=1, hours=-8),
            "closing_sale_amount": Decimal("865.00"), "status": "closed",
        },
    )

    open_session, _ = POSSession.objects.get_or_create(
        cafe=cafe, status="open",
        defaults={"opened_by": admin_user, "opened_at": now, "closed_at": None, "closing_sale_amount": None},
    )

    paid_order, _ = Order.objects.get_or_create(
        cafe=cafe, order_number="ORD-DEMO-0001",
        defaults={
            "session": open_session, "table": table_g1, "customer": customer_anita,
            "employee": cashier_user, "status": "paid", "subtotal": Decimal("540.00"),
            "tax_amount": Decimal("27.00"), "discount_amount": Decimal("54.00"),
            "total": Decimal("513.00"), "coupon": save10, "promotion": espresso_promo,
            "paid_at": now,
        },
    )

    draft_order, _ = Order.objects.get_or_create(
        cafe=cafe, order_number="ORD-DEMO-0002",
        defaults={
            "session": open_session, "table": table_g1, "customer": None,
            "employee": cashier_user, "status": "draft", "subtotal": Decimal("275.00"),
            "tax_amount": Decimal("13.75"), "discount_amount": Decimal("0.00"),
            "total": Decimal("288.75"), "coupon": None, "promotion": None, "paid_at": None,
        },
    )

    OrderLineItem.objects.get_or_create(
        order=paid_order, product=espresso,
        defaults={"quantity": 3, "unit_price": Decimal("120.00"), "line_discount": Decimal("36.00"),
                  "line_total": Decimal("324.00"), "kds_status": "completed"},
    )
    OrderLineItem.objects.get_or_create(
        order=paid_order, product=cappuccino,
        defaults={"quantity": 1, "unit_price": Decimal("180.00"), "line_discount": Decimal("0.00"),
                  "line_total": Decimal("180.00"), "kds_status": "completed"},
    )
    OrderLineItem.objects.get_or_create(
        order=draft_order, product=croissant,
        defaults={"quantity": 2, "unit_price": Decimal("95.00"), "line_discount": Decimal("0.00"),
                  "line_total": Decimal("190.00"), "kds_status": "to_cook"},
    )

    PaymentRecord.objects.get_or_create(
        order=paid_order,
        defaults={"method_type": "cash", "amount_tendered": Decimal("600.00"),
                  "change_due": Decimal("87.00"), "transaction_ref": None, "paid_at": now},
    )


def unseed_demo_cafe(apps, schema_editor):
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app_label, user_model_name)
    Cafe = apps.get_model("tenants", "Cafe")

    # Deleting the cafe cascades to all its cafe_pos rows.
    Cafe.objects.filter(subdomain="demo").delete()
    User.objects.filter(username__in=["demo_admin", "demo_cashier"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cafe_pos", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_demo_cafe, unseed_demo_cafe),
    ]
