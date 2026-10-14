import asyncio
import json
import threading

from django.core.handlers.asgi import ASGIHandler
from django.http import JsonResponse
from django.test import AsyncRequestFactory, SimpleTestCase, override_settings
from django.urls import path

from common.asgi import RoutedHTTPApplication


def synchronous_view(request):
    return JsonResponse({'mode': 'sync', 'thread': threading.get_ident(), 'path': request.path_info})


async def asynchronous_view(request):
    await asyncio.sleep(0)
    return JsonResponse({'mode': 'async', 'thread': threading.get_ident(), 'path': request.path_info})


urlpatterns = [path('api/sync/', synchronous_view), path('api/new-async/', asynchronous_view)]


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=[], ALLOWED_HOSTS=['testserver'])
class ASGIRoutingTests(SimpleTestCase):
    async def response(self, path, root=''):
        application = RoutedHTTPApplication(ASGIHandler())
        scope = AsyncRequestFactory().get(root + path).scope
        scope['root_path'] = root
        first = True
        messages = []

        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        await application(scope, receive, send)
        self.assertEqual(messages[0]['status'], 200)
        body = b''.join(m.get('body', b'') for m in messages)
        return json.loads(body)

    async def test_synchronous_api_uses_worker_thread_and_honors_root_path(self):
        loop_thread = threading.get_ident()
        for root in ('', '/prefix'):
            with self.subTest(root=root):
                result = await self.response('/api/sync/', root)
                self.assertEqual(result['mode'], 'sync')
                self.assertNotEqual(result['thread'], loop_thread)
                self.assertEqual(result['path'], '/api/sync/')

    async def test_new_async_view_keeps_event_loop_outside_realtime_namespace(self):
        loop_thread = threading.get_ident()
        result = await self.response('/api/new-async/', '/prefix')
        self.assertEqual(result['mode'], 'async')
        self.assertEqual(result['thread'], loop_thread)
        self.assertEqual(result['path'], '/api/new-async/')
