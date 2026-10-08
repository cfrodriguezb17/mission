from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MinLengthValidator
from rest_framework import serializers

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
            candidate.username = candidate.email
            try:
                validate_password(attrs["password"], user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance
