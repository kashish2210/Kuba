from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from tenants.middleware import split_host

from .kds import current_kds_tickets, kds_group_name


class KDSConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.cafe = await self._resolve_cafe()
        user = self.scope.get("user")
        if self.cafe is None or user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.group_name = kds_group_name(self.cafe.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "event": "snapshot",
            "orders": await database_sync_to_async(current_kds_tickets)(self.cafe),
        })

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def kds_order(self, event):
        await self.send_json({
            "event": event["event"],
            "order": event["order"],
        })

    @database_sync_to_async
    def _resolve_cafe(self):
        from tenants.models import Cafe

        headers = dict(self.scope.get("headers") or [])
        host = headers.get(b"host", b"").decode("ascii", errors="ignore").split(":", 1)[0]
        subdomain, base = split_host(host)
        if subdomain:
            return Cafe.objects.filter(subdomain=subdomain, is_active=True).first()
        if base is None and host:
            return Cafe.objects.filter(custom_domain=host, is_active=True).first()
        return None
