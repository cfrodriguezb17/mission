from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class IndiceRiesgo(models.Model):
    pais = models.ForeignKey("countries.Pais", on_delete=models.PROTECT, related_name="indices_riesgo")
    fecha_calculo = models.DateTimeField(default=timezone.now, editable=False)
    score_economico = models.DecimalField(max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    score_cambiario = models.DecimalField(max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    score_estabilidad = models.DecimalField(max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    indice_compuesto = models.DecimalField(max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    version_formula = models.CharField(max_length=100)
    detalle_calculo = models.JSONField()
    # NULL conserva el trabajo pendiente junto al cálculo, incluso sin reglas.
    fecha_alertas_procesadas = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-fecha_calculo", "-id"]
        verbose_name = "índice de riesgo"
        verbose_name_plural = "índices de riesgo"
        indexes = [models.Index(fields=["pais", "fecha_calculo"], name="riesgo_pais_fecha_idx"),
                   models.Index(fields=["fecha_calculo", "id"],
                                condition=models.Q(fecha_alertas_procesadas__isnull=True),
                                name="riesgo_alertas_pendientes_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(**{f"{field}__gte": 0, f"{field}__lte": 100}),
                                   name=f"riesgo_{field}_rango")
            for field in ("score_economico", "score_cambiario", "score_estabilidad", "indice_compuesto")
        ] + [models.CheckConstraint(condition=models.Q(version_formula__regex=r"\S"),
                                    name="riesgo_version_no_vacia")]

    @property
    def nivel_riesgo(self):
        if self.indice_compuesto >= Decimal("75"):
            return "BAJO"
        if self.indice_compuesto >= Decimal("50"):
            return "MODERADO"
        if self.indice_compuesto >= Decimal("25"):
            return "ALTO"
        return "CRITICO"

    @property
    def color(self):
        return {"BAJO": "#22c55e", "MODERADO": "#eab308", "ALTO": "#f97316", "CRITICO": "#ef4444"}[self.nivel_riesgo]

    def __str__(self):
        return f"{self.pais_id} / {self.fecha_calculo} / {self.indice_compuesto}"
