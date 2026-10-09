from django.urls import path

from .views import ExportPDFView

app_name = "reporting"
urlpatterns = [path("<int:pk>/export/pdf/", ExportPDFView.as_view(), name="export-pdf")]
