"""Avisos de refresco; los datos y permisos siguen en PostgreSQL."""
import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from redis.exceptions import RedisError

from alerts.selectors import alertas_visibles
from audit.services import registrar_actividad

logger = logging.getLogger(__name__)


def groups_for(user):
    return ('alerts.global', f'alerts.user.{user.pk}', 'dashboard')


async def join(layer, channel, groups):
    for group in groups:
        await asyncio.wait_for(layer.group_add(group, channel), timeout=2)


async def leave(layer, channel, groups):
    for group in groups:
        try:
            await asyncio.wait_for(layer.group_discard(group, channel), timeout=1)
        except (RedisError, OSError, TimeoutError):
            pass  # El grupo caduca aunque el cliente pierda la conexión.


@database_sync_to_async
def event_for(user, event):
    if event.get('kind') == 'alert':
        pk = event.get('id')
        if alertas_visibles(user).filter(pk=pk).exists():
            return {'event': 'alerta.creada', 'id': pk}
    elif event.get('kind') == 'dashboard':
        return {'event': 'dashboard.actualizado'}
    return None


@database_sync_to_async
def audit_connection(user, ip):
    registrar_actividad(usuario=user, accion='CONSULTAR', entidad='Realtime', ip=ip,
                        detalle={'operacion': 'consulta', 'origen': 'HTTP'})


def publish(group, event, *, using='default'):
    if not settings.REALTIME_ENABLED:
        return

    async def send():
        await asyncio.wait_for(get_channel_layer().group_send(group, {
            'type': 'realtime.event', **event}), timeout=2)

    def committed():
        try:
            async_to_sync(send)()
        except (RedisError, OSError, TimeoutError):
            logger.warning('No se pudo publicar el aviso; los datos permanecen guardados.')

    transaction.on_commit(committed, using=using)
