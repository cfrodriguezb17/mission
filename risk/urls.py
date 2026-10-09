from django.urls import path

from .views import CalcularView, DetalleView, HistoricoView, RankingView

app_name = "risk"
urlpatterns = [
    path("", RankingView.as_view(), name="ranking"),
    path("calcular/", CalcularView.as_view(), name="calcular"),
    path("<str:codigo_iso>/", DetalleView.as_view(), name="detalle"),
    path("<str:codigo_iso>/historico/", HistoricoView.as_view(), name="historico"),
]
