from collections.abc import Mapping

from rest_framework import serializers


class StrictInputSerializer(serializers.Serializer):
    """Entrada JSON estricta; los filtros query pueden ignorar otros parámetros."""
    unknown_field_message = "Campo no admitido."

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: self.unknown_field_message for key in sorted(unknown)})
        return super().to_internal_value(data)


class BooleanQueryField(serializers.ChoiceField):
    """Filtro que admite únicamente las cadenas true/false y devuelve bool."""

    def __init__(self, **kwargs):
        kwargs.setdefault("error_messages", {"invalid_choice": "Use true o false."})
        super().__init__(choices=["true", "false"], **kwargs)

    def to_internal_value(self, data):
        return super().to_internal_value(data) == "true"


class DateRangeFilterSerializer(serializers.Serializer):
    fecha_inicio = serializers.DateField(required=False, input_formats=["%Y-%m-%d"],
                                         error_messages={"invalid": "Use una fecha válida con formato AAAA-MM-DD."})
    fecha_fin = serializers.DateField(required=False, input_formats=["%Y-%m-%d"],
                                     error_messages={"invalid": "Use una fecha válida con formato AAAA-MM-DD."})

    def validate(self, attrs):
        if "fecha_inicio" in attrs and "fecha_fin" in attrs and attrs["fecha_inicio"] > attrs["fecha_fin"]:
            raise serializers.ValidationError({"fecha_fin": "Debe ser igual o posterior a fecha_inicio."})
        return attrs
