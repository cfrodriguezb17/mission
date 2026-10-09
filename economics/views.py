from datetime import date, timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import obtener_ip
from audit.mixins import ConsultaAuditadaMixin

from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination
from common.permissions import IsAdminRole
from common.serializers import DateRangeFilterSerializer as FechaFilterSerializer
from countries.models import Pais

from .models import IndicadorEconomico
from .selectors import cotizaciones_con_anterior
from .serializers import IndicadorFilterSerializer, IndicadorSerializer, SyncSerializer, TipoCambioSerializer
from backend.workflows import sincronizar_y_recalcular as sincronizar_indicadores


class EconomicListView(ConsultaAuditadaMixin, generics.ListAPIView):
    audit_entidad = "IndicadorEconomico"
    audit_id_kwarg = "codigo_iso"
    pagination_class = StandardPagination
    filter_backends = [StrictOrderingFilter]

    def get_pais(self):
        return get_object_or_404(Pais.objects.filter(activo=True), pk=self.kwargs["codigo_iso"].upper())


class IndicadorListView(EconomicListView):
    serializer_class = IndicadorSerializer
    ordering_fields = ["anio", "tipo", "valor", "fecha_actualizacion", "id"]
    ordering = ["-anio", "tipo", "id"]

    def get_queryset(self):
        pais = self.get_pais()
        params = self.request.query_params.copy()
        if "tipo" in params:
            params["tipo"] = params["tipo"].strip().upper()
        serializer = IndicadorFilterSerializer(data=params)
        serializer.is_valid(raise_exception=True)
        return IndicadorEconomico.objects.filter(pais=pais, **serializer.validated_data).select_related("tipo")


class TipoCambioListView(EconomicListView):
    audit_entidad = "TipoCambio"
    serializer_class = TipoCambioSerializer
    ordering_fields = ["fecha", "tasa", "id"]
    ordering = ["-fecha", "id"]

    def get_queryset(self):
        pais = self.get_pais()
        serializer = FechaFilterSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        if pais.moneda_id == "USD":
            end = params.get("fecha_fin", timezone.now().date())
            start = params.get("fecha_inicio", date.fromordinal(max(1, end.toordinal() - 29)))
            if start > end or (end - start).days > 365:
                raise ValidationError({"fecha_inicio": "La serie de identidad admite un rango ordenado de hasta 366 días."})
            self.identity = [{
                "id": None, "moneda_origen": "USD", "moneda_destino": "USD",
                "tasa": "1.000000000000", "fecha": (start + timedelta(days=i)).isoformat(),
                "variacion_porcentual": "0.000000", "dato_anterior_faltante": False,
                "fuente": "IDENTIDAD", "es_simulado": False,
            } for i in range((end - start).days + 1)]
            return []
        queryset = cotizaciones_con_anterior(pais.moneda_id)
        if "fecha_inicio" in params:
            queryset = queryset.filter(fecha__gte=params["fecha_inicio"])
        if "fecha_fin" in params:
            queryset = queryset.filter(fecha__lte=params["fecha_fin"])
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not hasattr(self, "identity"):
            queryset = self.filter_queryset(queryset)
            page = self.paginate_queryset(queryset)
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        # La identidad no es una cotización persistida; se pagina igual que el histórico.
        ordering = StrictOrderingFilter().get_ordering(request, self.identity, self)
        for field in reversed(ordering):
            self.identity.sort(key=lambda row: row[field.lstrip("-")] or 0, reverse=field.startswith("-"))
        return self.get_paginated_response(self.paginate_queryset(self.identity))


class SyncIndicadoresView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = SyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = sincronizar_indicadores(usuario=request.user, ip=obtener_ip(request), **serializer.validated_data,
                                        presupuesto=settings.ECONOMICS_SYNC_BUDGET_SECONDS)
        status = 503 if result["errores"] and not result["paises_procesados"] else 200
        return Response(result, status=status)
