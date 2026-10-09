"""Coordinación explícita sin dependencias cíclicas entre módulos."""
from economics.services import actualizar_tipos_cambio, sincronizar_indicadores
from risk.services import recalcular_riesgos
from alerts.services import generar_alertas


def _recalcular(result):
    result["riesgos"] = recalcular_riesgos(result["paises_procesados"])
    result["recalculo_pendiente"] = bool(result["riesgos"]["errores"])
    result["alertas"] = generar_alertas(result["riesgos"]["calculados"], result.get("datos_nuevos", []))
    result["alertas_pendientes"] = bool(result["alertas"]["errores"] or result["recalculo_pendiente"])
    result["recalculo_y_alertas_pendientes"] = result["alertas_pendientes"]
    if result["recalculo_pendiente"] or result["alertas_pendientes"]:
        result["estado"] = "PARCIAL"
    return result


def sincronizar_y_recalcular(**kwargs):
    return _recalcular(sincronizar_indicadores(**kwargs))


def actualizar_y_recalcular(**kwargs):
    return _recalcular(actualizar_tipos_cambio(**kwargs))


def recalcular_con_alertas(**kwargs):
    result = recalcular_riesgos(**kwargs)
    result["alertas"] = generar_alertas(result["calculados"])
    result["alertas_pendientes"] = bool(result["errores"] or result["alertas"]["errores"])
    return result
