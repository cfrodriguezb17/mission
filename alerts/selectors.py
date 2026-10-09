from django.db.models import Exists, OuterRef, Q

from .models import Alerta, LecturaAlerta


def alertas_visibles(usuario):
    return Alerta.objects.filter(Q(usuario__isnull=True) | Q(usuario=usuario)).annotate(
        leida=Exists(LecturaAlerta.objects.filter(usuario=usuario, alerta_id=OuterRef("pk"))))
