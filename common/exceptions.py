"""Sobre uniforme; conservar campos de validación para clientes existentes."""
import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("api.errors")
MESSAGES = {
    400: ("validacion", "Revise los datos enviados."),
    401: ("autenticacion", "Inicie sesión con credenciales válidas."),
    403: ("permiso_denegado", "No tiene permiso para realizar esta operación."),
    404: ("no_encontrado", "El recurso solicitado no existe o no está disponible."),
    405: ("metodo_no_permitido", "Este método no está permitido."),
    406: ("formato_no_admitido", "El formato de respuesta solicitado no está disponible."),
    409: ("conflicto", "Los datos cambiaron. Recargue y revise antes de guardar."),
    415: ("contenido_no_admitido", "El formato del contenido enviado no está permitido."),
    429: ("limite_solicitudes", "Ha superado el límite de solicitudes. Intente más tarde."),
}


def error_payload(status, details=None):
    code, message = MESSAGES.get(status, ("error_interno", "No se pudo completar la solicitud."))
    return {"codigo": code, "mensaje": message, "detalles": details or {}}


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        # Nunca publicar SQL, credenciales, payloads ni textos de excepciones.
        logger.error("Error interno de API", extra={"tipo_error": type(exc).__name__})
        return Response({"error": error_payload(500)}, status=500)
    details = response.data
    legacy = dict(details) if isinstance(details, dict) else {"detail": details}
    response.data = {**legacy, "error": error_payload(response.status_code, details)}
    return response
