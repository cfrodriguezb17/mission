from django.utils import timezone
from rest_framework import serializers

from common.serializers import DateRangeFilterSerializer as FechaFilterSerializer, StrictInputSerializer

# FechaFilterSerializer conserva el import público anterior del módulo.
from .catalog import COUNTRY_CODES, INDICATORS
from .models import IndicadorEconomico, TipoCambio
from .selectors import variacion_porcentual


YEAR_ERRORS = {
    "invalid": "Use un año entero válido.",
    "min_value": "El año debe ser mayor o igual a 1.",
    "max_value": "El año debe ser menor o igual a 9999.",
}


class IndicadorSerializer(serializers.ModelSerializer):
    pais = serializers.CharField(source="pais_id", read_only=True)
    tipo = serializers.CharField(source="tipo_id", read_only=True)
    unidad = serializers.CharField(source="tipo.unidad", read_only=True)

    class Meta:
        model = IndicadorEconomico
        fields = ["id", "pais", "tipo", "valor", "unidad", "anio", "fuente", "es_simulado", "fecha_actualizacion"]
        read_only_fields = fields


class TipoCambioSerializer(serializers.ModelSerializer):
    moneda_origen = serializers.CharField(source="moneda_origen_id", read_only=True)
    moneda_destino = serializers.CharField(source="moneda_destino_id", read_only=True)
    variacion_porcentual = serializers.SerializerMethodField()
    dato_anterior_faltante = serializers.SerializerMethodField()

    class Meta:
        model = TipoCambio
        fields = ["id", "moneda_origen", "moneda_destino", "tasa", "fecha", "variacion_porcentual",
                  "dato_anterior_faltante", "fuente", "es_simulado"]
        read_only_fields = fields

    def get_variacion_porcentual(self, obj):
        value = variacion_porcentual(obj.tasa, obj.tasa_anterior)
        return str(value) if value is not None else None

    def get_dato_anterior_faltante(self, obj):
        return obj.tasa_anterior is None


class IndicadorFilterSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=[r[0] for r in INDICATORS], required=False,
                                   error_messages={"invalid_choice": "Tipo de indicador inválido."})
    anio = serializers.IntegerField(min_value=1, max_value=9999, required=False, error_messages=YEAR_ERRORS)


class SyncSerializer(StrictInputSerializer):
    unknown_field_message = "Parámetro no admitido."
    paises = serializers.ListField(child=serializers.ChoiceField(choices=COUNTRY_CODES),
                                   min_length=1, max_length=10, required=False)
    anio_inicio = serializers.IntegerField(min_value=1, max_value=9999, required=False, error_messages=YEAR_ERRORS)
    anio_fin = serializers.IntegerField(min_value=1, max_value=9999, required=False, error_messages=YEAR_ERRORS)

    def validate(self, attrs):
        end = attrs.setdefault("anio_fin", timezone.now().year - 1)
        start = attrs.setdefault("anio_inicio", end - 4)
        if end > timezone.now().year or start > end or end - start > 19 or start < 1:
            raise serializers.ValidationError("Use un rango de hasta 20 años, ordenado y sin años futuros.")
        if "paises" in attrs:
            attrs["paises"] = list(dict.fromkeys(attrs["paises"]))
        return attrs
