import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cafe_pos.models import CafeTable, Floor, Profile
from tenants.models import Cafe


class LandingRedirectTests(TestCase):
    def test_authenticated_root_user_is_sent_to_their_cafe(self):
        user = get_user_model().objects.create_user(
            username="landing_admin",
            email="landing-admin@example.com",
            password="password",
        )
        cafe = Cafe.objects.create(name="Landing Cafe", subdomain="landingcafe", owner=user)
        Profile.objects.create(user=user, cafe=cafe, role=Profile.Role.ADMIN)
        self.client.login(username="landing_admin", password="password")

        response = self.client.get("/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://landingcafe.localhost/")


class TableMoveTests(TestCase):
    host = "tablemove.localhost"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        self.cafe = Cafe.objects.create(name="Table Move Cafe", subdomain="tablemove", owner=self.user)
        Profile.objects.create(user=self.user, cafe=self.cafe, role=Profile.Role.ADMIN)
        self.floor = Floor.objects.create(cafe=self.cafe, name="Ground", sort_order=0)
        self.tables = [
            CafeTable.objects.create(
                cafe=self.cafe,
                floor=self.floor,
                table_number=str(index + 1),
                sort_order=index,
                seats=4,
            )
            for index in range(4)
        ]
        self.client.login(username="admin", password="password")

    def post_move(self, payload):
        return self.client.post(
            reverse("dashboard:table-move"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_HOST=self.host,
        )

    def ordered_table_numbers(self):
        return list(
            CafeTable.objects.filter(floor=self.floor)
            .order_by("sort_order", "id")
            .values_list("table_number", flat=True)
        )

    def test_drop_on_table_swaps_the_two_tables(self):
        response = self.post_move({
            "table_id": self.tables[0].id,
            "target_floor_id": self.floor.id,
            "swap_table_id": self.tables[2].id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ordered_table_numbers(), ["3", "2", "1", "4"])

    def test_drop_on_grid_appends_table_on_same_floor(self):
        response = self.post_move({
            "table_id": str(self.tables[0].id),
            "target_floor_id": str(self.floor.id),
            "before_table_id": None,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ordered_table_numbers(), ["2", "3", "4", "1"])
