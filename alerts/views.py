from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from common.filters import StrictOrderingFilter
from common.pagination import StandardPagination

from .models import Alerta
from .selectors import alertas_visibles
from .serializers import AlertaFilterSerializer, AlertaSerializer
from .services import leer_alerta, leer_todas


class AlertaListView(generics.ListAPIView):
    serializer_class = AlertaSerializer
    pagination_class = StandardPagination
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["fecha_creacion", "tipo_alerta", "severidad", "pais", "id"]
    ordering = ["-fecha_creacion", "-id"]

    def get_queryset(self):
        params = AlertaFilterSerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        return alertas_visibles(self.request.user).filter(**params.validated_data)


class LeerView(APIView):
    def put(self, request, pk):
        alerta = get_object_or_404(alertas_visibles(request.user), pk=pk)
        leer_alerta(request.user, alerta.pk)
        alerta.leida = True
        return Response(AlertaSerializer(alerta).data)


class LeerTodasView(APIView):
    def put(self, request):
        return Response({"marcadas": leer_todas(request.user)})


class ResumenView(APIView):
    def get(self, request):
        queryset = alertas_visibles(request.user)
        totals = queryset.aggregate(total=Count("pk"), no_leidas=Count("pk", filter=Q(leida=False)))
        def group(field, choices):
            values = {row[field]: {"total": row["total"], "no_leidas": row["no_leidas"]}
                      for row in queryset.order_by().values(field).annotate(
                          total=Count("pk"), no_leidas=Count("pk", filter=Q(leida=False)))}
            return {value: values.get(value, {"total": 0, "no_leidas": 0}) for value in choices}
        return Response({**totals, "por_tipo": group("tipo_alerta", Alerta.Tipo.values),
                         "por_severidad": group("severidad", Alerta.Severidad.values)})
