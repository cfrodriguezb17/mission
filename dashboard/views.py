from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.mixins import ConsultaAuditadaMixin
from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination
from countries.models import Pais
from economics.models import IndicadorEconomico

from .selectors import paises_con_riesgo, resumen_dashboard
from .serializers import MapaSerializer, TendenciasFilterSerializer


class ResumenView(ConsultaAuditadaMixin, APIView):
    audit_entidad = "Dashboard"

    def get(self, request):
        return Response(resumen_dashboard(request.user))


class MapaView(ConsultaAuditadaMixin, generics.ListAPIView):
    audit_entidad = "Dashboard"
    serializer_class = MapaSerializer
    pagination_class = StandardPagination
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["codigo_iso", "nombre", "irpc"]
    ordering = ["codigo_iso"]

    def get_queryset(self):
        return paises_con_riesgo()


class TendenciasView(ConsultaAuditadaMixin, generics.GenericAPIView):
    audit_entidad = "Dashboard"
    pagination_class = StandardPagination
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["codigo_iso", "nombre"]
    ordering = ["codigo_iso"]

    def get(self, request):
        # Un parámetro vacío explícito es inválido, no equivale a omitirlo.
        filters = TendenciasFilterSerializer(data={key: request.query_params.get(key)
                                                  for key in ("tipo", "paises") if key in request.query_params})
        filters.is_valid(raise_exception=True)
        indicator = filters.validated_data["tipo"]
        countries = self.filter_queryset(Pais.objects.filter(pk__in=filters.validated_data["paises"], activo=True))
        page = self.paginate_queryset(countries)
        end = timezone.now().year - 1
        start = end - 4
        observations = {
            (row.pais_id, row.anio): row for row in IndicadorEconomico.objects.filter(
                pais_id__in=[country.pk for country in page], tipo=indicator, anio__range=(start, end))
        }
        series = []
        for country in page:
            values = []
            for year in range(start, end + 1):
                row = observations.get((country.pk, year))
                values.append({"anio": year, "valor": str(row.valor) if row else None,
                               "fuente": row.fuente if row else None,
                               "es_simulado": row.es_simulado if row else None})
            series.append({"pais": country.pk, "nombre_pais": country.nombre,
                           "datos_parciales": any(value["valor"] is None for value in values), "valores": values})
        response = self.get_paginated_response(series)
        response.data.update({"tipo": indicator.pk, "unidad": indicator.unidad,
                              "anio_inicio": start, "anio_fin": end})
        return response
