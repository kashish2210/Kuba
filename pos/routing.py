from django.urls import path

from .consumers import KDSConsumer


websocket_urlpatterns = [
    path("ws/kds/", KDSConsumer.as_asgi()),
]
