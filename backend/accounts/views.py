from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiExample
from audit.mixins import ConsultaAuditadaMixin

from .serializers import LoginSerializer, ProfileSerializer, RefreshSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


@extend_schema_view(post=extend_schema(
    request=LoginSerializer, responses={200: inline_serializer('TokenPair', {
        'access': serializers.CharField(), 'refresh': serializers.CharField()})},
    summary='Iniciar sesión y obtener JWT', examples=[OpenApiExample('Cuenta DEMO ANALISTA',
        value={'email': 'analista@datapulse.com', 'password': 'DataPulse2026!'}, request_only=True)]))
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


@extend_schema_view(post=extend_schema(
    request=RefreshSerializer, responses={200: inline_serializer('AccessToken', {'access': serializers.CharField()})}))
class RefreshView(TokenRefreshView):
    serializer_class = RefreshSerializer


class ProfileView(ConsultaAuditadaMixin, generics.RetrieveUpdateAPIView):
    audit_entidad = "Usuario"
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "put", "head", "options"]

    def get_object(self):
        # El cliente nunca elige el ID del perfil que modifica.
        return self.request.user
