import asyncio
import json
import time

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from redis.exceptions import RedisError

from .auth import authenticate, bearer, rate_limit
from .events import audit_connection, event_for, groups_for, join, leave


class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.heartbeat_task = None
        self.groups_joined = ()
        headers = {key.decode('latin1').lower(): value.decode('latin1') for key, value in self.scope['headers']}
        protocols = self.scope.get('subprotocols', [])
        tokens = [value[7:] for value in protocols if value.startswith('bearer.')]
        self.access = bearer(headers) or (tokens[0] if len(tokens) == 1 else None)
        self.user = await authenticate(self.access)
        if self.user is None:
            await self.close(code=4401)
            return
        client = self.scope.get('client') or ('', 0)
        meta = {'REMOTE_ADDR': client[0]}
        if 'x-forwarded-for' in headers:
            meta['HTTP_X_FORWARDED_FOR'] = headers['x-forwarded-for']
        if await rate_limit(self.user, meta=meta):
            await self.close(code=4429)
            return
        if not settings.REALTIME_ENABLED:
            await self.close(code=1013)
            return
        self.groups_joined = groups_for(self.user)
        try:
            await join(self.channel_layer, self.channel_name, self.groups_joined)
            await audit_connection(self.user, client[0])
        except (RedisError, OSError, TimeoutError):
            await self.close(code=1013)
            return
        await self.accept(subprotocol='datapulse' if 'datapulse' in protocols else None)
        await self.send_json({'event': 'conexion.lista'})
        self.last_ping = 0
        self.heartbeat_task = asyncio.create_task(self.heartbeat())

    async def authorized(self):
        self.user = await authenticate(self.access)
        if self.user is None:
            await self.close(code=4401)
            return False
        return True

    async def heartbeat(self):
        try:
            while True:
                await asyncio.sleep(settings.REALTIME_HEARTBEAT)
                if not await self.authorized():
                    return
                await join(self.channel_layer, self.channel_name, self.groups_joined)
                await self.send_json({'event': 'ping'})
        except (RedisError, OSError, TimeoutError):
            await self.close(code=1013)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        try:
            content = json.loads(text_data) if text_data and len(text_data) <= 4096 else None
        except ValueError:
            content = None
        if content != {'accion': 'ping'}:
            await self.close(code=4400)
            return
        if time.monotonic() - self.last_ping < 1:
            await self.close(code=4429)
            return
        self.last_ping = time.monotonic()
        if await self.authorized():
            await self.send_json({'event': 'pong'})

    async def realtime_event(self, event):
        if await self.authorized():
            data = await event_for(self.user, event)
            if data:
                await self.send_json(data)

    async def disconnect(self, code):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        if self.groups_joined:
            await leave(self.channel_layer, self.channel_name, self.groups_joined)
