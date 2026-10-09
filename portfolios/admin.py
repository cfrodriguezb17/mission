from django.contrib import admin

from .models import Portafolio, Posicion
from .selectors import portafolios_visibles


class SoloConsultaAdmin(admin.ModelAdmin):
    # Las escrituras usan la API para no saltarse versión, permisos ni límites.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Portafolio)
class PortafolioAdmin(SoloConsultaAdmin):
    list_display = ["nombre", "usuario", "es_publico", "activo", "version", "fecha_modificacion"]
    list_filter = ["es_publico", "activo"]
    search_fields = ["nombre", "usuario__email"]
    readonly_fields = [field.name for field in Portafolio._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=portafolios_visibles(request.user).values("pk"))


@admin.register(Posicion)
class PosicionAdmin(SoloConsultaAdmin):
    list_display = ["portafolio", "pais", "tipo_activo", "monto_inversion_usd", "fecha_entrada", "fecha_salida"]
    list_filter = ["tipo_activo", "pais"]
    readonly_fields = [field.name for field in Posicion._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(portafolio__in=portafolios_visibles(request.user))
