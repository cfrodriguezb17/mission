from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from audit.services import obtener_ip, registrar_actividad
from portfolios.selectors import portafolios_visibles, resumen_portafolio
from risk.selectors import ultimos_indices

from .renderers import PDFDownloadRenderer
from .services import generar_pdf


class ExportPDFView(APIView):
    renderer_classes = [JSONRenderer, PDFDownloadRenderer]

    @extend_schema(summary='Descargar portafolio en PDF', responses={
        (200, 'application/pdf'): OpenApiResponse(OpenApiTypes.BINARY, description='PDF con gráficos e instantánea del portafolio.')},
        parameters=[OpenApiParameter('Content-Disposition', str, OpenApiParameter.HEADER, response=[200])])
    def get(self, request, pk):
        # Las escrituras de posiciones usan el mismo bloqueo; capturar una sola versión.
        with transaction.atomic():
            portfolio = get_object_or_404(portafolios_visibles(request.user).select_for_update(), pk=pk)
            portfolio.usuario  # Cargar al propietario dentro de la instantánea.
            positions = list(portfolio.posiciones.select_related("pais").order_by("fecha_entrada", "pk"))
            risks = {row.pais_id: row for row in ultimos_indices().filter(pais_id__in={p.pais_id for p in positions})}
            summary = resumen_portafolio(portfolio, posiciones=positions, indices=risks)
        pdf = generar_pdf(portafolio=portfolio, posiciones=positions, resumen=summary, riesgos=risks, fecha=timezone.now())
        registrar_actividad(usuario=request.user, accion="EXPORT", entidad="Portafolio", entidad_id=portfolio.pk,
                            ip=obtener_ip(request), detalle={"operacion": "export_pdf", "origen": "HTTP",
                                                           "version": portfolio.version})
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="portafolio-{portfolio.pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
