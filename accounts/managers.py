from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        # Identidad sin distinción de mayúsculas en toda la dirección.
        return super().normalize_email(email.strip() if email else "").lower()

    @classmethod
    def validate_email(cls, email):
        email = cls.normalize_email(email)
        if not email:
            raise ValidationError("El email es obligatorio.")
        validate_email(email)
        if len(email) > 254:
            raise ValidationError("El email no puede superar 254 caracteres.")
        return email

    def get_by_natural_key(self, username):
        return self.get(email=self.normalize_email(username))

    def _create_user(self, email, password, **extra_fields):
        email = self.validate_email(email)
        extra_fields.pop("username", None)
        name = extra_fields.get("nombre_completo", "").strip()
        if not name:
            raise ValidationError({"nombre_completo": "El nombre completo es obligatorio."})
        extra_fields["nombre_completo"] = name
        user = self.model(email=email, username=email, **extra_fields)
        if password is not None:
            validate_password(password, user=user)
        user.set_password(password)
        user.full_clean(validate_unique=False, validate_constraints=False)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        for flag in ("is_staff", "is_superuser", "is_active"):
            if extra_fields.get(flag) is not True:
                raise ValueError(f"Un superusuario debe tener {flag}=True.")
        if not password:
            raise ValueError("Un superusuario debe tener contraseña.")
        # REQUIRED_FIELDS está vacío: el comando no solicita nombre completo.
        extra_fields.setdefault("nombre_completo", self.normalize_email(email))
        return self._create_user(email, password, **extra_fields)
