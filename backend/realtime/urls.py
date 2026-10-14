from django.urls import path
from . import views

urlpatterns = [
    path('resumen/', views.resumen, name='realtime-summary'),
    path('stream/', views.stream, name='realtime-stream'),
]
