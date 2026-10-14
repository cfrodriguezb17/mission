import asyncio
import json

from channels.layers import get_channel_layer
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from redis.exceptions import RedisError

from alerts.selectors import alertas_visibles
from common.exceptions import error_payload
from common.throttling import ThrottlingUnavailable
from countries.models import Pais
from .auth import authenticate, bearer, rate_limit
from .events import audit_connection, event_for, groups_for, join, leave


def error(status, **headers):
    return JsonResponse({'error': error_payload(status)}, status=status, headers=headers)


async def authorized(request):
    if request.method != 'GET':
        return None, error(405, Allow='GET')
    user = await authenticate(bearer(request.headers))
    if user is None:
        return None, error(401, **{'WWW-Authenticate': 'Bearer'})
    request.user = user
    try:
        wait = await rate_limit(user, meta=request.META)
    except ThrottlingUnavailable:
        return None, error(503, **{'Retry-After': '1'})
    if wait:
        return None, error(429, **{'Retry-After': str(wait)})
    return user, None


@csrf_exempt
async def resumen(request):
    user, failure = await authorized(request)
    if failure is not None:
        return failure
    data = {'alertas_no_leidas': await alertas_visibles(user).filter(leida=False).acount(),
            'paises_activos': await Pais.objects.filter(activo=True).acount()}
    await audit_connection(user, request.META.get('REMOTE_ADDR'))
    return JsonResponse(data, headers={'Cache-Control': 'private, no-store', 'Vary': 'Authorization'})


def frame(data):
    return f"event: {data['event']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@csrf_exempt
async def stream(request):
    user, failure = await authorized(request)
    if failure is not None:
        return failure
    if not settings.REALTIME_ENABLED:
        return error(503)
    layer = get_channel_layer()
    channel = await layer.new_channel()
    groups = groups_for(user)
    try:
        await join(layer, channel, groups)
        await audit_connection(user, request.META.get('REMOTE_ADDR'))
    except (RedisError, OSError, TimeoutError):
        await leave(layer, channel, groups)
        return error(503)
    access = bearer(request.headers)

    async def events():
        try:
            yield frame({'event': 'conexion.lista'})
            while True:
                try:
                    event = await asyncio.wait_for(layer.receive(channel), timeout=settings.REALTIME_HEARTBEAT)
                except TimeoutError:
                    event = None
                current_user = await authenticate(access)
                if current_user is None:
                    yield frame({'event': 'autenticacion.expirada'})
                    return
                await join(layer, channel, groups)
                data = await event_for(current_user, event) if event else {'event': 'ping'}
                if data:
                    yield frame(data)
        except (RedisError, OSError, TimeoutError):
            yield frame({'event': 'servicio.no_disponible'})
        finally:
            await leave(layer, channel, groups)

    return StreamingHttpResponse(events(), content_type='text/event-stream', headers={
        'Cache-Control': 'private, no-store', 'X-Accel-Buffering': 'no', 'Vary': 'Authorization'})
