from django.contrib import admin

from .models import Alerta, LecturaAlerta
from .selectors import alertas_visibles


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ["titulo", "pais", "usuario", "tipo_alerta", "severidad", "fecha_creacion"]
    list_filter = ["tipo_alerta", "severidad", "pais"]
    search_fields = ["titulo", "pais__codigo_iso"]
    readonly_fields = [field.name for field in Alerta._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=alertas_visibles(request.user).values("pk"))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LecturaAlerta)
class LecturaAlertaAdmin(AlertaAdmin):
    list_display = ["usuario", "alerta", "fecha_lectura"]
    list_filter = []
    search_fields = ["alerta__titulo"]
    readonly_fields = [field.name for field in LecturaAlerta._meta.fields]

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request).filter(usuario=request.user)
