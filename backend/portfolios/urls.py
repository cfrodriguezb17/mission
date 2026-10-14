from django.urls import path

from .views import (
    PortafolioDetailView, PortafolioListView, PosicionCreateView, PosicionDetailView,
    ResumenView, ValidarNombrePortafolioView,
)

app_name = "portfolios"
urlpatterns = [
    path("", PortafolioListView.as_view(), name="listado"),
    path("validar-nombre/", ValidarNombrePortafolioView.as_view(), name="validar-nombre"),
    path("<int:pk>/", PortafolioDetailView.as_view(), name="detalle"),
    path("<int:pk>/posiciones/", PosicionCreateView.as_view(), name="agregar-posicion"),
    path("<int:pk>/posiciones/<int:posicion_id>/", PosicionDetailView.as_view(), name="posicion"),
    path("<int:pk>/resumen/", ResumenView.as_view(), name="resumen"),
]
