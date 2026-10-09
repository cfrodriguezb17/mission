import logging
from time import perf_counter

logger = logging.getLogger("api.requests")


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = perf_counter()
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            user = getattr(request, "user", None)
            logger.log(logging.ERROR if locals().get("status", 500) >= 500 else logging.INFO,
                       "Solicitud HTTP", extra={
                           "metodo": request.method, "ruta": request.path,
                           "usuario": user.pk if user and user.is_authenticated else None,
                           "duracion_ms": round((perf_counter() - start) * 1000, 2),
                           "estado_http": locals().get("status", 500),
                       })
