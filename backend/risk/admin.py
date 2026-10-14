from django.contrib import admin

from .models import IndiceRiesgo


@admin.register(IndiceRiesgo)
class IndiceRiesgoAdmin(admin.ModelAdmin):
    list_display = ["pais", "fecha_calculo", "indice_compuesto", "nivel_riesgo", "version_formula"]
    list_filter = ["pais", "version_formula"]
    search_fields = ["pais__codigo_iso", "pais__nombre"]
    # Las instantáneas históricas se consultan; no se inventan ni alteran en admin.
    readonly_fields = [field.name for field in IndiceRiesgo._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
