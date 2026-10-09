from datetime import datetime, time, timezone as datetime_timezone

from django.shortcuts import get_object_or_404
from rest_framework import filters, generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.pagination import StandardPagination
from common.permissions import IsAdminRole
from countries.models import Pais
from economics.serializers import FechaFilterSerializer

from .selectors import historico_pais, ultimos_indices
from .serializers import CalcularSerializer, IndiceRiesgoSerializer
from .services import recalcular_riesgos


class CalcularView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = CalcularSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = recalcular_riesgos(**serializer.validated_data)
        return Response(result, status=503 if result["errores"] and not result["calculados"] else 200)


class RiskListView(generics.ListAPIView):
    serializer_class = IndiceRiesgoSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["pais", "fecha_calculo", "indice_compuesto", "score_economico",
                       "score_cambiario", "score_estabilidad", "id"]

    def filter_queryset(self, queryset):
        ordering = self.request.query_params.get("ordering")
        if ordering is not None and (not ordering or any(
            field.removeprefix("-") not in self.ordering_fields for field in ordering.split(",")
        )):
            raise ValidationError({"ordering": "Campos de ordenamiento inválidos."})
        return super().filter_queryset(queryset)


class RankingView(RiskListView):
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
