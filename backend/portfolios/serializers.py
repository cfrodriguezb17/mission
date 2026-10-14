from django.db.models import Prefetch, prefetch_related_objects
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from common.serializers import BooleanQueryField, StrictInputSerializer as EntradaEstricta
from countries.models import Pais

from .models import Portafolio, Posicion
from .selectors import resumen_portafolio


class VersionSerializer(EntradaEstricta):
    version = serializers.IntegerField(min_value=1, error_messages={
        "required": "Envíe la versión del portafolio.", "invalid": "La versión debe ser un entero positivo.",
        "min_value": "La versión debe ser un entero positivo.",
    })


def campo_nombre_portafolio(*, required=True):
    return serializers.CharField(min_length=3, max_length=100, required=required, trim_whitespace=True, error_messages={
        "required": "El nombre es obligatorio.", "blank": "El nombre es obligatorio.",
        "min_length": "El nombre debe tener al menos 3 caracteres.", "max_length": "El nombre no puede superar 100 caracteres.",
    })


class ValidarNombrePortafolioSerializer(EntradaEstricta):
    nombre = campo_nombre_portafolio()
    excluir = serializers.IntegerField(min_value=1, required=False, error_messages={
        "invalid": "Envíe el ID entero positivo del portafolio a editar.",
        "min_value": "Envíe el ID entero positivo del portafolio a editar.",
    })


class CrearPortafolioSerializer(EntradaEstricta):
    nombre = campo_nombre_portafolio()
    descripcion = serializers.CharField(max_length=500, allow_blank=True, required=False, default="",
                                        error_messages={"max_length": "La descripción no puede superar 500 caracteres."})
    es_publico = serializers.BooleanField(required=False, default=False)


class EditarPortafolioSerializer(VersionSerializer):
    nombre = campo_nombre_portafolio(required=False)
    descripcion = serializers.CharField(max_length=500, allow_blank=True, required=False,
                                        error_messages={"max_length": "La descripción no puede superar 500 caracteres."})
    es_publico = serializers.BooleanField(required=False)


class CrearPosicionSerializer(VersionSerializer):
    pais = serializers.PrimaryKeyRelatedField(queryset=Pais.objects.filter(activo=True), error_messages={
        "required": "El país es obligatorio.", "does_not_exist": "Seleccione un país existente y activo.",
        "incorrect_type": "Envíe el código ISO del país.",
    })
    tipo_activo = serializers.ChoiceField(choices=Posicion.TipoActivo.choices, error_messages={
        "required": "El tipo de activo es obligatorio.", "invalid_choice": "Tipo de activo inválido.",
    })
    monto_inversion_usd = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1000, max_value=10000000,
        error_messages={"required": "El monto es obligatorio.", "invalid": "Ingrese un monto numérico válido.",
                        "min_value": "El monto mínimo es 1.000 USD.", "max_value": "El monto máximo es 10.000.000 USD.",
                        "max_decimal_places": "El monto admite hasta dos decimales."})
    fecha_entrada = serializers.DateField(error_messages={"required": "La fecha de entrada es obligatoria.",
                                                         "invalid": "Use una fecha válida en formato AAAA-MM-DD."})
    fecha_salida = serializers.DateField(allow_null=True, required=False,
                                         error_messages={"invalid": "Use una fecha válida en formato AAAA-MM-DD."})
    notas = serializers.CharField(max_length=200, allow_blank=True, required=False,
                                   error_messages={"max_length": "Las notas no pueden superar 200 caracteres."})


class EditarPosicionSerializer(CrearPosicionSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("pais", "tipo_activo", "monto_inversion_usd", "fecha_entrada"):
            self.fields[field].required = False


class CerrarPosicionSerializer(VersionSerializer):
    fecha_salida = serializers.DateField(required=False,
                                         error_messages={"invalid": "Use una fecha válida en formato AAAA-MM-DD."})


class PosicionSerializer(serializers.ModelSerializer):
    pais = serializers.CharField(source="pais_id", read_only=True)
    nombre_pais = serializers.CharField(source="pais.nombre", read_only=True)

    class Meta:
        model = Posicion
        fields = ["id", "portafolio", "pais", "nombre_pais", "tipo_activo", "monto_inversion_usd",
                  "fecha_entrada", "fecha_salida", "notas"]
        read_only_fields = fields


class PosicionMutationSerializer(PosicionSerializer):
    version_portafolio = serializers.IntegerField(read_only=True)

    class Meta(PosicionSerializer.Meta):
        fields = PosicionSerializer.Meta.fields + ['version_portafolio']
        read_only_fields = fields


class DistribucionSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    monto_usd = serializers.CharField()
    porcentaje = serializers.CharField()


class ResumenPortafolioSerializer(serializers.Serializer):
    portafolio = serializers.IntegerField()
    version = serializers.IntegerField()
    total_invertido_usd = serializers.CharField()
    posiciones_activas = serializers.IntegerField()
    riesgo_promedio_ponderado = serializers.CharField(allow_null=True)
    monto_con_riesgo_usd = serializers.CharField()
    monto_sin_riesgo_usd = serializers.CharField()
    riesgo_incompleto = serializers.BooleanField()
    paises_sin_riesgo = serializers.ListField(child=serializers.CharField())
    distribucion_por_pais = DistribucionSerializer(many=True)
    distribucion_por_tipo_activo = DistribucionSerializer(many=True)
    distribucion_por_riesgo = DistribucionSerializer(many=True)


class PortafolioSerializer(serializers.ModelSerializer):
    es_propio = serializers.SerializerMethodField()
    puede_editar = serializers.SerializerMethodField()
    puede_eliminar = serializers.SerializerMethodField()
    puede_cambiar_visibilidad = serializers.SerializerMethodField()

    class Meta:
        model = Portafolio
        fields = ["id", "nombre", "descripcion", "usuario", "fecha_creacion", "fecha_modificacion", "activo",
                  "es_publico", "version", "es_propio", "puede_editar", "puede_eliminar", "puede_cambiar_visibilidad"]
        read_only_fields = fields

    def get_es_propio(self, obj) -> bool:
        return obj.usuario_id == self.context["request"].user.pk

    def get_puede_editar(self, obj) -> bool:
        user = self.context["request"].user
        return user.is_active and obj.activo and (user.rol == "ADMIN" or user.rol == "ANALISTA" and (obj.es_publico or obj.usuario_id == user.pk))

    def get_puede_eliminar(self, obj) -> bool:
        user = self.context["request"].user
        return self.get_puede_editar(obj) and (user.rol == "ADMIN" or obj.usuario_id == user.pk)

    def get_puede_cambiar_visibilidad(self, obj) -> bool:
        return self.get_puede_eliminar(obj)


class PortafolioDetailSerializer(PortafolioSerializer):
    posiciones = PosicionSerializer(many=True, read_only=True)
    resumen = serializers.SerializerMethodField()

    class Meta(PortafolioSerializer.Meta):
        fields = PortafolioSerializer.Meta.fields + ["posiciones", "resumen"]
        read_only_fields = fields

    def to_representation(self, instance):
        # Detalle y resumen comparten posiciones; el país se carga en el mismo SELECT.
        prefetch_related_objects([instance], Prefetch(
            "posiciones", queryset=Posicion.objects.select_related("pais")))
        return super().to_representation(instance)

    @extend_schema_field(ResumenPortafolioSerializer)
    def get_resumen(self, obj):
        return resumen_portafolio(obj, posiciones=obj.posiciones.all())


class PortafolioFilterSerializer(serializers.Serializer):
    es_publico = BooleanQueryField(required=False)
    propios = BooleanQueryField(required=False)
