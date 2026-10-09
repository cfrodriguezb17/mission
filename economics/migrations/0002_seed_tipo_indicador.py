from django.db import migrations


def seed_catalog(apps, schema_editor):
    TipoIndicador = apps.get_model("economics", "TipoIndicador")
    # Datos congelados: una migración histórica no importa el catálogo vigente.
    rows = (
        ("PIB", "Producto interno bruto", "USD", "NY.GDP.MKTP.CD"),
        ("INFLACION", "Inflación anual", "PORCENTAJE", "FP.CPI.TOTL.ZG"),
        ("DESEMPLEO", "Desempleo", "PORCENTAJE", "SL.UEM.TOTL.ZS"),
        ("BALANZA_COMERCIAL", "Balanza comercial / PIB", "PORCENTAJE", "NE.RSB.GNFS.ZS"),
        ("DEUDA_PIB", "Deuda del gobierno / PIB", "PORCENTAJE", "GC.DOD.TOTL.GD.ZS"),
        ("PIB_PERCAPITA", "PIB per cápita", "USD", "NY.GDP.PCAP.CD"),
    )
    for code, name, unit, wb in rows:
        TipoIndicador.objects.using(schema_editor.connection.alias).get_or_create(
            codigo=code, defaults={"nombre": name, "unidad": unit, "codigo_world_bank": wb},
        )


class Migration(migrations.Migration):
    dependencies = [("economics", "0001_initial")]
    operations = [migrations.RunPython(seed_catalog, reverse_code=migrations.RunPython.noop)]
