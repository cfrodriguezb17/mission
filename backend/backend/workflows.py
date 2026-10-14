"""Coordinación explícita sin dependencias cíclicas entre módulos."""
from economics.services import actualizar_tipos_cambio, sincronizar_indicadores
from risk.services import recalcular_riesgos
from alerts.services import generar_alertas
from audit.services import registrar_resultado


def _recalcular(result):
    result["riesgos"] = recalcular_riesgos(result["paises_procesados"])
    result["recalculo_pendiente"] = bool(result["riesgos"]["errores"])
    codes = set(result["paises_procesados"]) | {item["pais"] for item in result["errores"] if item.get("pais")}
    result["alertas"] = generar_alertas(result["riesgos"]["calculados"], result.get("datos_nuevos", []), paises=codes)
    result["alertas_pendientes"] = bool(result["alertas"]["errores"] or result["alertas"].get("pendientes")
                                        or result["recalculo_pendiente"])
    result["recalculo_y_alertas_pendientes"] = result["alertas_pendientes"]
    if result["recalculo_pendiente"] or result["alertas_pendientes"]:
        result["estado"] = "PARCIAL"
    return result


def _auditar(result, operacion, entidad, usuario, ip):
    errors = len(result.get("errores", [])) + len(result.get("riesgos", {}).get("errores", []))
    errors += len(result.get("alertas", {}).get("errores", []))
    detalle = {"operacion": operacion, "origen": "HTTP" if usuario else "COMANDO",
               "estado": "PARCIAL" if errors or result.get("estado") == "PARCIAL"
                   or result.get("alertas_pendientes") else "COMPLETO", "errores": errors}
    if "paises_procesados" in result:
        detalle["paises"] = result["paises_procesados"]
    for key in ("creados", "actualizados"):
        if key in result:
            detalle[key] = result[key]
    detalle["calculados"] = len(result.get("calculados", result.get("riesgos", {}).get("calculados", [])))
    return registrar_resultado(result, usuario=usuario, accion="EDITAR", entidad=entidad, ip=ip, detalle=detalle)


def sincronizar_y_recalcular(*, usuario=None, ip=None, **kwargs):
    result = _recalcular(sincronizar_indicadores(**kwargs))
    return _auditar(result, "sync_indicadores", "IndicadorEconomico", usuario, ip)


def actualizar_y_recalcular(*, usuario=None, ip=None, **kwargs):
    result = _recalcular(actualizar_tipos_cambio(**kwargs))
    return _auditar(result, "update_tipos_cambio", "TipoCambio", usuario, ip)


def recalcular_con_alertas(*, usuario=None, ip=None, **kwargs):
    result = recalcular_riesgos(**kwargs)
    result["alertas"] = generar_alertas(result["calculados"], paises=kwargs.get("paises"))
    result["alertas_pendientes"] = bool(result["errores"] or result["alertas"]["errores"]
                                        or result["alertas"].get("pendientes"))
    return _auditar(result, "calcular_riesgos", "IndiceRiesgo", usuario, ip)
