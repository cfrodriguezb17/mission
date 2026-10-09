from django.contrib import admin

from .models import Moneda, Pais


@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ("codigo_iso", "nombre", "moneda", "region", "poblacion", "activo")
    list_filter = ("region", "activo", "moneda")
    search_fields = ("codigo_iso", "nombre")
    list_select_related = ("moneda",)
