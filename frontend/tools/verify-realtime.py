"""Prueba Angular → Uvicorn (2 workers) → Redis/PostgreSQL en recursos temporales.

Ejecutar con ../backend/.venv/bin/python tools/verify-realtime.py desde frontend.
No modifica la base principal ni utiliza servicios HTTP existentes.
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

FRONTEND = Path(__file__).resolve().parents[1]
BACKEND = FRONTEND.parent / 'backend'
OUTPUT = FRONTEND / 'output/realtime'


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def wait_http(url, process, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('El servidor terminó antes de estar disponible.')
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(.2)
    raise TimeoutError('El servidor no respondió dentro del plazo.')


def main():
    import psycopg
    from psycopg import sql
    from redislite import Redis
    OUTPUT.mkdir(parents=True, exist_ok=True)
    backend_process = frontend_process = browser_process = None
    with tempfile.TemporaryDirectory(prefix='mission-browser-realtime-') as temporary:
        scratch = Path(temporary)
        redis = Redis(str(scratch / 'redis.db'))
        db_name = 'datapulse_browser_' + uuid.uuid4().hex[:12]
        backend_port, frontend_port = free_port(), free_port()
        while frontend_port == backend_port:
            frontend_port = free_port()
        origin = f'http://localhost:{frontend_port}'
        overrides = {
            'DJANGO_SETTINGS_MODULE': 'backend.settings',
            'DJANGO_SECRET_KEY': 'test-only-' + uuid.uuid4().hex,
            'DJANGO_DEBUG': 'false', 'DJANGO_ALLOWED_HOSTS': '127.0.0.1,localhost',
            'DJANGO_SECURE_SSL_REDIRECT': 'false', 'DJANGO_TRUST_PROXY': 'false',
            'CORS_ALLOWED_ORIGINS': origin, 'DJANGO_DB_CONN_MAX_AGE': '0',
            'DJANGO_DB_POOL': 'true', 'DJANGO_DB_POOL_MIN_SIZE': '1',
            'DJANGO_DB_POOL_MAX_SIZE': '4', 'DJANGO_DB_PREPARE_THRESHOLD': '5',
            'DJANGO_REDIS_URL': 'unix://' + redis.socket_file,
            'DJANGO_REALTIME_REDIS_URL': 'unix://' + redis.socket_file,
            'DJANGO_DATA_CACHE_PREFIX': db_name, 'DJANGO_REALTIME_PREFIX': db_name,
            'DJANGO_CACHE_LOCATION': str(scratch / 'cache'),
            'DJANGO_ASGI_SYNC_REST': 'true',
        }
        os.environ.update(overrides)
        sys.path.insert(0, str(BACKEND))
        import django
        django.setup()
        from django.conf import settings
        from django.db import connection
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from risk.models import IndiceRiesgo
        from alerts.services import generar_para_indice

        config = settings.DATABASES['default']
        original_name = config['NAME']
        credentials = {key: config[field] for key, field in (
            ('user', 'USER'), ('password', 'PASSWORD'), ('host', 'HOST'), ('port', 'PORT'))}
        env = {**os.environ, 'POSTGRES_DB': db_name}
        for field in ('USER', 'PASSWORD', 'HOST', 'PORT'):
            env['POSTGRES_' + field] = str(config[field])
        password = 'Live-' + uuid.uuid4().hex + '!'
        email = 'realtime@example.com'
        def index(value):
            return IndiceRiesgo.objects.create(
                pais_id='CO', indice_compuesto=value, score_economico=value,
                score_cambiario=value, score_estabilidad=value,
                version_formula='browser-test', detalle_calculo={},
                fecha_alertas_procesadas=timezone.now() if value == 30 else None)
        with (OUTPUT / 'live-servers.log').open('w') as server_log, (OUTPUT / 'live-browser.log').open('w') as browser_log:
            try:
                with psycopg.connect(dbname='postgres', autocommit=True, **credentials) as maintenance:
                    maintenance.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db_name)))
                    try:
                        for command in (('migrate', '--noinput'), ('seed_economics',)):
                            subprocess.run([sys.executable, 'manage.py', *command], cwd=BACKEND,
                                           env=env, stdout=server_log, stderr=server_log, check=True, timeout=90)
                        connection.close()
                        connection.close_pool()
                        config['NAME'] = db_name
                        get_user_model().objects.create_user(email=email, password=password,
                            nombre_completo='Prueba de tiempo real', rol='ANALISTA')
                        index(30)
                        def start_backend():
                            nonlocal backend_process
                            process = subprocess.Popen([sys.executable, '-m', 'uvicorn',
                                'backend.asgi:application', '--host', '127.0.0.1', '--port', str(backend_port),
                                '--workers', '2', '--lifespan', 'off', '--no-proxy-headers'],
                                cwd=BACKEND, env=env, stdout=server_log, stderr=server_log, start_new_session=True)
                            backend_process = process
                            wait_http(f'http://127.0.0.1:{backend_port}/health/', process)
                            return process
                        backend_process = start_backend()
                        proxy = scratch / 'proxy.json'
                        proxy.write_text(json.dumps({'^' + path + '/': {'target': f'http://127.0.0.1:{backend_port}',
                            'secure': False, 'changeOrigin': True, **({'ws': True} if path == '/ws' else {})}
                            for path in ('/api', '/ws')}))
                        frontend_process = subprocess.Popen(['pnpm', 'exec', 'ng', 'serve',
                            '--configuration', 'production', '--host', '127.0.0.1', '--port', str(frontend_port),
                            '--proxy-config', str(proxy)], cwd=FRONTEND, stdout=server_log,
                            stderr=server_log, start_new_session=True)
                        wait_http(origin + '/login', frontend_process)
                        browser_env = {**os.environ, 'E2E_BASE_URL': origin, 'REALTIME_LIVE_DIR': str(scratch),
                            'REALTIME_LIVE_EMAIL': email, 'REALTIME_LIVE_PASSWORD': password}
                        browser_process = subprocess.Popen(['pnpm', 'exec', 'playwright', 'test',
                            'e2e/realtime-live.spec.ts', '--output', str(scratch / 'browser-artifacts'),
                            '--reporter', 'list'], cwd=FRONTEND, env=browser_env,
                            stdout=browser_log, stderr=browser_log, start_new_session=True)
                        deadline = time.monotonic() + 150
                        handled = set()
                        while browser_process.poll() is None and time.monotonic() < deadline:
                            for phase, value in (('critical', 24), ('restart', 23)):
                                if phase not in handled and (scratch / phase).exists():
                                    handled.add(phase)
                                    if phase == 'restart':
                                        stop(backend_process)
                                    assert generar_para_indice(index(value).pk) == 1
                                    print(f'IRPC {value}: alerta creada' + (' sin consumidores conectados' if phase == 'restart' else ''), flush=True)
                                    if phase == 'restart':
                                        backend_process = start_backend()
                            time.sleep(.1)
                        if browser_process.poll() is None:
                            raise TimeoutError('El navegador superó el plazo de prueba.')
                        if browser_process.returncode:
                            raise RuntimeError('Falló la prueba; revisar output/realtime/live-browser.log')
                        result = json.loads((scratch / 'browser-result.json').read_text())
                        result.update(workers=2, database='PostgreSQL temporal', redis='Redis temporal')
                    finally:
                        for process in (browser_process, frontend_process, backend_process):
                            stop(process)
                        connection.close()
                        connection.close_pool()
                        config['NAME'] = original_name
                        maintenance.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(db_name)))
            finally:
                redis.shutdown()
        result.update(temporary_database_removed=True, temporary_services_stopped=True)
        (OUTPUT / 'live-result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
