from django.db import migrations, models
from django.db.models import OuterRef, Subquery
from django.utils import timezone


def preparar_indices_existentes(apps, schema_editor):
    Indice = apps.get_model("risk", "IndiceRiesgo")
    rows = Indice.objects.using(schema_editor.connection.alias)
    # Política de corte: no reenviar todo el histórico anterior. Conservar la
    # revisión del último índice por país que hacía el recuperador previo,
    # incluyendo países inactivos. Fecha/id resuelve empates determinísticamente.
    latest = rows.filter(pais_id=OuterRef("pais_id")).order_by("-fecha_calculo", "-pk").values("pk")[:1]
    rows.exclude(pk=Subquery(latest)).update(fecha_alertas_procesadas=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("risk", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="indiceriesgo", name="fecha_alertas_procesadas",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(preparar_indices_existentes, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="indiceriesgo",
            index=models.Index(fields=["fecha_calculo", "id"],
                               condition=models.Q(fecha_alertas_procesadas__isnull=True),
                               name="riesgo_alertas_pendientes_idx"),
        ),
    ]
