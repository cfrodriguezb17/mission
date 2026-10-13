from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.core.management import call_command
from django.db import transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from redis.exceptions import ConnectionError
from redislite import Redis
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from alerts.models import Alerta, LecturaAlerta
from audit.models import LogActividad
from common.data_cache import shared_data
from countries.models import Moneda, Pais
from economics.models import IndicadorEconomico
from economics.services import cargar_catalogo
from portfolios.models import Portafolio
from risk.models import IndiceRiesgo


class DataCacheTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.scratch = tempfile.TemporaryDirectory(prefix='mission-cache-tests-')
        cls.redis = Redis(str(Path(cls.scratch.name) / 'redis.db'))
        cls.redis_url = 'unix://' + cls.redis.socket_file

    @classmethod
    def tearDownClass(cls):
        cls.redis.shutdown()
        cls.scratch.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.prefix = 'test-data:' + uuid.uuid4().hex
        self.override = override_settings(DATA_CACHE_ENABLED=True, DATA_CACHE_TTL=60, CACHES={
            **settings.CACHES, 'data': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                                      'LOCATION': self.redis_url, 'KEY_PREFIX': self.prefix}})
        self.override.enable()
        self.addCleanup(self.override.disable)
        call_command('seed_countries', stdout=StringIO())
        cargar_catalogo()
        User = get_user_model()
        self.user = User.objects.create_user(email='cache-user@example.com', nombre_completo='Lector', rol='VIEWER')
        self.other = User.objects.create_user(email='cache-other@example.com', nombre_completo='Otro', rol='VIEWER')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def index(self, value='80'):
        return IndiceRiesgo.objects.create(pais_id='CO', indice_compuesto=value, score_economico=value,
            score_cambiario=value, score_estabilidad=value, version_formula='test', detalle_calculo={})

    def test_hit_skips_country_queries_but_keeps_audit_and_authentication(self):
        first = self.api.get('/api/paises/').data
        with self.assertNumQueries(1):
            second = self.api.get('/api/paises/')
        self.assertEqual(second.data, first)
        self.assertEqual(second['Cache-Control'], 'private, no-store')
        self.assertEqual(LogActividad.objects.filter(accion='CONSULTAR', entidad_afectada='Pais').count(), 2)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get('/api/paises/').status_code, 401)

    def test_cached_data_never_bypasses_inactive_jwt_account(self):
        self.api.get('/api/paises/')
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccessToken.for_user(self.user)))
        self.assertEqual(api.get('/api/paises/').status_code, 200)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertEqual(api.get('/api/paises/').status_code, 401)

    def test_hit_keeps_throttle_active(self):
        for _ in range(100):
            self.assertEqual(self.api.get('/api/paises/').status_code, 200)
        self.assertEqual(self.api.get('/api/paises/').status_code, 429)

    def test_query_parameters_and_hosts_have_separate_cache_entries(self):
        for params in ({'page_size': 1}, {'page_size': 2}, {'region': 'ANDINA'}, {'search': 'Brasil'}):
            first = self.api.get('/api/paises/', params).data
            with self.assertNumQueries(1):
                self.assertEqual(self.api.get('/api/paises/', params).data, first)
        self.assertEqual(self.api.get('/api/paises/', {'ordering': 'password'}).status_code, 400)
        with override_settings(ALLOWED_HOSTS=['testserver', 'other.test']):
            first = self.api.get('/api/paises/', {'page_size': 1}).data
            other = self.api.get('/api/paises/', {'page_size': 1}, HTTP_HOST='other.test').data
            self.assertIn('testserver', first['next'])
            self.assertIn('other.test', other['next'])

    def test_html_keeps_pagination_controls_after_json_hit(self):
        for path in ('/api/paises/?page_size=1', '/api/dashboard/mapa/?page_size=1',
                     '/api/dashboard/tendencias/?page_size=1'):
            self.api.get(path)
            response = self.api.get(path, HTTP_ACCEPT='text/html')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'<ul class="pagination">', response.content)

    def test_country_and_currency_changes_invalidate_only_after_commit(self):
        self.api.get('/api/paises/')
        generation = caches['data'].get('generation')
        with transaction.atomic():
            country = Pais.objects.get(pk='CO')
            country.nombre = 'Colombia actualizada'
            country.save(update_fields=['nombre'])
            self.assertEqual(caches['data'].get('generation'), generation)
            # Tampoco se sirven entradas antiguas dentro de una transacción.
            rows = self.api.get('/api/paises/').data['results']
            self.assertIn('Colombia actualizada', [row['nombre'] for row in rows])
        self.assertNotEqual(caches['data'].get('generation'), generation)
        currency = Moneda.objects.get(pk='COP')
        currency.nombre = 'Peso actualizado'
        currency.save(update_fields=['nombre'])
        rows = self.api.get('/api/paises/').data['results']
        self.assertEqual(next(row for row in rows if row['codigo_iso'] == 'CO')['moneda_nombre'], 'Peso actualizado')

    def test_rollback_does_not_invalidate_or_publish_uncommitted_data(self):
        before = self.api.get('/api/paises/').data
        generation = caches['data'].get('generation')
        try:
            with transaction.atomic():
                country = Pais.objects.get(pk='CO')
                country.activo = False
                country.save(update_fields=['activo'])
                self.assertEqual(self.api.get('/api/paises/').data['count'], 9)
                raise RuntimeError('rollback')
        except RuntimeError:
            pass
        self.assertEqual(caches['data'].get('generation'), generation)
        self.assertEqual(self.api.get('/api/paises/').data, before)

    def test_dashboard_keeps_user_counts_and_read_state_fresh(self):
        self.index()
        Portafolio.objects.create(usuario=self.user, nombre='Propio')
        alert = Alerta.objects.create(usuario=self.user, pais_id='CO', tipo_alerta='RIESGO',
                                      severidad='WARNING', titulo='Privada', mensaje='Prueba')
        first = self.api.get('/api/dashboard/resumen/').data
        self.assertEqual((first['portafolios_usuario'], first['alertas_activas']), (1, 1))
        with self.assertNumQueries(3):  # dos conteos privados y auditoría
            self.assertEqual(self.api.get('/api/dashboard/resumen/').data, first)
        self.api.force_authenticate(self.other)
        other = self.api.get('/api/dashboard/resumen/').data
        self.assertEqual((other['portafolios_usuario'], other['alertas_activas']), (0, 0))
        LecturaAlerta.objects.create(usuario=self.user, alerta=alert)
        Portafolio.objects.create(usuario=self.user, nombre='Nuevo')
        self.api.force_authenticate(self.user)
        data = self.api.get('/api/dashboard/resumen/').data
        self.assertEqual((data['portafolios_usuario'], data['alertas_activas']), (2, 0))

    def test_map_and_summary_refresh_after_risk_save_and_delete(self):
        index = self.index()
        for path in ('/api/dashboard/mapa/', '/api/dashboard/resumen/'):
            self.api.get(path)
        index.indice_compuesto = '0'
        index.save(update_fields=['indice_compuesto'])
        rows = self.api.get('/api/dashboard/mapa/').data['results']
        self.assertEqual(next(row for row in rows if row['codigo_iso'] == 'CO')['indice_compuesto'], '0.00')
        self.assertEqual(self.api.get('/api/dashboard/resumen/').data['promedio_irpc'], '0.00')
        index.delete()
        self.assertIsNone(self.api.get('/api/dashboard/resumen/').data['promedio_irpc'])

    def test_trends_refresh_after_indicator_change(self):
        row = IndicadorEconomico.objects.create(pais_id='CO', tipo_id='PIB', anio=timezone.now().year - 1,
                                               valor='12', fuente='MANUAL', es_simulado=True)
        path = '/api/dashboard/tendencias/?paises=CO'
        first = self.api.get(path).data
        with self.assertNumQueries(1):
            self.assertEqual(self.api.get(path).data, first)
        row.valor = '0'
        row.save(update_fields=['valor'])
        last = self.api.get(path).data['results'][0]['valores'][-1]
        self.assertEqual(last['valor'], '0.000000')

    def test_expiry_and_disabled_cache(self):
        self.assertEqual(shared_data('ttl', lambda: 'first'), 'first')
        # Eliminar solo la entrada de datos, conservando la generación.
        for key in self.redis.scan_iter(match=self.prefix + ':*:v1:*'):
            self.redis.pexpire(key, 1)
        import time
        time.sleep(.01)
        self.assertEqual(shared_data('ttl', lambda: 'second'), 'second')
        with override_settings(DATA_CACHE_TTL=0):
            self.assertEqual(shared_data('ttl', lambda: 'uncached'), 'uncached')

    def test_redis_failure_falls_back_to_database(self):
        with patch.object(caches['data'], 'get_or_set', side_effect=ConnectionError('offline')):
            self.assertEqual(self.api.get('/api/paises/').status_code, 200)
        with patch.object(caches['data'], 'set', side_effect=ConnectionError('offline')):
            country = Pais.objects.get(pk='CO')
            country.nombre = 'Guardado sin Redis'
            country.save(update_fields=['nombre'])
            self.assertEqual(Pais.objects.get(pk='CO').nombre, 'Guardado sin Redis')

    def test_redis_values_are_shared_between_processes(self):
        shared_data('cross-process', lambda: 'shared')
        env = {**os.environ, 'DJANGO_REDIS_URL': self.redis_url,
               'DJANGO_DATA_CACHE_PREFIX': self.prefix}
        script = """
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()
from common.data_cache import shared_data
assert shared_data('cross-process', lambda: 'miss') == 'shared'
"""
        subprocess.run([sys.executable, '-c', script], cwd=settings.BASE_DIR, env=env,
                       check=True, capture_output=True, text=True)
