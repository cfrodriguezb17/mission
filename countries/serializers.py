from rest_framework import serializers
from economics.serializers import IndicadorSerializer

from .models import Pais


class PaisSerializer(serializers.ModelSerializer):
    moneda_codigo = serializers.CharField(source="moneda.codigo", read_only=True)
    moneda_nombre = serializers.CharField(source="moneda.nombre", read_only=True)

    class Meta:
        model = Pais
        fields = [
            "codigo_iso", "nombre", "moneda_codigo", "moneda_nombre", "region",
            "latitud", "longitud", "poblacion", "bandera_url", "activo",
        ]
        read_only_fields = fields


class PaisValuesSerializer(PaisSerializer):
    moneda_codigo = serializers.CharField(source="moneda_id", read_only=True)
    moneda_nombre = serializers.CharField(source="moneda__nombre", read_only=True)


class PaisDetailSerializer(PaisSerializer):
    indicadores = IndicadorSerializer(many=True, read_only=True)

    class Meta(PaisSerializer.Meta):
        fields = PaisSerializer.Meta.fields + ["indicadores"]
        read_only_fields = fields
