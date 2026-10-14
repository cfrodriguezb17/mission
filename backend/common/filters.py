from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter


class StrictOrderingFilter(OrderingFilter):
    """Devuelve 400 en vez de ignorar ordenamientos vacíos o no admitidos."""

    def get_ordering(self, request, queryset, view):
        params = request.query_params.get(self.ordering_param)
        if params is not None and not params.strip():
            raise ValidationError({self.ordering_param: "Campos de ordenamiento inválidos."})
        return super().get_ordering(request, queryset, view)

    def remove_invalid_fields(self, queryset, fields, view, request):
        valid = super().remove_invalid_fields(queryset, fields, view, request)
        if len(valid) != len(fields):
            raise ValidationError({self.ordering_param: "Campos de ordenamiento inválidos."})
        return valid
