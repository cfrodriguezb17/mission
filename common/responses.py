"""Adaptar resultados de operaciones por lotes al contrato HTTP compartido."""
from rest_framework import status
from rest_framework.response import Response

from .exceptions import error_response_data


def operation_response(result, *, completed_key):
    """Fallo total: 503; éxito o avance parcial: 200, conservando lo procesado.

    Los servicios proporcionan errores seguros. Este adaptador no lanza
    excepciones que puedan revertir etapas ya guardadas por el workflow.
    """
    if result["errores"] and not result[completed_key]:
        return Response(error_response_data(
            result, status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"errores": result["errores"]},
        ), status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(result)
