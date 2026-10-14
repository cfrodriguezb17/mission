from django.test import SimpleTestCase, override_settings
from django.contrib.staticfiles.finders import find
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema
from rest_framework.test import APIClient


class OpenAPITests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def component(self, ref):
        return self.schema['components']['schemas'][ref.rsplit('/', 1)[-1]]

    def body(self, path, method):
        operation = self.schema['paths'][path][method]
        return self.component(operation['requestBody']['content']['application/json']['schema']['$ref'])

    def test_schema_validates_without_database_and_excludes_catchall(self):
        validate_schema(self.schema)
        self.assertTrue(self.schema['openapi'].startswith('3.'))
        self.assertNotIn('/api/schema/', self.schema['paths'])
        self.assertNotIn('/api/{var}/', self.schema['paths'])
        for path in ['/api/auth/login/', '/api/paises/', '/api/riesgo/', '/api/dashboard/tendencias/',
                     '/api/portafolios/', '/api/alertas/', '/api/realtime/resumen/', '/api/realtime/stream/']:
            self.assertIn(path, self.schema['paths'])

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_public_schema_and_swagger_use_local_static_assets(self):
        client = APIClient()
        response = client.get('/api/schema/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['info']['title'], 'DataPulse Latam API')
        response = client.get('/api/swagger/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js')
        self.assertContains(response, '/api/schema/')
        self.assertNotContains(response, 'cdn.jsdelivr.net')
        self.assertIsNotNone(find('drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js'))

    def test_jwt_login_and_protected_operations_have_correct_contracts(self):
        paths = self.schema['paths']
        self.assertNotIn('security', paths['/api/auth/login/']['post'])
        self.assertEqual(paths['/api/paises/']['get']['security'], [{'jwtAuth': []}])
        self.assertEqual(self.schema['components']['securitySchemes']['jwtAuth']['scheme'], 'bearer')
        self.assertEqual(set(self.body('/api/auth/login/', 'post')['required']), {'email', 'password'})
        login = paths['/api/auth/login/']['post']['responses']['200']
        tokens = self.component(login['content']['application/json']['schema']['$ref'])
        self.assertEqual(set(tokens['properties']), {'access', 'refresh'})
        refresh = paths['/api/auth/refresh/']['post']['responses']['200']
        self.assertEqual(set(self.component(refresh['content']['application/json']['schema']['$ref'])['properties']), {'access'})
        self.assertNotIn('password', self.schema['components']['schemas']['User']['properties'])

    def test_versioned_deletes_and_position_close_are_not_documented_as_empty(self):
        paths = self.schema['paths']
        for path in ['/api/portafolios/{id}/', '/api/portafolios/{id}/posiciones/{posicion_id}/']:
            self.assertIn('version', self.body(path, 'delete')['required'])
            self.assertIn('409', paths[path]['delete']['responses'])
        self.assertIn('204', paths['/api/portafolios/{id}/']['delete']['responses'])
        close = paths['/api/portafolios/{id}/posiciones/{posicion_id}/']['delete']['responses']['200']
        self.assertIn('version_portafolio', self.component(close['content']['application/json']['schema']['$ref'])['properties'])

    def test_pagination_queries_and_pdf_match_the_http_contract(self):
        paths = self.schema['paths']
        trend = paths['/api/dashboard/tendencias/']['get']
        self.assertTrue({'tipo', 'paises', 'page', 'page_size'} <= {p['name'] for p in trend['parameters']})
        props = self.component(trend['responses']['200']['content']['application/json']['schema']['$ref'])['properties']
        self.assertTrue({'count', 'results', 'tipo', 'unidad', 'anio_inicio', 'anio_fin'} <= set(props))
        detail = paths['/api/riesgo/{codigo_iso}/']['get']['responses']['200']
        self.assertEqual(set(self.component(detail['content']['application/json']['schema']['$ref'])['properties']), {'ultimo', 'historico'})
        pdf = paths['/api/portafolios/{id}/export/pdf/']['get']['responses']['200']
        self.assertEqual(pdf['content']['application/pdf']['schema']['format'], 'binary')
        self.assertIn('Content-Disposition', pdf['headers'])

    def test_documentation_does_not_disable_api_authentication(self):
        self.assertEqual(APIClient().get('/api/paises/').status_code, 401)
