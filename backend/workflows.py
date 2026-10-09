"""Coordinación explícita sin dependencias cíclicas entre módulos."""
from economics.services import actualizar_tipos_cambio, sincronizar_indicadores
from risk.services import recalcular_riesgos


def _recalcular(result):
    result["riesgos"] = recalcular_riesgos(result["paises_procesados"])
    result["recalculo_pendiente"] = bool(result["riesgos"]["errores"])
    result["alertas_pendientes"] = True
    # El flujo no se declara completo mientras alerts no esté implementado.
    result["recalculo_y_alertas_pendientes"] = True
    if result["recalculo_pendiente"]:
        result["estado"] = "PARCIAL"
    return result


def sincronizar_y_recalcular(**kwargs):
    return _recalcular(sincronizar_indicadores(**kwargs))


def actualizar_y_recalcular(**kwargs):
    return _recalcular(actualizar_tipos_cambio(**kwargs))
