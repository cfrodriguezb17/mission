"""Bound active application work independently of idle HTTP and live sockets."""
import asyncio
from contextlib import asynccontextmanager
import json

from django.conf import settings

from .exceptions import error_payload


class Budget:
    def __init__(self, limit, queue=0, wait_seconds=0):
        self.limit = limit
        self.queue = queue
        self.wait_seconds = wait_seconds
        self.pending = 0
        self.semaphore = asyncio.BoundedSemaphore(limit)

    @asynccontextmanager
    async def slot(self):
        if self.pending >= self.limit + self.queue:
            yield False
            return
        self.pending += 1
        acquired = False
        try:
            if self.semaphore.locked():
                try:
                    async with asyncio.timeout(self.wait_seconds):
                        await self.semaphore.acquire()
                except TimeoutError:
                    yield False
                    return
            else:
                await self.semaphore.acquire()
            acquired = True
            yield True
        finally:
            if acquired:
                self.semaphore.release()
            self.pending -= 1


class AdmissionControlledApplication:
    def __init__(self, application, *, http_limit, http_queue, wait_seconds,
                 websocket_limit, stream_limit):
        self.application = application
        self.http = Budget(http_limit, http_queue, wait_seconds)
        self.websockets = Budget(websocket_limit)
        self.streams = Budget(stream_limit)

    async def __call__(self, scope, receive, send):
        protocol = scope['type']
        if protocol not in ('http', 'websocket'):
            return await self.application(scope, receive, send)
        path = scope.get('path', '')
        root = scope.get('root_path', '').rstrip('/')
        if root and (path == root or path.startswith(root + '/')):
            path = path[len(root):] or '/'
        # Health probes must remain schedulable while the work queue is full.
        if protocol == 'http' and path == '/health/':
            return await self.application(scope, receive, send)
        budget = (self.websockets if protocol == 'websocket' else
                  self.streams if path == '/api/realtime/stream/' else self.http)
        async with budget.slot() as accepted:
            if accepted:
                return await self.application(scope, receive, send)
            if protocol == 'websocket':
                await send({'type': 'websocket.close', 'code': 1013})
                return
            body = json.dumps({'error': error_payload(503)}, ensure_ascii=False).encode()
            headers = [(b'content-type', b'application/json; charset=utf-8'),
                       (b'content-length', str(len(body)).encode()),
                       (b'retry-after', b'1'), (b'cache-control', b'no-store'),
                       (b'vary', b'Origin')]
            origin = dict(scope.get('headers', [])).get(b'origin', b'').decode('latin1')
            if origin and origin in settings.CORS_ALLOWED_ORIGINS:
                headers.append((b'access-control-allow-origin', origin.encode('latin1')))
            await send({'type': 'http.response.start', 'status': 503, 'headers': headers})
            await send({'type': 'http.response.body', 'body': body})
