from django.db import transaction

from .services import CAMPOS, obtener_ip, registrar_actividad


class AdminAuditadoMixin:
    def _registrar(self, request, obj, accion, campos=()):
        registrar_actividad(usuario=request.user, accion=accion,
                            entidad="Usuario" if obj._meta.label_lower == "accounts.user" else obj._meta.object_name,
                            entidad_id=obj.pk, ip=obtener_ip(request),
                            detalle={"operacion": "admin", "origen": "ADMIN",
                                     "campos": sorted(set(campos) & CAMPOS)})

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._registrar(request, obj, "EDITAR" if change else "CREAR", form.changed_data)

    @transaction.atomic
    def delete_model(self, request, obj):
        self._registrar(request, obj, "ELIMINAR")
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._registrar(request, obj, "ELIMINAR")
        super().delete_queryset(request, queryset)
