"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

django_application = get_asgi_application()

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from realtime.consumers import NotificationsConsumer
from common.asgi import RoutedHTTPApplication
from common.admission import AdmissionControlledApplication

if settings.DATABASES['default']['CONN_MAX_AGE'] != 0:
    raise ImproperlyConfigured('ASGI requiere DJANGO_DB_CONN_MAX_AGE=0.')

origins = settings.CORS_ALLOWED_ORIGINS or (
    ['http://localhost:4200', 'http://127.0.0.1:4200'] if settings.DEBUG else [])
application = AdmissionControlledApplication(ProtocolTypeRouter({
    'http': RoutedHTTPApplication(django_application) if settings.ASGI_SYNC_REST else django_application,
    'websocket': OriginValidator(URLRouter([
        path('ws/notificaciones/', NotificationsConsumer.as_asgi()),
    ]), origins),
}), http_limit=settings.ASGI_HTTP_LIMIT, http_queue=settings.ASGI_HTTP_QUEUE,
   wait_seconds=settings.ASGI_ADMISSION_WAIT_MS / 1000,
   websocket_limit=settings.ASGI_WEBSOCKET_LIMIT, stream_limit=settings.ASGI_STREAM_LIMIT)
