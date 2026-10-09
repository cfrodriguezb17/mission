from django.contrib import admin

from audit.admin_mixins import AdminAuditadoMixin

from .models import IndicadorEconomico, TipoCambio, TipoIndicador


@admin.register(TipoIndicador)
class TipoIndicadorAdmin(AdminAuditadoMixin, admin.ModelAdmin):
    list_display = ("codigo", "nombre", "unidad", "codigo_world_bank")
    search_fields = ("codigo", "nombre", "codigo_world_bank")


@admin.register(IndicadorEconomico)
class IndicadorEconomicoAdmin(AdminAuditadoMixin, admin.ModelAdmin):
    list_display = ("pais", "tipo", "valor", "anio", "fuente", "es_simulado", "fecha_actualizacion")
    list_filter = ("pais", "tipo", "anio", "fuente", "es_simulado")
    list_select_related = ("pais", "tipo")
    search_fields = ("pais__nombre", "pais__codigo_iso", "tipo__codigo")
    readonly_fields = ("fecha_actualizacion",)


@admin.register(TipoCambio)
class TipoCambioAdmin(AdminAuditadoMixin, admin.ModelAdmin):
    list_display = ("moneda_origen", "moneda_destino", "tasa", "fecha", "fuente", "es_simulado")
    list_filter = ("moneda_origen", "moneda_destino", "fecha", "es_simulado")
    list_select_related = ("moneda_origen", "moneda_destino")
    search_fields = ("moneda_origen__codigo", "moneda_destino__codigo", "fuente")
