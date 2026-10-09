from django.contrib import admin

from .models import LogActividad


@admin.register(LogActividad)
class LogActividadAdmin(admin.ModelAdmin):
    list_display = ["fecha", "usuario", "accion", "entidad_afectada", "entidad_id", "ip_address"]
    list_filter = ["accion", "entidad_afectada"]
    search_fields = ["entidad_id", "usuario__email"]
    readonly_fields = [field.name for field in LogActividad._meta.fields]

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.rol == "ADMIN" and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if request.user.rol == "ADMIN" else queryset.none()
