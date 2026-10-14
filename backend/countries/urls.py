from django.urls import path

from .views import PaisDetailView, PaisListView

app_name = "countries"

urlpatterns = [
    path("", PaisListView.as_view(), name="list"),
    path("<str:codigo_iso>/", PaisDetailView.as_view(), name="detail"),
]
