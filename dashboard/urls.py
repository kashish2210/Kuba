from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="index"),

    # Floors & tables
    path("floors/", views.floors, name="floors"),
    path("floors/add/", views.floor_create, name="floor-create"),
    path("floors/<int:pk>/edit/", views.floor_update, name="floor-update"),
    path("floors/<int:pk>/delete/", views.floor_delete, name="floor-delete"),
    path("tables/add/", views.table_create, name="table-create"),
    path("tables/<int:pk>/edit/", views.table_update, name="table-update"),
    path("tables/<int:pk>/delete/", views.table_delete, name="table-delete"),
    path("tables/move/", views.table_move, name="table-move"),

    # Products & categories
    path("products/", views.products, name="products"),
    path("products/add/", views.product_create, name="product-create"),
    path("products/<int:pk>/edit/", views.product_update, name="product-update"),
    path("products/<int:pk>/delete/", views.product_delete, name="product-delete"),
    path("categories/", views.categories, name="categories"),
    path("categories/add/", views.category_create, name="category-create"),
    path("categories/<int:pk>/edit/", views.category_update, name="category-update"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category-delete"),

    # Team
    path("team/", views.users, name="users"),
    path("team/<int:pk>/archive/", views.user_archive, name="user-archive"),
    path("team/<int:pk>/password/", views.user_password, name="user-password"),

    # Customize & audit
    path("customize/", views.customize, name="customize"),
    path("audit/", views.audit_log, name="audit-log"),

    # Deferred POS modules
    path("pos/", views.coming_soon, name="pos-session"),
    path("kds/", views.coming_soon, name="kds"),
    path("reports/", views.coming_soon, name="reports"),
    path("bookings/", views.coming_soon, name="bookings"),
    path("payment-methods/", views.coming_soon, name="payment-methods"),
    path("coupons/", views.coming_soon, name="coupons"),
]
