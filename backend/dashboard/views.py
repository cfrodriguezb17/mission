from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from common.schema import PAGINATION_PARAMETERS

from audit.mixins import ConsultaAuditadaMixin
from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination
from common.data_cache import data_response, shared_data, SharedDataListMixin
from countries.models import Pais
from economics.models import IndicadorEconomico

from .selectors import paises_con_riesgo, resumen_dashboard
from .serializers import MapaSerializer, TendenciasFilterSerializer, ResumenDashboardSerializer, TendenciasResponse


class ResumenView(ConsultaAuditadaMixin, APIView):
    audit_entidad = "Dashboard"

    @extend_schema(responses=ResumenDashboardSerializer)
    def get(self, request):
        return data_response(resumen_dashboard(request.user))


class MapaView(ConsultaAuditadaMixin, SharedDataListMixin, generics.ListAPIView):
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
    queryset = Pais.objects.filter(activo=True)
    pagination_class = StandardPagination
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["codigo_iso", "nombre"]
    ordering = ["codigo_iso"]

    @extend_schema(parameters=[TendenciasFilterSerializer, *PAGINATION_PARAMETERS,
        OpenApiParameter('ordering', str, description='codigo_iso o nombre; prefijo - para descendente.')],
        responses=TendenciasResponse)
    def get(self, request):
        if request.accepted_renderer.format != 'json':
            return self.get_uncached(request)
        key = f'trends:{timezone.now().year}:{request.build_absolute_uri()}'
        return data_response(shared_data(key, lambda: self.get_uncached(request).data))

    def get_uncached(self, request):
        # Un parámetro vacío explícito es inválido, no equivale a omitirlo.
        filters = TendenciasFilterSerializer(data={key: request.query_params.get(key)
                                                  for key in ("tipo", "paises") if key in request.query_params})
        filters.is_valid(raise_exception=True)
        indicator = filters.validated_data["tipo"]
        countries = self.filter_queryset(Pais.objects.filter(
            pk__in=filters.validated_data["paises"], activo=True).values("codigo_iso", "nombre"))
        page = self.paginate_queryset(countries)
        end = timezone.now().year - 1
        start = end - 4
        observations = {
            (row['pais_id'], row['anio']): row for row in IndicadorEconomico.objects.filter(
                pais_id__in=[country['codigo_iso'] for country in page], tipo=indicator,
                anio__range=(start, end)).values('pais_id', 'anio', 'valor', 'fuente', 'es_simulado')
        }
        series = []
        for country in page:
            values = []
            for year in range(start, end + 1):
                row = observations.get((country['codigo_iso'], year))
                values.append({"anio": year, "valor": str(row['valor']) if row else None,
                               "fuente": row['fuente'] if row else None,
                               "es_simulado": row['es_simulado'] if row else None})
            series.append({"pais": country['codigo_iso'], "nombre_pais": country['nombre'],
                           "datos_parciales": any(value["valor"] is None for value in values), "valores": values})
        response = self.get_paginated_response(series)
        response.data.update({"tipo": indicator.pk, "unidad": indicator.unidad,
                              "anio_inicio": start, "anio_fin": end})
        return response
