from django.urls import path

from .consumers import KDSConsumer, LiveOrdersConsumer


websocket_urlpatterns = [
    path("ws/kds/", KDSConsumer.as_asgi()),
    path("ws/orders/", LiveOrdersConsumer.as_asgi()),
]
