"""Ejecutar la API DRF síncrona en un único tramo dentro del servidor ASGI."""
from asgiref.sync import iscoroutinefunction, sync_to_async
from django.core.handlers.asgi import ASGIHandler
from django.urls import Resolver404, resolve


class SynchronousAPIHandler(ASGIHandler):
    def __init__(self):
        # Conserva el ciclo ASGI de Django (body, desconexiones, cierre y señales).
        # Solo middleware, vista y renderizado se agrupan en la ruta síncrona.
        self.load_middleware(is_async=False)
        self._middleware_chain = sync_to_async(self._middleware_chain, thread_sensitive=True)


class RoutedHTTPApplication:
    def __init__(self, asynchronous_application):
        self.asynchronous_application = asynchronous_application
        self.synchronous_api = SynchronousAPIHandler()

    async def __call__(self, scope, receive, send):
        root = scope.get('root_path', '').rstrip('/')
        path = scope['path']
        if root and (path == root or path.startswith(root + '/')):
            path = path[len(root):] or '/'
        target = self.asynchronous_application
        if path.startswith('/api/'):
            try:
                callback = resolve(path).func
            except Resolver404:
                pass
            else:
                if not iscoroutinefunction(callback):
                    target = self.synchronous_api
        await target(scope, receive, send)
