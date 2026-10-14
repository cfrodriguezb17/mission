from rest_framework import serializers

from countries.models import Pais
from economics.models import TipoIndicador
from risk.presentation import color_riesgo, nivel_riesgo
from common.schema import paginated


class MapaSerializer(serializers.ModelSerializer):
    moneda_codigo = serializers.CharField(source="moneda_id", read_only=True)
    indice_compuesto = serializers.DecimalField(source="irpc", max_digits=5, decimal_places=2, allow_null=True)
    fecha_calculo = serializers.DateTimeField(source="fecha_riesgo", allow_null=True)
    datos_parciales = serializers.BooleanField(allow_null=True)
    contiene_simulaciones = serializers.BooleanField(allow_null=True)
    nivel_riesgo = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()

    class Meta:
        model = Pais
        fields = ["codigo_iso", "nombre", "moneda_codigo", "latitud", "longitud", "indice_compuesto",
                  "fecha_calculo", "nivel_riesgo", "color", "datos_parciales", "contiene_simulaciones"]

    def get_nivel_riesgo(self, obj) -> str:
        return nivel_riesgo(obj['irpc']) if obj['irpc'] is not None else "SIN_DATOS"

    def get_color(self, obj) -> str:
        return color_riesgo(obj['irpc']) if obj['irpc'] is not None else "#94a3b8"


class TendenciasFilterSerializer(serializers.Serializer):
    tipo = serializers.CharField(default="PIB")
    paises = serializers.CharField(default="CO,BR,MX")

    def validate_tipo(self, value):
        try:
            return TipoIndicador.objects.get(pk=value.upper())
        except TipoIndicador.DoesNotExist:
            raise serializers.ValidationError("Seleccione un tipo de indicador existente.")

    def validate_paises(self, value):
        codes = [code.strip().upper() for code in value.split(",")]
        if not 1 <= len(codes) <= 3 or any(len(code) != 2 for code in codes) or len(set(codes)) != len(codes):
            raise serializers.ValidationError("Seleccione entre uno y tres países distintos, separados por comas.")
        if set(codes) != set(Pais.objects.filter(pk__in=codes, activo=True).values_list("pk", flat=True)):
            raise serializers.ValidationError("Seleccione únicamente países existentes y activos.")
        return codes


class ResumenDashboardSerializer(serializers.Serializer):
    total_paises = serializers.IntegerField()
    promedio_irpc = serializers.CharField(allow_null=True)
    paises_con_riesgo = serializers.IntegerField()
    paises_con_datos_parciales = serializers.IntegerField()
    alertas_activas = serializers.IntegerField()
    portafolios_usuario = serializers.IntegerField()


class ObservacionSerializer(serializers.Serializer):
    anio = serializers.IntegerField()
    valor = serializers.CharField(allow_null=True)
    fuente = serializers.CharField(allow_null=True)
    es_simulado = serializers.BooleanField(allow_null=True)


class SerieTendenciaSerializer(serializers.Serializer):
    pais = serializers.CharField()
    nombre_pais = serializers.CharField()
    datos_parciales = serializers.BooleanField()
    valores = ObservacionSerializer(many=True)


TendenciasResponse = paginated('Tendencias', SerieTendenciaSerializer,
    tipo=serializers.CharField(), unidad=serializers.CharField(),
    anio_inicio=serializers.IntegerField(), anio_fin=serializers.IntegerField())
