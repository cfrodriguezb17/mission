from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class Moneda(models.Model):
    codigo = models.CharField(
        primary_key=True, max_length=3,
        validators=[RegexValidator(r"^[A-Z]{3}$", "El código de moneda debe tener 3 letras mayúsculas.")],
    )
    nombre = models.CharField(max_length=100)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "moneda"
        verbose_name_plural = "monedas"
        constraints = [
            models.CheckConstraint(condition=models.Q(codigo__regex=r"^[A-Z]{3}$"), name="moneda_codigo_valido"),
            models.CheckConstraint(condition=models.Q(nombre__regex=r"\S"), name="moneda_nombre_no_vacio"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


class Pais(models.Model):
    class Region(models.TextChoices):
        ANDINA = "ANDINA", "Andina"
        CONO_SUR = "CONO_SUR", "Cono Sur"
        CENTROAMERICA = "CENTROAMERICA", "Centroamérica"
        CARIBE = "CARIBE", "Caribe"

    codigo_iso = models.CharField(
        primary_key=True, max_length=2,
        validators=[RegexValidator(r"^[A-Z]{2}$", "El código ISO debe tener 2 letras mayúsculas.")],
    )
    nombre = models.CharField(max_length=100)
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, related_name="paises")
    region = models.CharField(max_length=13, choices=Region.choices, db_index=True)
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-90, message="La latitud mínima es -90."),
                    MaxValueValidator(90, message="La latitud máxima es 90.")],
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-180, message="La longitud mínima es -180."),
                    MaxValueValidator(180, message="La longitud máxima es 180.")],
    )
    poblacion = models.PositiveBigIntegerField()
    bandera_url = models.URLField(max_length=500, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre", "codigo_iso"]
        verbose_name = "país"
        verbose_name_plural = "países"
        constraints = [
            models.CheckConstraint(condition=models.Q(codigo_iso__regex=r"^[A-Z]{2}$"), name="pais_codigo_valido"),
            models.CheckConstraint(condition=models.Q(nombre__regex=r"\S"), name="pais_nombre_no_vacio"),
            models.CheckConstraint(condition=models.Q(region__in=["ANDINA", "CONO_SUR", "CENTROAMERICA", "CARIBE"]), name="pais_region_valida"),
            models.CheckConstraint(condition=models.Q(latitud__gte=-90, latitud__lte=90), name="pais_latitud_valida"),
            models.CheckConstraint(condition=models.Q(longitud__gte=-180, longitud__lte=180), name="pais_longitud_valida"),
        ]

    def __str__(self):
        return f"{self.codigo_iso} — {self.nombre}"
