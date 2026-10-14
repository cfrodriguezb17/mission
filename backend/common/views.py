from django.db import connection
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from .schema import APIIndexSerializer, MarkdownDocumentationSerializer

from .exceptions import error_payload


class APIIndexView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=APIIndexSerializer, tags=['documentacion'], summary='Información de la API')
    def get(self, request):
        return Response({"nombre": "DataPulse Latam API", "version": "1",
                         "autenticacion": "Bearer JWT", "documentacion": "/api/docs/"})


class APIDocsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=MarkdownDocumentationSerializer, tags=['documentacion'], summary='Contrato detallado en Markdown')
    def get(self, request):
        # Archivo del repositorio, sin datos de usuarios ni secretos.
        from django.conf import settings
        return Response({"formato": "markdown", "contenido": (settings.BASE_DIR / "API.md").read_text(encoding="utf-8")})


class APINotFoundView(APIView):
    schema = None
    permission_classes = [AllowAny]
    authentication_classes = []

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        raise NotFound("El recurso solicitado no existe.")


def health(request):
    if request.method != "GET":
        return JsonResponse({"error": error_payload(405)}, status=405)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"estado": "no_disponible"}, status=503)
    return JsonResponse({"estado": "ok"})


def api_not_found(request, exception=None):
    return JsonResponse({"error": error_payload(404)}, status=404)


def api_server_error(request):
    return JsonResponse({"error": error_payload(500)}, status=500)
