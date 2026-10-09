from django.contrib import admin

from audit.admin_mixins import AdminAuditadoMixin

from .models import Moneda, Pais


@admin.register(Moneda)
class MonedaAdmin(AdminAuditadoMixin, admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(Pais)
class PaisAdmin(AdminAuditadoMixin, admin.ModelAdmin):
    list_display = ("codigo_iso", "nombre", "moneda", "region", "poblacion", "activo")
    list_filter = ("region", "activo", "moneda")
    search_fields = ("codigo_iso", "nombre")
    list_select_related = ("moneda",)
