# Alertas y lecturas — implementado el 8 de octubre de 2026

`Alerta` guarda país, destinatario opcional, tipo, severidad, título, mensaje y
fecha. Destinatario null = global; otro valor = privada. `LecturaAlerta` guarda
usuario, alerta y fecha, con unicidad (usuario, alerta): completa el tercer
ajuste principal de normalización. No hay columna `leida` en Alerta.

La base protege países y destinatarios privados con PROTECT: eliminar un
usuario no convierte sus alertas en globales. Las lecturas usan CASCADE al
eliminar su usuario o alerta. Checks de tipos, severidades y textos no vacíos;
índices (usuario, fecha_creacion) y (tipo_alerta, severidad).

## API

JWT obligatorio. Los tres roles pueden consultar y marcar sus lecturas; ni
ADMIN ni superusuario Django amplían la visibilidad de alertas privadas. El
admin es de consulta, con las mismas restricciones de destinatario, y solo
muestra las lecturas del propio usuario. No permite editar destinatarios,
crear lecturas ajenas ni alterar evidencia.

| Método | Ruta | Respuesta |
| --- | --- | --- |
| GET | `/api/alertas/` | Listado paginado de globales y privadas propias, con `leida` calculada mediante Exists para ese usuario. |
| PUT | `/api/alertas/{id}/leer/` | Alerta con leida=true. Repetir conserva la fecha original de lectura. |
| PUT | `/api/alertas/leer-todas/` | `{"marcadas": N}` de lecturas nuevas. Repetir devuelve cero si no aparecieron alertas nuevas. |
| GET | `/api/alertas/resumen/` | total, no_leidas, por_tipo y por_severidad; cada grupo contiene total/no_leidas, incluidos ceros. |

Filtros: `leida=true|false`, `tipo_alerta=RIESGO|TIPO_CAMBIO|INDICADOR`,
`severidad=INFO|WARNING|CRITICAL`. `ordering`: fecha_creacion, tipo_alerta,
severidad, pais e id; admite prefijo `-`. Orden predeterminado fecha/id
descendente. `page_size` 20 por defecto, máximo 100; respuesta count/next/
previous/results. Parámetros inválidos: 400; sin JWT: 401; alerta privada ajena
o inexistente: 404. El cuerpo de lectura no modifica los atributos de Alerta.
No hay endpoint de creación, edición o eliminación de alertas.

Lecturas individuales y masivas bloquean al usuario para serializar requests
simultáneos. Leer todas afecta las alertas visibles en ese momento; una alerta
creada después seguirá sin leer. El listado usa una subconsulta Exists y no
hace una consulta adicional por alerta.

## Generación automática

`backend.workflows` coordina sync → IRPC → alertas. El recálculo administrativo
por API o comando también genera alertas. Los módulos economics y risk siguen
sin importar alerts: sus servicios básicos solo persisten sus datos.

| Regla | Tipo | Severidad |
| --- | --- | --- |
| IRPC <25 | RIESGO | CRITICAL |
| Caída estrictamente >15 puntos frente al cálculo anterior | RIESGO | WARNING |
| Magnitud de variación diaria estrictamente >3 % | TIPO_CAMBIO | WARNING |
| Inflación estrictamente >50 % | INDICADOR | CRITICAL |
| Datos creados o actualizados realmente durante sincronización | INDICADOR o TIPO_CAMBIO | INFO |

Las alertas automáticas son globales. Inflación, IRPC y cotizaciones proceden
de la instantánea histórica de cada cálculo. Caída compara con su predecesor
por fecha/id, incluso si se reintenta un cálculo antiguo. Datos ausentes no se
convierten en cero y no generan una comparación inventada. La evidencia conserva
procedencia y marcas de simulación cuando están presentes.

La regla cambiaria interpreta el umbral como **magnitud absoluta**: se alerta
tanto apreciación como depreciación porque el par local → USD produce cambios
negativos al depreciarse. Se compara la última cotización de la instantánea
con el día calendario anterior del mismo par, sin saltar huecos; no se evalúa
otra fecha como sustituto. USD/USD no tiene cotizaciones persistidas y no genera
alertas cambiarias. Se usa Decimal y se evalúa el umbral antes del redondeo.

INFO se agrupa en una alerta por país/lote. Economics expone `datos_nuevos`
solo para escrituras efectivas, con su evidencia; datos sin cambios, manuales
conservados, ausentes o transacciones revertidas no generan INFO.

## Idempotencia y fallos

Alerta incorpora `clave_evento` única (SHA-256 del país, destinatario, regla y
evidencia canónica) y `detalle` JSON. Para creación manual desde código la
clave predeterminada es UUID. La restricción única y bloqueos por país evitan
duplicados en reintentos o ejecuciones simultáneas.

- IRPC crítico: versión, resultado y entradas; repetir un cálculo idéntico no
  repite la alerta. Una evidencia diferente puede generar otra.
- Inflación: observación usada (año, valor, fuente y actualización).
- Caída: transición entre los dos ids de cálculo y sus valores.
- Cambio: cotización actual/anterior, par, fecha y variación.
- INFO: lote ordenado de datos efectivamente modificados.

La respuesta de workflows añade `alertas={creadas, errores}`. Tras éxito,
alertas_pendientes y recalculo_y_alertas_pendientes son false; ante errores de
riesgo o alertas siguen true y la sincronización queda PARCIAL. Los comandos
devuelven salida distinta de cero ante esos errores. Se conservan los datos
económicos y cálculos ya guardados; un fallo de generación no los revierte.

```bash
python manage.py migrate
python manage.py generar_alertas
python manage.py generar_alertas --paises CO EC
python manage.py calcular_riesgos --paises CO EC
python manage.py test alerts --noinput
python manage.py verify_migrations
python manage.py verify_migrations --fresh
```

`generar_alertas` reintenta el último cálculo por país activo. Para reintentar
un cálculo anterior o un lote INFO fallido, reutilizar la respuesta original
guardada de sincronización con el servicio público `generar_alertas(indices,
datos_nuevos)`. No existe una cola ni reintento persistente automático en esta
etapa: repetir la sincronización sin cambios no reconstruye el lote INFO.
WebSockets siguen siendo una extensión opcional; la recuperación y lectura
de alertas ya funcionan por REST.
