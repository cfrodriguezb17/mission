from django.urls import path

from .views import AlertaListView, LeerTodasView, LeerView, ResumenView

app_name = "alerts"
urlpatterns = [
    path("", AlertaListView.as_view(), name="listado"),
    path("resumen/", ResumenView.as_view(), name="resumen"),
    path("leer-todas/", LeerTodasView.as_view(), name="leer-todas"),
    path("<int:pk>/leer/", LeerView.as_view(), name="leer"),
]
