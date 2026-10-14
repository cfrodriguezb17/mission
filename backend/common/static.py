"""WhiteNoise compatible con ASGI sin adaptar a síncrono las peticiones de API."""
from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from whitenoise.middleware import WhiteNoiseMiddleware


class AsyncWhiteNoiseMiddleware(WhiteNoiseMiddleware):
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        super().__init__(get_response)
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.is_async:
            return self.async_call(request)
        return super().__call__(request)

    async def async_call(self, request):
        if self.autorefresh:
            # Solo desarrollo: la búsqueda puede consultar el sistema de archivos.
            static_file = await sync_to_async(self.find_file, thread_sensitive=False)(request.path_info)
        else:
            # WhiteNoise precarga este índice al arrancar; aquí no hay acceso a disco.
            static_file = self.files.get(request.path_info)
        if static_file is None:
            return await self.get_response(request)
        # Abrir el archivo y resolver sus cabeceras tampoco debe bloquear el loop.
        return await sync_to_async(self.serve, thread_sensitive=False)(static_file, request)
