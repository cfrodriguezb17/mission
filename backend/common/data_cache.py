"""Solo datos compartidos; autenticación, throttling y auditoría siguen activos."""
import hashlib
import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from django.db import connections, transaction
from redis.exceptions import RedisError
from rest_framework.response import Response

logger = logging.getLogger(__name__)
MISSING = object()


def data_response(data):
    return Response(data, headers={'Cache-Control': 'private, no-store', 'Vary': 'Authorization'})


def shared_data(key, factory):
    # Nunca publicar una lectura de una transacción que aún podría revertirse.
    if not settings.DATA_CACHE_ENABLED or not settings.DATA_CACHE_TTL or connections['default'].in_atomic_block:
        return factory()
    cache = caches['data']
    try:
        generation = cache.get_or_set('generation', lambda: uuid.uuid4().hex, timeout=None)
        digest = hashlib.sha256(key.encode()).hexdigest()
        cache_key = f'v1:{generation}:{digest}'
        cached = cache.get(cache_key, MISSING)
        if cached is not MISSING:
            return cached
    except (RedisError, OSError):
        logger.warning('Caché compartida no disponible; consultar PostgreSQL.')
        return factory()
    data = factory()
    try:
        cache.set(cache_key, data, timeout=settings.DATA_CACHE_TTL)
    except (RedisError, OSError):
        logger.warning('No se pudo guardar la caché compartida.')
    return data


def invalidate_shared_data(*, using='default'):
    if not settings.DATA_CACHE_ENABLED:
        return

    def invalidate():
        try:
            caches['data'].set('generation', uuid.uuid4().hex, timeout=None)
        except (RedisError, OSError):
            logger.warning('No se pudo invalidar la caché; las entradas caducarán por TTL.')

    transaction.on_commit(invalidate, using=using)


class SharedDataListMixin:
    def list(self, request, *args, **kwargs):
        if request.accepted_renderer.format != 'json':
            return super().list(request, *args, **kwargs)
        key = f'{type(self).__name__}:{request.build_absolute_uri()}'
        data = shared_data(key, lambda: super(SharedDataListMixin, self).list(request, *args, **kwargs).data)
        return data_response(data)
