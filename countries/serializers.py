from rest_framework import serializers

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
