from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MinLengthValidator
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from audit.services import obtener_ip, registrar_actividad

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    activo = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "nombre_completo", "rol", "fecha_creacion",
            "activo", "password",
        ]
        read_only_fields = ["id", "rol", "fecha_creacion"]
        extra_kwargs = {
            # La unicidad se comprueba después de normalizar la dirección.
            "email": {
                "required": True,
                "allow_blank": False,
                "allow_null": False,
                "validators": [],
            },
            "password": {
                "write_only": True,
                "required": True,
                "trim_whitespace": False,
                "validators": [MinLengthValidator(
                    6, message="La contraseña debe tener al menos 6 caracteres.",
                )],
            },
        }

    def validate_email(self, value):
        try:
            value = User.objects.validate_email(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        users = User.objects.filter(email=value)
        if self.instance is not None:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise serializers.ValidationError("Ya existe un usuario con este email.")
        return value

    def validate(self, attrs):
        if "password" in attrs:
            candidate = User(
                email=attrs.get("email", getattr(self.instance, "email", "")),
                nombre_completo=attrs.get(
                    "nombre_completo", getattr(self.instance, "nombre_completo", ""),
                ),
            )
            try:
                validate_password(attrs["password"], user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                user = User.objects.create_user(**validated_data)
                registrar_actividad(usuario=user, accion="CREAR", entidad="Usuario", entidad_id=user.pk,
                                    detalle={"operacion": "registro"}, ip=obtener_ip(self.context.get("request")))
                return user
        except IntegrityError:
            # También devolver un error de campo ante registros concurrentes.
            self.validate_email(validated_data["email"])
            raise

    def update(self, instance, validated_data):
        data = dict(validated_data)
        password = data.pop("password", None)
        try:
            with transaction.atomic():
                try:
                    current = User.objects.select_for_update().get(pk=instance.pk)
                except User.DoesNotExist as exc:
                    raise AuthenticationFailed("El usuario ya no existe.") from exc
                # request.user se leyó al autenticar; revalidar tras adquirir el bloqueo.
                if not current.is_active or current.password != instance.password:
                    raise AuthenticationFailed("La cuenta o la contraseña ha cambiado. Inicia sesión de nuevo.")
                for field, value in data.items():
                    setattr(current, field, value)
                fields = list(data)
                if password is not None:
                    current.set_password(password)
                    fields.append("password")
                # No escribir rol, activación ni privilegios desde la copia anterior.
                current.save(update_fields=fields)
                registrar_actividad(usuario=current, accion="EDITAR", entidad="Usuario", entidad_id=current.pk,
                                    detalle={"operacion": "perfil", "campos": sorted(data),
                                             "credenciales_actualizadas": password is not None},
                                    ip=obtener_ip(self.context.get("request")))
        except IntegrityError:
            self.validate_email(data.get("email", instance.email))
            raise
        return current


class ProfileSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        extra_kwargs = {
            **UserSerializer.Meta.extra_kwargs,
            "password": {
                **UserSerializer.Meta.extra_kwargs["password"],
                "required": False,
            },
        }


class LoginSerializer(TokenObtainPairSerializer):
    default_error_messages = {
        "no_active_account": "Email o contraseña incorrectos, o cuenta inactiva.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"] = serializers.EmailField(write_only=True)
        self.fields["password"].trim_whitespace = False

    def validate_email(self, value):
        return User.objects.validate_email(value)

    @transaction.atomic
    def validate(self, attrs):
        result = super().validate(attrs)
        registrar_actividad(usuario=self.user, accion="LOGIN", entidad="Usuario", entidad_id=self.user.pk,
                            detalle={"operacion": "login"}, ip=obtener_ip(self.context.get("request")))
        return result


class RefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.get(api_settings.USER_ID_CLAIM)
        if user_id is None:
            raise InvalidToken("El token no identifica a un usuario.")
        try:
            user = User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("El usuario ya no existe.") from exc
        if api_settings.CHECK_REVOKE_TOKEN and refresh.get(
            api_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise AuthenticationFailed("La contraseña ha cambiado. Inicia sesión de nuevo.")
        return super().validate(attrs)
