from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .catalog import INDICATORS


class TipoIndicador(models.Model):
    class Unidad(models.TextChoices):
        USD = "USD", "USD"
        PORCENTAJE = "PORCENTAJE", "Porcentaje"

    codigo = models.CharField(primary_key=True, max_length=20,
                              choices=[(row[0], row[1]) for row in INDICATORS])
    nombre = models.CharField(max_length=100)
    unidad = models.CharField(max_length=10, choices=Unidad.choices)
    codigo_world_bank = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "tipo de indicador"
        verbose_name_plural = "tipos de indicador"
        constraints = [
            models.CheckConstraint(condition=models.Q(codigo__in=[r[0] for r in INDICATORS]), name="tipo_indicador_codigo_valido"),
            models.CheckConstraint(condition=models.Q(unidad__in=["USD", "PORCENTAJE"]), name="tipo_indicador_unidad_valida"),
            models.CheckConstraint(condition=models.Q(nombre__regex=r"\S"), name="tipo_indicador_nombre_no_vacio"),
            models.CheckConstraint(condition=models.Q(codigo_world_bank__regex=r"\S"), name="tipo_indicador_wb_no_vacio"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


class IndicadorEconomico(models.Model):
    class Fuente(models.TextChoices):
        WORLD_BANK = "WORLD_BANK", "World Bank"
        MANUAL = "MANUAL", "Manual"

    pais = models.ForeignKey("countries.Pais", on_delete=models.PROTECT, related_name="indicadores")
    tipo = models.ForeignKey(TipoIndicador, on_delete=models.PROTECT, related_name="observaciones")
    valor = models.DecimalField(max_digits=24, decimal_places=6)
    anio = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(9999)])
    fuente = models.CharField(max_length=10, choices=Fuente.choices)
    es_simulado = models.BooleanField(default=False)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-anio", "tipo_id", "id"]
        verbose_name = "indicador económico"
        verbose_name_plural = "indicadores económicos"
        constraints = [
            models.UniqueConstraint(fields=["pais", "tipo", "anio"], name="indicador_pais_tipo_anio_unico"),
            models.CheckConstraint(condition=models.Q(anio__gte=1, anio__lte=9999), name="indicador_anio_valido"),
            models.CheckConstraint(condition=models.Q(fuente__in=["WORLD_BANK", "MANUAL"]), name="indicador_fuente_valida"),
            models.CheckConstraint(condition=models.Q(es_simulado=False) | models.Q(fuente="MANUAL"), name="indicador_simulado_manual"),
        ]

    def __str__(self):
        return f"{self.pais_id} / {self.tipo_id} / {self.anio}"


class TipoCambio(models.Model):
    moneda_origen = models.ForeignKey("countries.Moneda", on_delete=models.PROTECT, related_name="cotizaciones_origen")
    moneda_destino = models.ForeignKey("countries.Moneda", default="USD", on_delete=models.PROTECT, related_name="cotizaciones_destino")
    tasa = models.DecimalField(max_digits=24, decimal_places=12,
                               validators=[MinValueValidator(Decimal("0.000000000001"))])
    fecha = models.DateField()
    fuente = models.CharField(max_length=50)
    es_simulado = models.BooleanField(default=False)
    # Cero identifica registros previos; cada escritura efectiva del proveedor
    # avanza la revisión bajo el bloqueo de moneda, incluso en transiciones A→B→A.
    revision = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-fecha", "id"]
        verbose_name = "tipo de cambio"
        verbose_name_plural = "tipos de cambio"
        constraints = [
            models.UniqueConstraint(fields=["moneda_origen", "moneda_destino", "fecha"], name="cambio_par_fecha_unico"),
            models.CheckConstraint(condition=models.Q(tasa__gt=0), name="cambio_tasa_positiva"),
            models.CheckConstraint(condition=~models.Q(moneda_origen=models.F("moneda_destino")), name="cambio_monedas_distintas"),
            models.CheckConstraint(condition=models.Q(fuente__regex=r"\S"), name="cambio_fuente_no_vacia"),
        ]

    def __str__(self):
        return f"{self.moneda_origen_id} → {self.moneda_destino_id} / {self.fecha}"


class LoteActualizacion(models.Model):
    """Evidencia persistente de un cambio económico pendiente de notificación."""

    pais = models.ForeignKey("countries.Pais", on_delete=models.PROTECT, related_name="lotes_actualizacion")
    clave_evento = models.CharField(max_length=64, unique=True, editable=False)
    datos = models.JSONField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_alerta = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["pais", "id"], condition=models.Q(fecha_alerta__isnull=True),
                               name="lote_pendiente_pais_idx")]
        constraints = [models.CheckConstraint(condition=~models.Q(datos=[]), name="lote_datos_no_vacios")]
