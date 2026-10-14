"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path
from common.views import APIDocsView, APIIndexView, APINotFoundView, api_not_found, api_server_error, health

handler404 = api_not_found
handler500 = api_server_error

urlpatterns = [
    path('api/', APIIndexView.as_view(), name='api-index'),
    path('api/docs/', APIDocsView.as_view(), name='api-docs'),
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/realtime/', include('realtime.urls')),
    path('api/paises/', include('economics.urls')),
    path('api/paises/', include('countries.urls')),
    path('api/riesgo/', include('risk.urls')),
    path('api/alertas/', include('alerts.urls')),
    path('api/portafolios/', include('portfolios.urls')),
    path('api/portafolios/', include('reporting.urls')),
    path('api/dashboard/', include('dashboard.urls')),
    re_path(r'^api/.*$', APINotFoundView.as_view(), name='api-not-found'),
]
