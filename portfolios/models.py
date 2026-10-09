from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual
from django.utils import timezone


class Portafolio(models.Model):
    nombre = models.CharField(max_length=100, validators=[
        MinLengthValidator(3, message="El nombre debe tener al menos 3 caracteres."),
    ])
    descripcion = models.TextField(blank=True, validators=[
        MaxLengthValidator(500, message="La descripción no puede superar 500 caracteres."),
    ])
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="portafolios")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)
    es_publico = models.BooleanField(default=False)
    version = models.PositiveBigIntegerField(default=1)

    class Meta:
        ordering = ["-fecha_modificacion", "-pk"]
        verbose_name = "portafolio"
        verbose_name_plural = "portafolios"
        indexes = [
            models.Index(fields=["usuario", "activo"], name="portfolio_usuario_activo_idx"),
            models.Index(fields=["es_publico", "activo"], name="portfolio_publico_activo_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "nombre"], name="portafolio_usuario_nombre_uq"),
            models.CheckConstraint(condition=models.Q(nombre__regex=r"^.{3,100}$") & models.Q(nombre__regex=r"\S"),
                                   name="portafolio_nombre_valido"),
            models.CheckConstraint(condition=LessThanOrEqual(Length("descripcion"), 500),
                                   name="portafolio_descripcion_valida"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="portafolio_version_positiva"),
        ]

    def __str__(self):
        return self.nombre


class Posicion(models.Model):
    class TipoActivo(models.TextChoices):
        RENTA_FIJA = "RENTA_FIJA", "Renta fija"
        RENTA_VARIABLE = "RENTA_VARIABLE", "Renta variable"
        COMMODITIES = "COMMODITIES", "Commodities"
        MONEDA = "MONEDA", "Moneda"

    portafolio = models.ForeignKey(Portafolio, on_delete=models.PROTECT, related_name="posiciones")
    pais = models.ForeignKey("countries.Pais", on_delete=models.PROTECT, related_name="posiciones")
    tipo_activo = models.CharField(max_length=14, choices=TipoActivo.choices)
    monto_inversion_usd = models.DecimalField(max_digits=12, decimal_places=2, validators=[
        MinValueValidator(Decimal("1000"), message="El monto mínimo es 1.000 USD."),
        MaxValueValidator(Decimal("10000000"), message="El monto máximo es 10.000.000 USD."),
    ])
    fecha_entrada = models.DateField()
    fecha_salida = models.DateField(null=True, blank=True)
    notas = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha_entrada", "-pk"]
        verbose_name = "posición"
        verbose_name_plural = "posiciones"
        indexes = [models.Index(fields=["portafolio", "pais", "tipo_activo"],
                                condition=models.Q(fecha_salida__isnull=True), name="posicion_activa_combo_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(tipo_activo__in=["RENTA_FIJA", "RENTA_VARIABLE", "COMMODITIES", "MONEDA"]),
                                   name="posicion_tipo_valido"),
            models.CheckConstraint(condition=models.Q(monto_inversion_usd__gte=1000, monto_inversion_usd__lte=10000000),
                                   name="posicion_monto_valido"),
            models.CheckConstraint(condition=models.Q(fecha_salida__isnull=True) | models.Q(fecha_salida__gt=models.F("fecha_entrada")),
                                   name="posicion_salida_posterior"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.fecha_entrada and self.fecha_entrada > timezone.localdate():
            errors["fecha_entrada"] = "La fecha de entrada no puede ser futura."
        if self.fecha_salida and self.fecha_entrada and self.fecha_salida <= self.fecha_entrada:
            errors["fecha_salida"] = "La salida debe ser posterior a la entrada."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.portafolio_id} / {self.pais_id} / {self.tipo_activo}"
