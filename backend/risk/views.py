from datetime import datetime, time, timezone as datetime_timezone

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from audit.services import obtener_ip
from audit.mixins import ConsultaAuditadaMixin

from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination
from common.permissions import IsAdminRole
from common.responses import operation_response
from common.serializers import DateRangeFilterSerializer as FechaFilterSerializer
from countries.models import Pais

from .selectors import historico_pais, ultimos_indices
from .serializers import CalcularSerializer, IndiceRiesgoSerializer, RankingSerializer
from backend.workflows import recalcular_con_alertas as recalcular_riesgos


class CalcularView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = CalcularSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = recalcular_riesgos(usuario=request.user, ip=obtener_ip(request), **serializer.validated_data)
        return operation_response(result, completed_key="calculados")


class RiskListView(ConsultaAuditadaMixin, generics.ListAPIView):
    audit_entidad = "IndiceRiesgo"
    audit_id_kwarg = "codigo_iso"
    serializer_class = IndiceRiesgoSerializer
    pagination_class = StandardPagination
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["pais", "fecha_calculo", "indice_compuesto", "score_economico",
                       "score_cambiario", "score_estabilidad", "id"]


class RankingView(RiskListView):
    serializer_class = RankingSerializer
    ordering = ["-indice_compuesto", "pais"]

    def get_queryset(self):
        return ultimos_indices()


class HistoricoView(RiskListView):
    ordering = ["-fecha_calculo", "-id"]

    def get_queryset(self):
        self.pais = get_object_or_404(Pais.objects.filter(activo=True), pk=self.kwargs["codigo_iso"].upper())
        serializer = FechaFilterSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = historico_pais(self.pais)
        params = serializer.validated_data
        # Rango de días UTC sobre el timestamp indexado; fecha_fin incluye el día entero.
        if "fecha_inicio" in params:
            queryset = queryset.filter(fecha_calculo__gte=datetime.combine(
                params["fecha_inicio"], time.min, tzinfo=datetime_timezone.utc))
        if "fecha_fin" in params:
            end = datetime.combine(params["fecha_fin"], time.max, tzinfo=datetime_timezone.utc)
            queryset = queryset.filter(fecha_calculo__lte=end)
        return queryset


class DetalleView(HistoricoView):
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        latest = historico_pais(self.pais).first()
        page = self.paginate_queryset(queryset)
        history = self.get_paginated_response(self.get_serializer(page, many=True).data).data
        return Response({"ultimo": self.get_serializer(latest).data if latest else None,
                         "historico": history})
