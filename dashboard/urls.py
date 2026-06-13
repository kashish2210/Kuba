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
    path("products/bulk/", views.product_bulk_action, name="product-bulk-action"),
    path("categories/", views.categories, name="categories"),
    path("categories/add/", views.category_create, name="category-create"),
    path("categories/<int:pk>/edit/", views.category_update, name="category-update"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category-delete"),

    # Team
    path("team/", views.users, name="users"),
    path("team/<int:pk>/archive/", views.user_archive, name="user-archive"),
    path("team/<int:pk>/password/", views.user_password, name="user-password"),

    # Coupons & Promotions
    path("coupons/", views.coupons, name="coupons"),
    path("coupons/add/", views.coupon_create, name="coupon-create"),
    path("coupons/<int:pk>/edit/", views.coupon_update, name="coupon-update"),
    path("coupons/<int:pk>/delete/", views.coupon_delete, name="coupon-delete"),
    path("coupons/<int:pk>/toggle/", views.coupon_toggle, name="coupon-toggle"),
    path("promotions/add/", views.promotion_create, name="promotion-create"),
    path("promotions/<int:pk>/edit/", views.promotion_update, name="promotion-update"),
    path("promotions/<int:pk>/delete/", views.promotion_delete, name="promotion-delete"),
    path("promotions/<int:pk>/toggle/", views.promotion_toggle, name="promotion-toggle"),

    # Payment settings
    path("payment-methods/", views.payment_settings, name="payment-methods"),

    # Receipts
    path("receipts/", views.receipt_settings, name="receipts"),
    path("receipts/preview/", views.receipt_preview, name="receipt-preview"),
    path("receipts/test/", views.receipt_test, name="receipt-test"),

    # Customize & audit
    path("customize/", views.customize, name="customize"),
    path("audit/", views.audit_log, name="audit-log"),

    # Deferred POS modules
    path("pos/", views.coming_soon, name="pos-session"),
    path("kds/", views.coming_soon, name="kds"),
    path("reports/", views.coming_soon, name="reports"),
    path("bookings/", views.coming_soon, name="bookings"),
]
