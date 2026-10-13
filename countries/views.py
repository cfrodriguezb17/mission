from rest_framework import filters, generics
from rest_framework.exceptions import ValidationError

from audit.mixins import ConsultaAuditadaMixin

from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination
from common.data_cache import SharedDataListMixin

from .models import Pais
from .serializers import PaisDetailSerializer, PaisValuesSerializer


class PaisListView(ConsultaAuditadaMixin, SharedDataListMixin, generics.ListAPIView):
    audit_entidad = "Pais"
    serializer_class = PaisValuesSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, StrictOrderingFilter]
    search_fields = ["nombre", "codigo_iso", "moneda__codigo", "moneda__nombre"]
    ordering_fields = ["nombre", "codigo_iso", "region", "poblacion"]
    ordering = ["nombre", "codigo_iso"]

    def get_queryset(self):
        queryset = Pais.objects.filter(activo=True).values(
            "codigo_iso", "nombre", "moneda_id", "moneda__nombre", "region", "latitud",
            "longitud", "poblacion", "bandera_url", "activo")
        region = self.request.query_params.get("region")
        if region is not None:
            region = region.strip().upper()
            if region not in Pais.Region.values:
                raise ValidationError({"region": "Región inválida. Use ANDINA, CONO_SUR, CENTROAMERICA o CARIBE."})
            queryset = queryset.filter(region=region)
        return queryset


class PaisDetailView(ConsultaAuditadaMixin, generics.RetrieveAPIView):
    audit_entidad = "Pais"
    audit_id_kwarg = "codigo_iso"
    def get_queryset(self):
        from django.db.models import Prefetch
        from economics.models import IndicadorEconomico

        return Pais.objects.filter(activo=True).select_related("moneda").prefetch_related(
            Prefetch("indicadores", queryset=IndicadorEconomico.objects.select_related("tipo")),
        )

    serializer_class = PaisDetailSerializer
    lookup_field = "codigo_iso"

    def get_object(self):
        self.kwargs[self.lookup_field] = self.kwargs[self.lookup_field].upper()
        return super().get_object()
