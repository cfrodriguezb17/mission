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
- INFO: lote ordenado de datos efectivamente modificados. Para cotizaciones,
  cada dato incluye `id` y `revision`; la revisión forma parte del hash tanto
  del lote como de la alerta. Tasas A → B → A producen tres INFO distintos.

La respuesta de workflows añade `alertas={creadas, errores, pendientes}`. Tras éxito,
alertas_pendientes y recalculo_y_alertas_pendientes son false; ante errores de
riesgo o alertas, o trabajos sin procesar, siguen true y la sincronización queda PARCIAL. Los comandos
devuelven salida distinta de cero ante esos errores o trabajos todavía pendientes. Se conservan los datos
económicos y cálculos ya guardados; un fallo de generación no los revierte.

```bash
python manage.py migrate
python manage.py generar_alertas
python manage.py generar_alertas --paises CO EC
python manage.py generar_alertas --limite 1000
python manage.py calcular_riesgos --paises CO EC
python manage.py test alerts --noinput
python manage.py verify_migrations
python manage.py verify_migrations --fresh
```

`economics.LoteActualizacion` conserva un lote por país con su evidencia original,
clave única, fecha de creación y fecha de entrega. Se guarda dentro de la misma
transacción que los indicadores/cotizaciones: si no se puede registrar, se
revierte ese país/par. Datos simulados del seed no producen lotes ficticios.
Economics no importa alerts. Una moneda compartida guarda una sola cotización
y registra un lote por cada país afectado.

La alerta y `fecha_alerta` se confirman en otra transacción común. Si falla la
creación o el marcador, ambos se revierten y el lote sigue pendiente. Los
bloqueos siguen el orden país → lote; productores de cotizaciones bloquean
países ordenados → moneda, compatible con risk. Dos recuperaciones simultáneas
no duplican la alerta. Los lotes entregados conservan su evidencia y no se
reenvían al repetir datos.

`economics.0004_tipo_cambio_revision` añade `TipoCambio.revision`, entero no
negativo con valor inicial cero para registros existentes. `guardar_cotizacion`
lo incrementa solo al guardar un cambio efectivo, bajo los mismos bloqueos y
en la transacción de la cotización y sus lotes. El evento conserva esa revisión;
reintentar la entrega nunca la incrementa. Consultas sin cambios y cotizaciones
manuales conservadas no crean revisiones ni lotes. Una moneda compartida usa la
misma revisión en los lotes de todos los países afectados.

La migración conserva claves, evidencia y marcadores de los lotes y alertas
previos. Los lotes antiguos pendientes siguen recuperables con su clave
original; los entregados no se reenvían. No reconstruye revisiones ni INFO
perdidos antes del cambio. La [evidencia de B01](../../docs/backend-b01-20261010/README.md)
separa la verificación funcional de la comprobación pendiente en PostgreSQL.

`risk.0002_indice_alertas_procesadas` añade un marcador nullable a cada índice.
NULL significa trabajo pendiente: se inserta junto al cálculo en su misma
transacción. `generar_para_indice` bloquea país → índice, vuelve a consultar el
marcador y confirma **todas** las alertas del índice y el marcador en una sola
transacción. También marca índices sin reglas activadas. Si falla una regla o
el marcador, se revierten todos sus eventos y el índice sigue pendiente.
Las claves de evidencia existentes no cambian. Dos trabajadores no evalúan ni
entregan de nuevo un índice ya procesado.

`generar_alertas` recupera índices pendientes, incluidos históricos, y lotes
INFO, también de países inactivos. No requiere ids ni respuestas originales.
`--paises` limita selección y conteo; sin filtro atiende todos los países.
Sincronizaciones posteriores, incluso sin cambios, recuperan ambos tipos en
sus países procesados o con error identificado. El recálculo también recupera
el histórico pendiente de su alcance.

El contrato conserva `alertas={creadas, errores, pendientes}`. **`pendientes`
ahora suma índices sin procesar y lotes INFO sin entregar** del alcance, después
de los intentos. Un índice puede producir cero o varias alertas: este conteo
mide trabajos, no notificaciones. `errores` identifica `pais` y `indice` o `lote`
con un mensaje seguro. `alertas_pendientes` considera esa suma y los errores de
riesgo/generación; `recalculo_y_alertas_pendientes` la refleja en sincronizaciones.

El presupuesto común predeterminado es **100 trabajos**; `--limite` admite
1–1000. Se ordenan índices por fecha_calculo/id y lotes por fecha_creacion/id,
y se toman los más antiguos del conjunto. Empates entre tipos priorizan índice.
Cada candidato ocupa un turno aunque falle o no active reglas. No se reintenta
dos veces dentro de la misma ejecución. Si quedan trabajos o errores, el
comando imprime el JSON y sale con error; hay que repetirlo. El límite acota
trabajos por invocación, no el número de alertas ni el total de varios workers.
Puede programarse en el scheduler del servidor; no se instaló ni activó uno
local. La cola es PostgreSQL y no requiere Redis.

**Política de migración de índices anteriores:** se preservan todas las filas,
instantáneas y alertas. Los índices previos, salvo el último de cada país, se
marcan con la fecha de migración como excluidos de revisión retrospectiva; este
marcador no acredita una entrega anterior. Solo el último por fecha/id queda
pendiente, también en países inactivos, para conservar la revisión que hacía
el recuperador previo. Puede emitir eventos si su evidencia no fue entregada.
No se recuperan automáticamente caídas antiguas anteriores a ese corte; evita
una avalancha de notificaciones. Todos los índices creados después del cambio
son recuperables aun cuando haya cálculos posteriores. Aplicar la migración
con los productores/recuperadores detenidos y desplegar el código nuevo antes
de reanudarlos. No regenerar ni borrar migraciones aplicadas.

La migración `economics.0003_lotes_actualizacion` crea almacenamiento adicional,
sin modificar datos anteriores. No reconstruye alertas perdidas antes de esta
mejora: solo una evidencia histórica conservada permite registrarlas mediante
`generar_alertas(datos_nuevos=...)`. Las referencias `indices=...` siguen
admitidas para validar ids, pero no eluden el filtro, el marcador ni el límite;
no reabren índices procesados o excluidos por la migración. Los resúmenes de
auditoría fallidos conservan su limitación previa. WebSockets sigue siendo una
extensión opcional. [Evidencia de B02](../../docs/backend-b02-20261010/README.md).
