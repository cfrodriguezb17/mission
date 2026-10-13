from types import SimpleNamespace
from unittest.mock import AsyncMock

from django.http import HttpResponse
from django.test import AsyncRequestFactory, SimpleTestCase
from django.utils.functional import SimpleLazyObject

from common.middleware import RequestLoggingMiddleware


class AsyncLoggingTests(SimpleTestCase):
    async def test_async_logging_resolves_lazy_session_user_without_sync_database_access(self):
        request = AsyncRequestFactory().get('/health/')
        request.user = SimpleLazyObject(lambda: self.fail('No resolver sesión de forma síncrona'))
        request.auser = AsyncMock(return_value=SimpleNamespace(pk=42, is_authenticated=True))

        async def response(request):
            return HttpResponse('ok')

        with self.assertLogs('api.requests') as output:
            result = await RequestLoggingMiddleware(response)(request)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(output.records[0].usuario, 42)
        request.auser.assert_awaited_once()

    async def test_async_logging_records_failure_without_swallowing_it(self):
        request = AsyncRequestFactory().get('/health/')

        async def response(request):
            raise RuntimeError('test')

        with self.assertLogs('api.requests', level='ERROR') as output:
            with self.assertRaises(RuntimeError):
                await RequestLoggingMiddleware(response)(request)
        self.assertEqual(output.records[0].estado_http, 500)
