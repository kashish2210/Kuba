from django.urls import path

from . import views

app_name = "pos"

urlpatterns = [
    path("", views.terminal, name="terminal"),
    path("kds/", views.kds_display, name="kds"),
    path("session/open/", views.session_open, name="session-open"),
    path("session/close/", views.session_close, name="session-close"),
    path("tables/", views.tables, name="tables"),

    path("orders/", views.orders_page, name="orders"),
    path("orders/data/", views.orders_data, name="orders-data"),
    path("order/start/", views.order_start, name="order-start"),
    path("order/<int:pk>/", views.order_detail, name="order-detail"),
    path("order/<int:pk>/line/", views.order_add_line, name="order-add-line"),
    path("order/<int:pk>/line/<int:lid>/", views.order_update_line, name="order-update-line"),
    path("order/<int:pk>/discount/", views.order_discount, name="order-discount"),
    path("order/<int:pk>/customer/", views.order_customer, name="order-customer"),
    path("order/<int:pk>/send-kitchen/", views.order_send_kitchen, name="order-send-kitchen"),
    path("order/<int:pk>/pay/", views.order_pay, name="order-pay"),
    path("order/<int:pk>/email-receipt/", views.order_email_receipt, name="order-email-receipt"),
    path("order/<int:pk>/razorpay/create/", views.order_razorpay_create, name="order-razorpay-create"),
    path("order/<int:pk>/razorpay/verify/", views.order_razorpay_verify, name="order-razorpay-verify"),
    path("order/<int:pk>/upi-qr/", views.order_upi_qr, name="order-upi-qr"),
    path("order/<int:pk>/cancel/", views.order_cancel, name="order-cancel"),

    # Customer endpoints
    path("customers/", views.customer_list, name="customer-list"),
    path("customers/create/", views.customer_create_update, name="customer-create"),
    path("customers/<int:pk>/edit/", views.customer_create_update, name="customer-edit"),
    path("customers/<int:pk>/delete/", views.customer_delete, name="customer-delete"),
    path("order/<int:pk>/line/<int:lid>/kds-status/", views.kds_update_line_status, name="kds-update-line-status"),
]
