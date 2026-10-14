"""HTTP, SSE y WebSockets reales, con Redis y PostgreSQL temporales."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import gzip
import http.client
from io import StringIO
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from redislite import Redis
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import AccessToken
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from alerts.models import Alerta
from audit.models import LogActividad
from countries.models import Pais


class UvicornRealtimeTests(TransactionTestCase):
    origin = 'http://localhost:4200'

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='mission-uvicorn-test-')
        self.folder = Path(self.scratch.name)
        self.addCleanup(self.scratch.cleanup)
        self.redis = Redis(str(self.folder / 'redis.db'))
        self.addCleanup(self.redis.shutdown)
        url = 'unix://' + self.redis.socket_file
        self.prefix = 'realtime-test:' + uuid.uuid4().hex
        layers = {'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer', 'CONFIG': {
            'hosts': [url], 'prefix': self.prefix, 'group_expiry': 60, 'expiry': 60}}}
        self.override = override_settings(REALTIME_ENABLED=True, CHANNEL_LAYERS=layers)
        self.override.enable()
        self.addCleanup(self.override.disable)
        call_command('seed_countries', stdout=StringIO())
        User = get_user_model()
        self.owner = User.objects.create_user(email='rt-owner@example.com', nombre_completo='Owner', rol='ANALISTA')
        self.other = User.objects.create_user(email='rt-other@example.com', nombre_completo='Other', rol='ANALISTA')
        self.viewer = User.objects.create_user(email='rt-viewer@example.com', nombre_completo='Viewer', rol='VIEWER')
        self.secret = 'test-only-' + uuid.uuid4().hex
        self.encoder = TokenBackend(algorithm='HS256', signing_key=self.secret)
        self.access = self.token(self.owner)
        config = connection.settings_dict
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        heartbeat = 15 if self._testMethodName == 'test_idle_connections_survive_blocking_redis_reads' else 0.2
        source = f'from backend.settings import *\nREALTIME_HEARTBEAT = {heartbeat}\n'
        if self._testMethodName == 'test_static_files_under_asgi':
            static_root = self.folder / 'static'
            static_root.mkdir()
            self.css = b'body { color: blue; }\n' * 50
            (static_root / 'test.css').write_bytes(self.css)
            (static_root / 'test.css.gz').write_bytes(gzip.compress(self.css))
            source += f'STATIC_ROOT = {str(static_root)!r}\n'
        (self.folder / 'uvicorn_test_settings.py').write_text(source)
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'uvicorn_test_settings',
               'PYTHONPATH': str(self.folder) + os.pathsep + str(settings.BASE_DIR),
               'POSTGRES_DB': config['NAME'], 'POSTGRES_USER': config['USER'],
               'POSTGRES_PASSWORD': config['PASSWORD'], 'POSTGRES_HOST': config['HOST'],
               'POSTGRES_PORT': str(config['PORT']), 'DJANGO_SECRET_KEY': self.secret,
               'DJANGO_DEBUG': 'false', 'DJANGO_ALLOWED_HOSTS': '127.0.0.1',
               'DJANGO_SECURE_SSL_REDIRECT': 'false', 'CORS_ALLOWED_ORIGINS': self.origin,
               'DJANGO_DB_CONN_MAX_AGE': '0', 'DJANGO_DB_POOL': 'true',
               'DJANGO_DB_POOL_MIN_SIZE': '1', 'DJANGO_DB_POOL_MAX_SIZE': '4',
               'DJANGO_DB_PREPARE_THRESHOLD': '2',
               'DJANGO_ASGI_SYNC_REST': 'true',
               'DJANGO_REALTIME_REDIS_URL': url, 'DJANGO_REALTIME_PREFIX': self.prefix,
               'DJANGO_REDIS_URL': url, 'DJANGO_DATA_CACHE_PREFIX': self.prefix + ':data',
               'DJANGO_CACHE_LOCATION': str(self.folder / 'cache')}
        if self._testMethodName == 'test_missing_redis_keeps_summary_available':
            env.update(DJANGO_REALTIME_REDIS_URL='', DJANGO_REDIS_URL='')
        if self._testMethodName == 'test_rollback_mode_preserves_http_and_realtime':
            env['DJANGO_ASGI_SYNC_REST'] = 'false'
        self.log = (self.folder / 'server.log').open('w')
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen([
            sys.executable, '-m', 'uvicorn', 'backend.asgi:application', '--host', '127.0.0.1',
            '--port', str(self.port), '--workers', '2', '--loop', 'uvloop', '--http', 'httptools',
            '--lifespan', 'off', '--no-proxy-headers', '--ws-max-size', '16384'],
            cwd=settings.BASE_DIR, env=env, stdout=self.log, stderr=self.log, start_new_session=True)
        self.addCleanup(self.stop_server)
        deadline = time.monotonic() + 20
        while True:
            try:
                if self.http('/health/', token=None)[0] == 200:
                    break
            except OSError:
                pass
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.fail('Uvicorn no arrancó: ' + (self.folder / 'server.log').read_text()[-3000:])
            time.sleep(.1)

    def stop_server(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()

    def token(self, user, expired=False):
        access = AccessToken.for_user(user)
        if expired:
            access.set_exp(lifetime=timedelta(seconds=-1))
        return self.encoder.encode(access.payload)

    def http(self, path, *, token='default', method='GET', body=None, raw=False):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {}
        token = self.access if token == 'default' else token
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if body is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(body)
        try:
            client.request(method, path, body=body, headers=headers)
            response = client.getresponse()
            data = response.read()
            return response.status, data if raw else json.loads(data)
        finally:
            client.close()

    def websocket(self, token='default', origin=None):
        token = self.access if token == 'default' else token
        protocols = ['datapulse', 'bearer.' + token] if token else ['datapulse']
        return connect(f'ws://127.0.0.1:{self.port}/ws/notificaciones/', subprotocols=protocols,
                       origin=origin or self.origin, proxy=None, open_timeout=5)

    def next_ws(self, ws, event, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = json.loads(ws.recv(timeout=max(.01, deadline - time.monotonic())))
            except TimeoutError:
                return None
            if data['event'] == event:
                return data
        return None

    def alert(self, user=None):
        return Alerta.objects.create(pais_id='CO', usuario=user, tipo_alerta='RIESGO',
                                     severidad='WARNING', titulo='Prueba', mensaje='Dato privado')

    def sse(self, token='default'):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        token = self.access if token == 'default' else token
        client.request('GET', '/api/realtime/stream/', headers={'Authorization': 'Bearer ' + token})
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'text/event-stream')
        self.assertEqual(response.getheader('X-Accel-Buffering'), 'no')
        self.addCleanup(client.close)
        return client, response

    def next_sse(self, response, event, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = None
            while True:
                line = response.readline()
                if not line:
                    return None
                if line.startswith(b'data: '):
                    data = json.loads(line[6:])
                if line == b'\n':
                    break
            if data and data['event'] == event:
                return data
        return None

    def test_async_summary_authentication_privacy_audit_and_method(self):
        self.alert(self.owner)
        self.assertEqual(self.http('/api/realtime/resumen/'),
                         (200, {'alertas_no_leidas': 1, 'paises_activos': 10}))
        self.assertEqual(self.http('/api/realtime/resumen/', token=self.token(self.other))[1]['alertas_no_leidas'], 0)
        self.assertEqual(self.http('/api/realtime/resumen/', token=None)[0], 401)
        self.assertEqual(self.http('/api/realtime/resumen/', token=self.token(self.owner, expired=True))[0], 401)
        self.assertEqual(self.http('/api/realtime/resumen/', method='POST')[0], 405)
        self.assertTrue(LogActividad.objects.filter(usuario=self.owner, entidad_afectada='Realtime').exists())

    def test_websocket_private_and_global_events_cross_process(self):
        with self.websocket() as owner, self.websocket(self.token(self.other)) as other:
            self.assertIsNotNone(self.next_ws(owner, 'conexion.lista'))
            self.assertIsNotNone(self.next_ws(other, 'conexion.lista'))
            self.assertEqual(owner.subprotocol, 'datapulse')
            private = self.alert(self.owner)
            self.assertEqual(self.next_ws(owner, 'alerta.creada')['id'], private.pk)
            self.assertIsNone(self.next_ws(other, 'alerta.creada', timeout=.35))
            public = self.alert()
            self.assertEqual(self.next_ws(owner, 'alerta.creada')['id'], public.pk)
            self.assertEqual(self.next_ws(other, 'alerta.creada')['id'], public.pk)
            owner.send(json.dumps({'accion': 'ping'}))
            self.assertIsNotNone(self.next_ws(owner, 'pong'))

    def test_websocket_rejects_missing_invalid_expired_tokens_and_wrong_origin(self):
        for token, origin in ((None, None), ('invalid', None),
                              (self.token(self.owner, expired=True), None),
                              (self.access, 'https://untrusted.example')):
            with self.subTest(origin=origin), self.assertRaises(InvalidStatus):
                self.websocket(token, origin)

    def test_websocket_revalidates_disabled_user_and_password_change(self):
        for field, value in (('is_active', False), ('password', 'revoked')):
            self.owner.is_active = True
            self.owner.set_unusable_password()
            self.owner.save()
            access = self.token(self.owner)
            with self.websocket(access) as ws:
                self.assertIsNotNone(self.next_ws(ws, 'conexion.lista'))
                setattr(self.owner, field, value)
                self.owner.save(update_fields=[field])
                with self.assertRaises(ConnectionClosed):
                    while True:
                        ws.recv(timeout=3)
                self.assertEqual(ws.close_code, 4401)

    def test_websocket_rejects_invalid_messages_and_excessive_pings(self):
        for message in ('not-json', '{"accion":"escribir"}', b'binary'):
            with self.subTest(message=message), self.websocket() as ws:
                self.next_ws(ws, 'conexion.lista')
                ws.send(message)
                with self.assertRaises(ConnectionClosed):
                    while True:
                        ws.recv(timeout=3)
                self.assertEqual(ws.close_code, 4400)
        with self.websocket() as ws:
            self.next_ws(ws, 'conexion.lista')
            ws.send('{"accion":"ping"}')
            self.assertIsNotNone(self.next_ws(ws, 'pong'))
            ws.send('{"accion":"ping"}')
            with self.assertRaises(ConnectionClosed):
                while True:
                    ws.recv(timeout=3)
            self.assertEqual(ws.close_code, 4429)

    def test_redis_outage_preserves_database_writes_and_normal_http(self):
        self.redis.shutdown()
        with self.assertLogs('realtime.events', level='WARNING'):
            alert = self.alert(self.owner)
        self.assertTrue(Alerta.objects.filter(pk=alert.pk).exists())
        self.assertEqual(self.http('/api/realtime/resumen/')[0], 200)
        self.assertEqual(self.http('/api/realtime/stream/')[0], 503)
        with self.assertRaises(InvalidStatus):
            self.websocket()

    def test_idle_connections_survive_blocking_redis_reads(self):
        with self.websocket() as ws:
            self.next_ws(ws, 'conexion.lista')
            client, response = self.sse()
            self.next_sse(response, 'conexion.lista')
            time.sleep(6)
            alert = self.alert(self.owner)
            self.assertEqual(self.next_ws(ws, 'alerta.creada')['id'], alert.pk)
            self.assertEqual(self.next_sse(response, 'alerta.creada')['id'], alert.pk)
            client.close()

    def test_missing_redis_keeps_summary_available(self):
        self.assertEqual(self.http('/api/realtime/resumen/')[0], 200)
        self.assertEqual(self.http('/api/realtime/stream/')[0], 503)
        self.assertEqual(self.http('/api/realtime/stream/', token=None)[0], 401)
        self.assertEqual(self.http('/api/realtime/stream/', method='POST')[0], 405)
        with self.assertRaises(InvalidStatus):
            self.websocket()

    def test_commit_and_rollback_only_publish_committed_alerts(self):
        with self.websocket() as ws:
            self.next_ws(ws, 'conexion.lista')
            with transaction.atomic():
                alert = self.alert(self.owner)
                self.assertIsNone(self.next_ws(ws, 'alerta.creada', timeout=.3))
            self.assertEqual(self.next_ws(ws, 'alerta.creada')['id'], alert.pk)
            try:
                with transaction.atomic():
                    self.alert(self.owner)
                    raise RuntimeError('rollback')
            except RuntimeError:
                pass
            self.assertIsNone(self.next_ws(ws, 'alerta.creada', timeout=.3))

    def test_stream_delivers_events_incrementally_and_closes_after_revocation(self):
        client, response = self.sse()
        self.assertIsNotNone(self.next_sse(response, 'conexion.lista'))
        alert = self.alert(self.owner)
        self.assertEqual(self.next_sse(response, 'alerta.creada')['id'], alert.pk)
        self.owner.is_active = False
        self.owner.save(update_fields=['is_active'])
        self.assertIsNotNone(self.next_sse(response, 'autenticacion.expirada'))
        client.close()
        self.assertEqual(self.http('/api/realtime/stream/', token=self.access)[0], 401)

    def test_stream_privacy_and_dashboard_notifications(self):
        client, response = self.sse(self.token(self.other))
        self.next_sse(response, 'conexion.lista')
        self.alert(self.owner)
        self.assertIsNone(self.next_sse(response, 'alerta.creada', timeout=.3))
        country = Pais.objects.get(pk='CO')
        country.poblacion += 1
        country.save(update_fields=['poblacion'])
        self.assertIsNotNone(self.next_sse(response, 'dashboard.actualizado'))
        client.close()

    def test_existing_crud_concurrency_and_pdf_work_under_asgi(self):
        status, portfolio = self.http('/api/portafolios/', method='POST', body={'nombre': 'Concurrente', 'es_publico': True})
        self.assertEqual(status, 201)
        path = f"/api/portafolios/{portfolio['id']}/"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda name: self.http(path, method='PUT',
                body={'version': 1, 'nombre': name})[0], ('Cambio A', 'Cambio B')))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.http(path)[1]['version'], 2)
        status, pdf = self.http(path + 'export/pdf/', raw=True)
        self.assertEqual(status, 200)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(self.http('/api/portafolios/', token=self.token(self.viewer),
                                   method='POST', body={'nombre': 'Prohibido'})[0], 403)

    def test_auth_profile_and_error_contracts_with_synchronous_api_under_asgi(self):
        self.owner.set_password('Initial-password-2026!')
        self.owner.save(update_fields=['password'])
        status, tokens = self.http('/api/auth/login/', method='POST', token=None,
            body={'email': self.owner.email, 'password': 'Initial-password-2026!'})
        self.assertEqual(status, 200)
        access = tokens['access']
        self.assertEqual(self.http('/api/auth/me/', token=access)[1]['email'], self.owner.email)
        self.assertEqual(self.http('/api/auth/me/', token=access, method='PUT',
                                  body={'email': self.owner.email})[0], 400)
        self.assertEqual(self.http('/api/not-a-real-endpoint/', token=access)[0], 404)
        self.assertEqual(self.http('/api/paises/', token=access, method='DELETE')[0], 405)
        self.assertEqual(self.http('/api/auth/me/', token=access, method='PUT', body={
            'email': self.owner.email, 'nombre_completo': 'Nombre actualizado',
            'password': 'Replacement-password-2026!'})[0], 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.nombre_completo, 'Nombre actualizado')
        self.assertEqual(self.http('/api/auth/me/', token=access)[0], 401)

    def test_rollback_mode_preserves_http_and_realtime(self):
        self.assertEqual(self.http('/api/paises/')[0], 200)
        self.assertEqual(self.http('/api/realtime/resumen/')[0], 200)
        with self.websocket() as ws:
            self.next_ws(ws, 'conexion.lista')
            client, response = self.sse()
            self.next_sse(response, 'conexion.lista')
            alert = self.alert(self.owner)
            self.assertEqual(self.next_ws(ws, 'alerta.creada')['id'], alert.pk)
            self.assertEqual(self.next_sse(response, 'alerta.creada')['id'], alert.pk)
            client.close()

    def test_static_files_under_asgi(self):
        for method, headers, expected_status in (
            ('GET', {}, 200), ('HEAD', {}, 200),
            ('GET', {'Range': 'bytes=0-3'}, 206),
            ('GET', {'Accept-Encoding': 'gzip'}, 200)):
            with self.subTest(method=method, headers=headers):
                client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
                try:
                    client.request(method, '/static/test.css', headers=headers)
                    response = client.getresponse()
                    body = response.read()
                    self.assertEqual(response.status, expected_status)
                    self.assertIn('public', response.getheader('Cache-Control'))
                    if method == 'HEAD':
                        self.assertEqual(body, b'')
                    elif 'Range' in headers:
                        self.assertEqual(body, self.css[:4])
                    elif 'Accept-Encoding' in headers:
                        self.assertEqual(response.getheader('Content-Encoding'), 'gzip')
                        self.assertEqual(gzip.decompress(body), self.css)
                    else:
                        self.assertEqual(body, self.css)
                finally:
                    client.close()
