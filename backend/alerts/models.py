import uuid

from django.conf import settings
from django.db import models


def event_key():
    return uuid.uuid4().hex


class Alerta(models.Model):
    class Tipo(models.TextChoices):
        RIESGO = "RIESGO", "Riesgo"
        TIPO_CAMBIO = "TIPO_CAMBIO", "Tipo de cambio"
        INDICADOR = "INDICADOR", "Indicador"

    class Severidad(models.TextChoices):
        INFO = "INFO", "Información"
        WARNING = "WARNING", "Advertencia"
        CRITICAL = "CRITICAL", "Crítica"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.PROTECT, related_name="alertas")
    pais = models.ForeignKey("countries.Pais", on_delete=models.PROTECT, related_name="alertas")
    tipo_alerta = models.CharField(max_length=11, choices=Tipo.choices)
    severidad = models.CharField(max_length=8, choices=Severidad.choices)
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    clave_evento = models.CharField(max_length=64, unique=True, default=event_key, editable=False)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fecha_creacion", "-id"]
        indexes = [models.Index(fields=["usuario", "fecha_creacion"], name="alerta_usuario_fecha_idx"),
                   models.Index(fields=["tipo_alerta", "severidad"], name="alerta_tipo_severidad_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(tipo_alerta__in=["RIESGO", "TIPO_CAMBIO", "INDICADOR"]), name="alerta_tipo_valido"),
            models.CheckConstraint(condition=models.Q(severidad__in=["INFO", "WARNING", "CRITICAL"]), name="alerta_severidad_valida"),
            models.CheckConstraint(condition=models.Q(titulo__regex=r"\S"), name="alerta_titulo_no_vacio"),
            models.CheckConstraint(condition=models.Q(mensaje__regex=r"\S"), name="alerta_mensaje_no_vacio"),
        ]

    def __str__(self):
        return self.titulo


class LecturaAlerta(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecturas_alertas")
    alerta = models.ForeignKey(Alerta, on_delete=models.CASCADE, related_name="lecturas")
    fecha_lectura = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["usuario", "alerta"], name="lectura_usuario_alerta_unica")]
