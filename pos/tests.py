import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cafe_pos.models import (
    CafeTable,
    Floor,
    Order,
    OrderLineItem,
    POSSession,
    Product,
    ProductCategory,
    Profile,
)
from tenants.models import Cafe


class OrderStartTableSwitchTests(TestCase):
    host = "postableswitch.localhost"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pos_admin",
            email="pos-admin@example.com",
            password="password",
        )
        self.cafe = Cafe.objects.create(name="POS Table Switch", subdomain="postableswitch", owner=self.user)
        Profile.objects.create(user=self.user, cafe=self.cafe, role=Profile.Role.ADMIN)
        self.session = POSSession.objects.create(
            cafe=self.cafe,
            opened_by=self.user,
            status=POSSession.SessionStatus.OPEN,
        )
        self.floor = Floor.objects.create(cafe=self.cafe, name="Ground", sort_order=0)
        self.table_1 = CafeTable.objects.create(
            cafe=self.cafe,
            floor=self.floor,
            table_number="1",
            seats=4,
            sort_order=0,
        )
        self.table_2 = CafeTable.objects.create(
            cafe=self.cafe,
            floor=self.floor,
            table_number="2",
            seats=4,
            sort_order=1,
        )
        self.category = ProductCategory.objects.create(cafe=self.cafe, name="Coffee", color="#335577")
        self.product = Product.objects.create(
            cafe=self.cafe,
            category=self.category,
            name="Espresso",
            price=Decimal("100.00"),
            unit_of_measure=Product.UnitOfMeasure.PER_CUP,
            tax_percentage=Decimal("5.00"),
        )
        self.client.login(username="pos_admin", password="password")

    def post_start(self, payload):
        return self.client.post(
            reverse("pos:order-start"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_HOST=self.host,
        )

    def create_order(self, table):
        return Order.objects.create(
            cafe=self.cafe,
            session=self.session,
            table=table,
            employee=self.user,
            status=Order.OrderStatus.DRAFT,
            order_number=f"ORD-{Order.objects.filter(cafe=self.cafe).count() + 1:04d}",
            subtotal=0,
            tax_amount=0,
            discount_amount=0,
            total=0,
        )

    def test_empty_current_order_moves_to_new_table_without_creating_order(self):
        order = self.create_order(self.table_1)

        response = self.post_start({"table": self.table_2.id, "current_order": order.id})

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(response.json()["id"], order.id)
        self.assertEqual(order.table_id, self.table_2.id)
        self.assertEqual(Order.objects.filter(cafe=self.cafe).count(), 1)

    def test_current_order_with_products_stays_put_and_new_table_gets_new_order(self):
        order = self.create_order(self.table_1)
        OrderLineItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            line_discount=0,
            line_total=self.product.price,
        )

        response = self.post_start({"table": self.table_2.id, "current_order": order.id})

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.table_id, self.table_1.id)
        self.assertEqual(response.json()["table_id"], self.table_2.id)
        self.assertEqual(Order.objects.filter(cafe=self.cafe).count(), 2)
