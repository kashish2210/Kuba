from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.utils import timezone


def seed_dummy_data(apps, schema_editor):
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")

    User = apps.get_model(user_app_label, user_model_name)
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

    admin_user, created = User.objects.get_or_create(
        username="seed_admin",
        defaults={
            "email": "seed_admin@cafe.com",
            "first_name": "Seed",
            "last_name": "Admin",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )
    if created:
        admin_user.password = make_password("Admin@123")
        admin_user.save(update_fields=["password"])

    cashier_user, created = User.objects.get_or_create(
        username="seed_cashier",
        defaults={
            "email": "seed_cashier@cafe.com",
            "first_name": "Seed",
            "last_name": "Cashier",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        },
    )
    if created:
        cashier_user.password = make_password("Cashier@123")
        cashier_user.save(update_fields=["password"])

    Profile.objects.get_or_create(
        user=admin_user,
        defaults={"role": "admin", "is_archived": False},
    )
    Profile.objects.get_or_create(
        user=cashier_user,
        defaults={"role": "cashier", "is_archived": False},
    )

    beverages, _ = ProductCategory.objects.get_or_create(
        name="Beverages",
        defaults={"color": "#FF6B6B"},
    )
    snacks, _ = ProductCategory.objects.get_or_create(
        name="Snacks",
        defaults={"color": "#4ECDC4"},
    )

    espresso, _ = Product.objects.get_or_create(
        name="Espresso",
        defaults={
            "category": beverages,
            "price": Decimal("120.00"),
            "unit_of_measure": "per cup",
            "tax_percentage": Decimal("5.00"),
            "description": "Strong espresso shot",
            "show_in_kds": True,
            "is_active": True,
        },
    )
    cappuccino, _ = Product.objects.get_or_create(
        name="Cappuccino",
        defaults={
            "category": beverages,
            "price": Decimal("180.00"),
            "unit_of_measure": "per cup",
            "tax_percentage": Decimal("5.00"),
            "description": "Classic cappuccino",
            "show_in_kds": True,
            "is_active": True,
        },
    )
    croissant, _ = Product.objects.get_or_create(
        name="Butter Croissant",
        defaults={
            "category": snacks,
            "price": Decimal("95.00"),
            "unit_of_measure": "per piece",
            "tax_percentage": Decimal("5.00"),
            "description": "Freshly baked croissant",
            "show_in_kds": True,
            "is_active": True,
        },
    )

    ground_floor, _ = Floor.objects.get_or_create(name="Ground Floor")
    terrace, _ = Floor.objects.get_or_create(name="Terrace")

    table_g1, _ = CafeTable.objects.get_or_create(
        floor=ground_floor,
        table_number="T1",
        defaults={"seats": 4, "is_active": True},
    )
    CafeTable.objects.get_or_create(
        floor=ground_floor,
        table_number="T2",
        defaults={"seats": 2, "is_active": True},
    )
    CafeTable.objects.get_or_create(
        floor=terrace,
        table_number="T1",
        defaults={"seats": 6, "is_active": True},
    )

    PaymentMethod.objects.update_or_create(
        type="cash",
        defaults={"is_enabled": True, "upi_id": None},
    )
    PaymentMethod.objects.update_or_create(
        type="card",
        defaults={"is_enabled": True, "upi_id": None},
    )
    PaymentMethod.objects.update_or_create(
        type="upi",
        defaults={"is_enabled": True, "upi_id": "odoo.cafe@upi"},
    )

    save10, _ = Coupon.objects.get_or_create(
        code="SAVE10",
        defaults={
            "discount_type": "percentage",
            "discount_value": Decimal("10.00"),
            "is_active": True,
        },
    )
    Coupon.objects.get_or_create(
        code="FLAT50",
        defaults={
            "discount_type": "fixed",
            "discount_value": Decimal("50.00"),
            "is_active": True,
        },
    )

    espresso_promo, _ = Promotion.objects.get_or_create(
        name="Espresso 3+ Deal",
        defaults={
            "apply_to": "product",
            "product": espresso,
            "min_quantity": 3,
            "min_order_amount": None,
            "discount_type": "percentage",
            "discount_value": Decimal("15.00"),
            "is_active": True,
        },
    )
    Promotion.objects.get_or_create(
        name="Order 500 Flat 75",
        defaults={
            "apply_to": "order",
            "product": None,
            "min_quantity": None,
            "min_order_amount": Decimal("500.00"),
            "discount_type": "fixed",
            "discount_value": Decimal("75.00"),
            "is_active": True,
        },
    )

    customer_anita, _ = Customer.objects.get_or_create(
        email="anita@example.com",
        defaults={"name": "Anita Sharma", "phone": "+919876543210"},
    )
    Customer.objects.get_or_create(
        email="rahul@example.com",
        defaults={"name": "Rahul Verma", "phone": "+919123456789"},
    )

    now = timezone.now()

    closed_session, _ = POSSession.objects.get_or_create(
        opened_by=admin_user,
        opened_at=now - timezone.timedelta(days=1),
        defaults={
            "closed_at": now - timezone.timedelta(days=1, hours=-8),
            "closing_sale_amount": Decimal("865.00"),
            "status": "closed",
        },
    )

    open_session, _ = POSSession.objects.get_or_create(
        status="open",
        defaults={
            "opened_by": admin_user,
            "opened_at": now,
            "closed_at": None,
            "closing_sale_amount": None,
        },
    )

    paid_order, _ = Order.objects.get_or_create(
        order_number="ORD-DEMO-0001",
        defaults={
            "session": open_session,
            "table": table_g1,
            "customer": customer_anita,
            "employee": cashier_user,
            "status": "paid",
            "subtotal": Decimal("540.00"),
            "tax_amount": Decimal("27.00"),
            "discount_amount": Decimal("54.00"),
            "total": Decimal("513.00"),
            "coupon": save10,
            "promotion": espresso_promo,
            "created_at": now,
            "paid_at": now,
        },
    )

    draft_order, _ = Order.objects.get_or_create(
        order_number="ORD-DEMO-0002",
        defaults={
            "session": open_session,
            "table": table_g1,
            "customer": None,
            "employee": cashier_user,
            "status": "draft",
            "subtotal": Decimal("275.00"),
            "tax_amount": Decimal("13.75"),
            "discount_amount": Decimal("0.00"),
            "total": Decimal("288.75"),
            "coupon": None,
            "promotion": None,
            "created_at": now,
            "paid_at": None,
        },
    )

    OrderLineItem.objects.get_or_create(
        order=paid_order,
        product=espresso,
        defaults={
            "quantity": 3,
            "unit_price": Decimal("120.00"),
            "line_discount": Decimal("36.00"),
            "line_total": Decimal("324.00"),
            "kds_status": "completed",
        },
    )
    OrderLineItem.objects.get_or_create(
        order=paid_order,
        product=cappuccino,
        defaults={
            "quantity": 1,
            "unit_price": Decimal("180.00"),
            "line_discount": Decimal("0.00"),
            "line_total": Decimal("180.00"),
            "kds_status": "completed",
        },
    )
    OrderLineItem.objects.get_or_create(
        order=draft_order,
        product=croissant,
        defaults={
            "quantity": 2,
            "unit_price": Decimal("95.00"),
            "line_discount": Decimal("0.00"),
            "line_total": Decimal("190.00"),
            "kds_status": "to_cook",
        },
    )

    PaymentRecord.objects.get_or_create(
        order=paid_order,
        defaults={
            "method_type": "cash",
            "amount_tendered": Decimal("600.00"),
            "change_due": Decimal("87.00"),
            "transaction_ref": None,
            "paid_at": now,
        },
    )

    if closed_session.closing_sale_amount is None:
        closed_session.closing_sale_amount = Decimal("865.00")
        closed_session.save(update_fields=["closing_sale_amount"])


def unseed_dummy_data(apps, schema_editor):
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")

    User = apps.get_model(user_app_label, user_model_name)
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

    Order.objects.filter(order_number__in=["ORD-DEMO-0001", "ORD-DEMO-0002"]).delete()

    POSSession.objects.filter(status="open", opened_by__username="seed_admin").delete()
    POSSession.objects.filter(status="closed", opened_by__username="seed_admin").delete()

    Customer.objects.filter(email__in=["anita@example.com", "rahul@example.com"]).delete()

    Promotion.objects.filter(name__in=["Espresso 3+ Deal", "Order 500 Flat 75"]).delete()
    Coupon.objects.filter(code__in=["SAVE10", "FLAT50"]).delete()

    PaymentMethod.objects.filter(type__in=["cash", "card", "upi"]).delete()

    Product.objects.filter(name__in=["Espresso", "Cappuccino", "Butter Croissant"]).delete()
    ProductCategory.objects.filter(name__in=["Beverages", "Snacks"]).delete()

    CafeTable.objects.filter(table_number__in=["T1", "T2"]).delete()
    Floor.objects.filter(name__in=["Ground Floor", "Terrace"]).delete()

    Profile.objects.filter(user__username__in=["seed_admin", "seed_cashier"]).delete()
    User.objects.filter(username__in=["seed_admin", "seed_cashier"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cafe_pos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_dummy_data, unseed_dummy_data),
    ]
