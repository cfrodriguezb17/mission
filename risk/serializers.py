from rest_framework import serializers

from common.serializers import StrictInputSerializer
from .models import IndiceRiesgo
from countries.models import Pais


class CalcularSerializer(StrictInputSerializer):
    unknown_field_message = "Parámetro no admitido."
    paises = serializers.ListField(child=serializers.CharField(min_length=2, max_length=2),
                                   min_length=1, max_length=10, required=False)

    def validate(self, attrs):
        if "paises" in attrs:
            codes = list(dict.fromkeys(code.upper() for code in attrs["paises"]))
            existing = set(Pais.objects.filter(pk__in=codes, activo=True).values_list("pk", flat=True))
            if set(codes) - existing:
                raise serializers.ValidationError({"paises": "Seleccione únicamente países existentes y activos."})
            attrs["paises"] = codes
        return attrs


class IndiceRiesgoSerializer(serializers.ModelSerializer):
    pais = serializers.CharField(source="pais_id", read_only=True)
    nombre_pais = serializers.CharField(source="pais.nombre", read_only=True)
    nivel_riesgo = serializers.CharField(read_only=True)
    color = serializers.CharField(read_only=True)

    class Meta:
        model = IndiceRiesgo
        fields = ["id", "pais", "nombre_pais", "fecha_calculo", "score_economico", "score_cambiario",
                  "score_estabilidad", "indice_compuesto", "nivel_riesgo", "color", "version_formula", "detalle_calculo"]
        read_only_fields = fields
