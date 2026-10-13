import logging
from time import perf_counter
from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.utils.functional import SimpleLazyObject

logger = logging.getLogger("api.requests")


class RequestLoggingMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.is_async:
            return self.__acall__(request)
        start = perf_counter()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            self.log(request, status, start, getattr(request, 'user', None))

    async def __acall__(self, request):
        start = perf_counter()
        status = 500
        try:
            response = await self.get_response(request)
            status = response.status_code
            return response
        finally:
            user = getattr(request, 'user', None)
            if type(user) is SimpleLazyObject:
                user = await request.auser()
            self.log(request, status, start, user)

    @staticmethod
    def log(request, status, start, user):
        logger.log(logging.ERROR if status >= 500 else logging.INFO,
                   "Solicitud HTTP", extra={
                           "metodo": request.method, "ruta": request.path,
                           "usuario": user.pk if user and user.is_authenticated else None,
                           "duracion_ms": round((perf_counter() - start) * 1000, 2),
                           "estado_http": status,
                       })
