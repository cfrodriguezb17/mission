from rest_framework import serializers

from common.serializers import BooleanQueryField
from .models import Alerta


class AlertaSerializer(serializers.ModelSerializer):
    pais = serializers.CharField(source="pais_id", read_only=True)
    leida = serializers.BooleanField(read_only=True)

    class Meta:
        model = Alerta
        fields = ["id", "pais", "tipo_alerta", "severidad", "titulo", "mensaje", "fecha_creacion", "leida", "detalle"]
        read_only_fields = fields


class AlertaFilterSerializer(serializers.Serializer):
    leida = BooleanQueryField(required=False)
    tipo_alerta = serializers.ChoiceField(choices=Alerta.Tipo.choices, required=False,
                                        error_messages={"invalid_choice": "Tipo de alerta inválido."})
    severidad = serializers.ChoiceField(choices=Alerta.Severidad.choices, required=False,
                                      error_messages={"invalid_choice": "Severidad inválida."})
