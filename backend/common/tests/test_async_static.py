import gzip
from pathlib import Path
import tempfile
import threading
from unittest.mock import AsyncMock, patch

from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.test import AsyncRequestFactory, RequestFactory, SimpleTestCase, override_settings

from common.static import AsyncWhiteNoiseMiddleware


class AsyncStaticTests(SimpleTestCase):
    content = b'body { color: blue; }\n' * 50

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='mission-static-test-')
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        (root / 'sample.css').write_bytes(self.content)
        (root / 'sample.css.gz').write_bytes(gzip.compress(self.content))
        self.config = override_settings(DEBUG=False, STATIC_ROOT=str(root), STATIC_URL='/static/',
                                       WHITENOISE_AUTOREFRESH=False, WHITENOISE_USE_FINDERS=False)
        self.config.enable()
        self.addCleanup(self.config.disable)

    async def body(self, response):
        try:
            return await sync_to_async(lambda: b''.join(response.streaming_content))() if response.streaming else response.content
        finally:
            await sync_to_async(response.close)()

    async def test_async_api_passes_through_without_thread_adaptation(self):
        loop_thread = threading.get_ident()

        async def handler(request):
            self.assertEqual(threading.get_ident(), loop_thread)
            return HttpResponse('API')

        middleware = AsyncWhiteNoiseMiddleware(handler)
        with patch.object(middleware, 'find_file', side_effect=AssertionError('No buscar en disco')):
            response = await middleware(AsyncRequestFactory().get('/api/paises/'))
        self.assertEqual(response.content, b'API')

    async def test_async_static_preserves_compression_range_conditional_and_head(self):
        handler = AsyncMock(side_effect=AssertionError('El archivo no debe llegar a la vista'))
        middleware = AsyncWhiteNoiseMiddleware(handler)
        factory = AsyncRequestFactory()
        response = await middleware(factory.get('/static/sample.css'))
        etag = response['ETag']
        self.assertEqual(response['Cache-Control'], 'max-age=60, public')
        self.assertEqual(await self.body(response), self.content)
        response = await middleware(factory.get('/static/sample.css', headers={'Range': 'bytes=0-3'}))
        self.assertEqual(response.status_code, 206)
        self.assertEqual(await self.body(response), self.content[:4])
        response = await middleware(factory.get('/static/sample.css', headers={'If-None-Match': etag}))
        self.assertEqual(response.status_code, 304)
        self.assertEqual(await self.body(response), b'')
        response = await middleware(factory.head('/static/sample.css'))
        self.assertEqual(response['Content-Length'], str(len(self.content)))
        self.assertEqual(await self.body(response), b'')
        response = await middleware(factory.get('/static/sample.css', headers={'Accept-Encoding': 'gzip'}))
        self.assertEqual(response['Content-Encoding'], 'gzip')
        self.assertEqual(gzip.decompress(await self.body(response)), self.content)

    async def test_development_file_lookup_runs_outside_event_loop(self):
        with override_settings(WHITENOISE_AUTOREFRESH=True):
            middleware = AsyncWhiteNoiseMiddleware(AsyncMock(return_value=HttpResponse('fallback')))
        loop_thread = threading.get_ident()
        original = middleware.find_file

        def lookup(path):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return original(path)

        with patch.object(middleware, 'find_file', side_effect=lookup):
            response = await middleware(AsyncRequestFactory().get('/static/sample.css'))
        self.assertEqual(await self.body(response), self.content)

    def test_sync_requests_keep_existing_static_behavior(self):
        middleware = AsyncWhiteNoiseMiddleware(lambda request: HttpResponse('fallback'))
        response = middleware(RequestFactory().get('/static/sample.css'))
        try:
            self.assertEqual(b''.join(response.streaming_content), self.content)
        finally:
            response.close()
        self.assertEqual(middleware(RequestFactory().get('/api/paises/')).content, b'fallback')
