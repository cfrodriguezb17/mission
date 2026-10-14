"""Componentes compartidos del contrato OpenAPI; no ejecutan consultas ni escrituras."""
from drf_spectacular.utils import extend_schema_serializer, inline_serializer, OpenApiParameter
from drf_spectacular.openapi import AutoSchema
from rest_framework import serializers

from .exceptions import MESSAGES

PAGINATION_PARAMETERS = [
    OpenApiParameter('page', int, description='Página, desde 1.'),
    OpenApiParameter('page_size', int, description='Resultados por página; máximo 100, predeterminado 20.'),
]


class DataPulseAutoSchema(AutoSchema):
    def _get_request_body(self, direction='request'):
        # Este contrato usa JSON con versión en DELETE, que spectacular omite por defecto.
        if self.method == 'DELETE' and self.get_request_serializer() is not None:
            schema, required = self._get_request_for_media_type(self.get_request_serializer(), direction)
            return {'content': {'application/json': {'schema': schema}}, 'required': required}
        return super()._get_request_body(direction)


def paginated(name, item, **extra):
    envelope = inline_serializer(name, fields={
        'count': serializers.IntegerField(),
        'next': serializers.URLField(allow_null=True),
        'previous': serializers.URLField(allow_null=True),
        'results': item(many=True),
        **extra,
    })
    extend_schema_serializer(many=False)(envelope.__class__)
    return envelope


class APIIndexSerializer(serializers.Serializer):
    nombre = serializers.CharField()
    version = serializers.CharField()
    autenticacion = serializers.CharField()
    documentacion = serializers.CharField()


class MarkdownDocumentationSerializer(serializers.Serializer):
    formato = serializers.CharField()
    contenido = serializers.CharField()


class OperationResultSerializer(serializers.Serializer):
    """Los detalles dependen de la tarea y conservan los fallos parciales."""
    errores = serializers.ListField(child=serializers.JSONField())
    estado = serializers.CharField(required=False)
    paises_procesados = serializers.ListField(child=serializers.CharField(), required=False)
    calculados = serializers.ListField(child=serializers.JSONField(), required=False)
    creados = serializers.IntegerField(required=False)
    actualizados = serializers.IntegerField(required=False)
    faltantes = serializers.JSONField(required=False)
    riesgos = serializers.JSONField(required=False)
    alertas = serializers.JSONField(required=False)
    recalculo_pendiente = serializers.BooleanField(required=False)
    alertas_pendientes = serializers.BooleanField(required=False)
    auditoria_pendiente = serializers.BooleanField(required=False)


def add_common_errors(result, generator, request, public):
    """Documentar el sobre uniforme sin eliminar campos adicionales de DRF."""
    result['components']['schemas']['APIError'] = {
        'type': 'object', 'required': ['error'], 'additionalProperties': True,
        'properties': {'error': {
            'type': 'object', 'required': ['codigo', 'mensaje', 'detalles'],
            'properties': {
                'codigo': {'type': 'string'}, 'mensaje': {'type': 'string'},
                'detalles': {},
            },
        }},
    }
    for path, methods in result['paths'].items():
        for method, operation in methods.items():
            if method not in ('get', 'post', 'put', 'patch', 'delete'):
                continue
            codes = [400, 429, 503]
            if operation.get('security'):
                codes += [401, 403]
            if path in ('/api/auth/login/', '/api/auth/refresh/'):
                codes.append(401)
            if '{' in path:
                codes.append(404)
            if path.startswith('/api/portafolios/') and method in ('put', 'delete', 'post') and '{' in path:
                codes.append(409)
            for code in codes:
                operation['responses'].setdefault(str(code), {
                    'description': MESSAGES[code][1],
                    'content': {'application/json': {'schema': {'$ref': '#/components/schemas/APIError'}}},
                })
    # Estas vistas son async de Django y no aparecen en la introspección de DRF.
    for suffix, description, content in [
        ('resumen', 'Conteos visibles del usuario; alternativa de polling.', {
            'application/json': {'schema': {'type': 'object', 'required': ['alertas_no_leidas', 'paises_activos'],
                'properties': {'alertas_no_leidas': {'type': 'integer'}, 'paises_activos': {'type': 'integer'}}}}}),
        ('stream', 'Flujo SSE autenticado. La conexión permanece abierta; ver eventos en /api/docs/.', {
            'text/event-stream': {'schema': {'type': 'string'}}}),
    ]:
        result['paths'][f'/api/realtime/{suffix}/'] = {'get': {
            'operationId': f'realtime_{suffix}', 'tags': ['realtime'], 'description': description,
            'security': [{'jwtAuth': []}],
            'responses': {'200': {'description': 'Respuesta en tiempo real', 'content': content},
                **{str(code): {'description': MESSAGES[code][1], 'content': {'application/json': {
                    'schema': {'$ref': '#/components/schemas/APIError'}}}} for code in (401, 429, 503)}},
        }}
    return result
