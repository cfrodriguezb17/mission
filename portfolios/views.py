from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import filters, generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import obtener_ip
from audit.mixins import ConsultaAuditadaMixin

from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination

from .permissions import exigir_edicion, exigir_escritura
from .selectors import portafolios_visibles, resumen_portafolio
from .serializers import (
    CerrarPosicionSerializer, CrearPortafolioSerializer, CrearPosicionSerializer,
    EditarPortafolioSerializer, EditarPosicionSerializer, PortafolioDetailSerializer,
    PortafolioFilterSerializer, PortafolioSerializer, PosicionSerializer, VersionSerializer,
)
from .services import (
    agregar_posicion, cerrar_posicion, crear_portafolio, editar_portafolio,
    editar_posicion, eliminar_portafolio,
)


def entrada(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def visible(request, pk, bloquear=False):
    queryset = portafolios_visibles(request.user)
    return get_object_or_404(queryset.select_for_update() if bloquear else queryset, pk=pk)


class PortafolioListView(ConsultaAuditadaMixin, generics.ListAPIView):
    audit_entidad = "Portafolio"
    serializer_class = PortafolioSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, StrictOrderingFilter]
    search_fields = ["nombre", "descripcion"]
    ordering_fields = ["nombre", "fecha_creacion", "fecha_modificacion", "id"]
    ordering = ["-fecha_modificacion", "-id"]

    def get_queryset(self):
        serializer = PortafolioFilterSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        params = dict(serializer.validated_data)
        propios = params.pop("propios", None)
        queryset = portafolios_visibles(self.request.user).filter(**params)
        if propios is not None:
            queryset = queryset.filter(usuario=self.request.user) if propios else queryset.exclude(usuario=self.request.user)
        return queryset

    @transaction.atomic
    def post(self, request):
        exigir_escritura(request.user)
        portfolio = crear_portafolio(request.user, entrada(CrearPortafolioSerializer, request), ip=obtener_ip(request))
        return Response(PortafolioSerializer(portfolio, context={"request": request}).data, status=status.HTTP_201_CREATED)


class PortafolioDetailView(ConsultaAuditadaMixin, APIView):
    audit_entidad = "Portafolio"
    audit_id_kwarg = "pk"
    @transaction.atomic
    def get(self, request, pk):
        portfolio = visible(request, pk, bloquear=True)
        return Response(PortafolioDetailSerializer(portfolio, context={"request": request}).data)

    @transaction.atomic
    def put(self, request, pk):
        exigir_edicion(request.user, visible(request, pk))
        data = entrada(EditarPortafolioSerializer, request)
        portfolio = editar_portafolio(request.user, pk, data.pop("version"), data, ip=obtener_ip(request))
        return Response(PortafolioDetailSerializer(portfolio, context={"request": request}).data)

    def delete(self, request, pk):
        exigir_edicion(request.user, visible(request, pk), solo_propietario=True)
        data = entrada(VersionSerializer, request)
        eliminar_portafolio(request.user, pk, data["version"], ip=obtener_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PosicionCreateView(APIView):
    @transaction.atomic
    def post(self, request, pk):
        exigir_edicion(request.user, visible(request, pk))
        data = entrada(CrearPosicionSerializer, request)
        position, portfolio = agregar_posicion(request.user, pk, data.pop("version"), data, ip=obtener_ip(request))
        return Response({**PosicionSerializer(position).data, "version_portafolio": portfolio.version},
                        status=status.HTTP_201_CREATED)


class PosicionDetailView(APIView):
    @transaction.atomic
    def put(self, request, pk, posicion_id):
        exigir_edicion(request.user, visible(request, pk))
        data = entrada(EditarPosicionSerializer, request)
        position, portfolio = editar_posicion(request.user, pk, posicion_id, data.pop("version"), data, ip=obtener_ip(request))
        return Response({**PosicionSerializer(position).data, "version_portafolio": portfolio.version})

    @transaction.atomic
    def delete(self, request, pk, posicion_id):
        exigir_edicion(request.user, visible(request, pk))
        data = entrada(CerrarPosicionSerializer, request)
        position, portfolio = cerrar_posicion(request.user, pk, posicion_id, data["version"], data.get("fecha_salida"), ip=obtener_ip(request))
        # El cierre conserva la fila y devuelve la nueva versión para seguir editando.
        return Response({**PosicionSerializer(position).data, "version_portafolio": portfolio.version})


class ResumenView(ConsultaAuditadaMixin, APIView):
    audit_entidad = "Portafolio"
    audit_id_kwarg = "pk"
    @transaction.atomic
    def get(self, request, pk):
        return Response(resumen_portafolio(visible(request, pk, bloquear=True)))
