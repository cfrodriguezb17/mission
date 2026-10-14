from django.conf import settings
from django.db import models


class LogActividad(models.Model):
    class Accion(models.TextChoices):
        CREAR = "CREAR", "Crear"
        EDITAR = "EDITAR", "Editar"
        ELIMINAR = "ELIMINAR", "Eliminar"
        CONSULTAR = "CONSULTAR", "Consultar"
        LOGIN = "LOGIN", "Login"
        EXPORT = "EXPORT", "Exportar"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="actividad")
    accion = models.CharField(max_length=9, choices=Accion.choices)
    entidad_afectada = models.CharField(max_length=100)
    entidad_id = models.CharField(max_length=100, blank=True, default="")
    detalle = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["usuario", "fecha"], name="audit_usuario_fecha_idx"),
            models.Index(fields=["entidad_afectada", "entidad_id", "fecha"], name="audit_entidad_fecha_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(accion__in=[
                "CREAR", "EDITAR", "ELIMINAR", "CONSULTAR", "LOGIN", "EXPORT",
            ]), name="audit_accion_valida"),
            models.CheckConstraint(condition=~models.Q(entidad_afectada=""), name="audit_entidad_no_vacia"),
        ]

    def __str__(self):
        return f"{self.accion} {self.entidad_afectada} {self.entidad_id}"
