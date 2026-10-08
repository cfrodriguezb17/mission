from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Rol(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        ANALISTA = "ANALISTA", "Analista"
        VIEWER = "VIEWER", "Viewer"

    # Conservamos username como identificador interno y admitimos emails largos.
    username = models.CharField(max_length=254, unique=True, editable=False)
    email = models.EmailField(unique=True, blank=False)
    nombre_completo = models.CharField(max_length=255)
    rol = models.CharField(max_length=8, choices=Rol.choices, default=Rol.VIEWER)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, db_column="activo")

    # Los campos de negocio reemplazan los equivalentes heredados.
    first_name = None
    last_name = None
    date_joined = None

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def clean(self):
        super().clean()
        self.email = type(self).objects.validate_email(self.email)
        self.username = self.email

    def save(self, *args, **kwargs):
        self.email = type(self).objects.validate_email(self.email)
        self.username = self.email
        if kwargs.get("update_fields") is not None:
            fields = set(kwargs["update_fields"])
            if "email" in fields or "username" in fields:
                fields.update({"email", "username"})
            kwargs["update_fields"] = fields
        return super().save(*args, **kwargs)

    def get_full_name(self):
        return self.nombre_completo

    def get_short_name(self):
        return self.nombre_completo.split()[0] if self.nombre_completo else self.email

    def __str__(self):
        return self.email
