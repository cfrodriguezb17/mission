from django.urls import path

from .views import IndicadorListView, SyncIndicadoresView, TipoCambioListView

app_name = "economics"
urlpatterns = [
    path("sync-indicadores/", SyncIndicadoresView.as_view(), name="sync-indicadores"),
    path("<str:codigo_iso>/indicadores/", IndicadorListView.as_view(), name="indicadores"),
    path("<str:codigo_iso>/tipo-cambio/", TipoCambioListView.as_view(), name="tipo-cambio"),
]
