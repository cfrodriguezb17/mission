from django.urls import path

from .views import MapaView, ResumenView, TendenciasView

app_name = "dashboard"
urlpatterns = [
    path("resumen/", ResumenView.as_view(), name="resumen"),
    path("mapa/", MapaView.as_view(), name="mapa"),
    path("tendencias/", TendenciasView.as_view(), name="tendencias"),
]
