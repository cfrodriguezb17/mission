from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from audit.mixins import ConsultaAuditadaMixin

from .serializers import LoginSerializer, ProfileSerializer, RefreshSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


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
