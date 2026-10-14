import asyncio
import json

from django.test import SimpleTestCase, override_settings

from common.admission import AdmissionControlledApplication, Budget


class AdmissionTests(SimpleTestCase):
    def application(self, handler, **options):
        return AdmissionControlledApplication(handler, http_limit=1, http_queue=1,
            wait_seconds=options.get('wait_seconds', .03), websocket_limit=1, stream_limit=1)

    async def test_bounded_queue_timeout_and_cancellation_release_capacity(self):
        budget = Budget(1, queue=1, wait_seconds=.02)
        async with budget.slot() as first:
            self.assertTrue(first)
            async def waiting():
                async with budget.slot() as accepted:
                    return accepted
            waiter = asyncio.create_task(waiting())
            await asyncio.sleep(0)
            async with budget.slot() as overflow:
                self.assertFalse(overflow)
            self.assertFalse(await waiter)
            cancelled = asyncio.create_task(waiting())
            await asyncio.sleep(0)
            cancelled.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await cancelled
        self.assertEqual(budget.pending, 0)
        async with budget.slot() as accepted:
            self.assertTrue(accepted)

    async def test_queued_request_runs_when_previous_finishes_and_errors_release_slot(self):
        budget = Budget(1, queue=1, wait_seconds=.2)
        entered = asyncio.Event()
        release = asyncio.Event()
        async def work():
            async with budget.slot() as accepted:
                self.assertTrue(accepted)
                entered.set()
                await release.wait()
        task = asyncio.create_task(work())
        await entered.wait()
        async def queued():
            async with budget.slot() as accepted:
                return accepted
        waiting = asyncio.create_task(queued())
        await asyncio.sleep(0)
        release.set()
        self.assertTrue(await waiting)
        await task
        with self.assertRaises(RuntimeError):
            async with budget.slot():
                raise RuntimeError('handler failed')
        self.assertEqual(budget.pending, 0)

    @override_settings(CORS_ALLOWED_ORIGINS=['https://frontend.example'])
    async def test_websocket_stream_http_and_health_have_independent_budgets(self):
        release = asyncio.Event()
        entered = {'websocket': asyncio.Event(), 'stream': asyncio.Event(), 'http': asyncio.Event()}
        async def handler(scope, receive, send):
            name = ('websocket' if scope['type'] == 'websocket' else
                    'stream' if scope['path'].endswith('/stream/') else
                    'health' if scope['path'].endswith('/health/') else 'http')
            if name == 'health':
                await send({'type': 'http.response.start', 'status': 200})
                return
            entered[name].set()
            await release.wait()
        application = self.application(handler)
        messages = []
        async def send(message):
            messages.append(message)
        async def receive():
            await asyncio.Event().wait()
        def scope(protocol, path):
            return {'type': protocol, 'path': path, 'root_path': '/prefix',
                    'headers': [(b'origin', b'https://frontend.example')]}
        tasks = [asyncio.create_task(application(scope(protocol, path), receive, send))
                 for protocol, path in [('websocket', '/prefix/ws/notificaciones/'),
                                        ('http', '/prefix/api/realtime/stream/'),
                                        ('http', '/prefix/api/dashboard/resumen/')]]
        for event in entered.values():
            await asyncio.wait_for(event.wait(), .5)
        await application(scope('http', '/prefix/health/'), receive, send)
        await application(scope('websocket', '/prefix/ws/notificaciones/'), receive, send)
        await application(scope('http', '/prefix/api/dashboard/resumen/'), receive, send)
        self.assertEqual(messages[0]['status'], 200)
        self.assertEqual(messages[1], {'type': 'websocket.close', 'code': 1013})
        self.assertEqual(messages[2]['status'], 503)
        headers = dict(messages[2]['headers'])
        self.assertEqual(headers[b'retry-after'], b'1')
        self.assertEqual(headers[b'access-control-allow-origin'], b'https://frontend.example')
        self.assertEqual(json.loads(messages[3]['body'])['error']['codigo'], 'servicio_no_disponible')
        release.set()
        await asyncio.gather(*tasks)
        self.assertEqual(application.http.pending, 0)
        self.assertEqual(application.websockets.pending, 0)
        self.assertEqual(application.streams.pending, 0)
