from django.db.models import OuterRef, Subquery

from .models import IndiceRiesgo


def ultimos_indices():
    latest = IndiceRiesgo.objects.filter(pais_id=OuterRef("pais_id")).order_by("-fecha_calculo", "-pk")
    return IndiceRiesgo.objects.filter(pais__activo=True, pk=Subquery(latest.values("pk")[:1])).select_related("pais")


def historico_pais(pais):
    return IndiceRiesgo.objects.filter(pais=pais).select_related("pais")
