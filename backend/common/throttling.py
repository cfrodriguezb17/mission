"""Shared normal operation; bounded local throttling during Redis outages."""
import logging
import threading
import time

from django.conf import settings
from django.core.cache import caches
from redis.exceptions import RedisError
from rest_framework.exceptions import APIException
from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
from rest_framework.throttling import UserRateThrottle as DRFUserRateThrottle

logger = logging.getLogger(__name__)
_retry_at = 0.0
_state_lock = threading.Lock()


class ThrottlingUnavailable(APIException):
    status_code = 503
    default_detail = 'El control de solicitudes no está disponible. Intente más tarde.'
    default_code = 'servicio_no_disponible'


class CacheFailureMixin:
    def local_request(self, request, view):
        self.cache = caches['throttle_fallback']
        key = self.get_cache_key(request, view)
        if key and self.cache.get(key) is None:
            recent = caches['throttle_shadow'].get(key)
            if recent is not None:
                self.cache.set(key, recent, self.duration)
        return super().allow_request(request, view)

    def allow_request(self, request, view):
        global _retry_at
        try:
            if settings.THROTTLE_REDIS and time.monotonic() < _retry_at:
                return self.local_request(request, view)
            try:
                allowed = super().allow_request(request, view)
            except (RedisError, OSError):
                with _state_lock:
                    _retry_at = time.monotonic() + 60
                logger.warning('Redis de throttling no disponible; usar límites locales durante 60 segundos.')
                return self.local_request(request, view)
            if settings.THROTTLE_REDIS and getattr(self, 'key', None):
                caches['throttle_shadow'].set(self.key, self.history, self.duration)
            return allowed
        except (RedisError, OSError) as exc:
            raise ThrottlingUnavailable() from exc


class UserRateThrottle(CacheFailureMixin, DRFUserRateThrottle):
    pass


class AnonRateThrottle(CacheFailureMixin, DRFAnonRateThrottle):
    pass
