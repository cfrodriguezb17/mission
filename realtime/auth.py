import math

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from rest_framework.exceptions import APIException
from rest_framework.throttling import UserRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication


def bearer(headers):
    value = headers.get('authorization', '')
    parts = value.split()
    return parts[1] if len(parts) == 2 and parts[0].lower() == 'bearer' else None


@database_sync_to_async
def authenticate(access):
    if not access:
        return None
    try:
        backend = JWTAuthentication()
        return backend.get_user(backend.get_validated_token(access))
    except APIException:
        return None


@database_sync_to_async
def rate_limit(user, *, meta):
    request = HttpRequest()
    request.user = user or AnonymousUser()
    request.META = meta
    throttle = UserRateThrottle()
    if not throttle.allow_request(request, None):
        return max(1, math.ceil(throttle.wait() or 1))
    return None
