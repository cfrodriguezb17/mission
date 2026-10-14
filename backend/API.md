# Contrato de API - DataPulse Latam

## Swagger y OpenAPI

- `/api/swagger/`: interfaz interactiva, con recursos estáticos servidos por el backend.
- `/api/schema/`: contrato OpenAPI 3 en JSON, generado a partir de vistas y serializers.
- `/api/docs/`: este documento en JSON, conservado por compatibilidad.

En Swagger, ejecutar `POST /api/auth/login/` con una cuenta DEMO, copiar `access`,
abrir **Authorize** y pegar solo el token, sin el prefijo Bearer. La autorización
no persiste al recargar. Los permisos y límites de la API también se aplican a
Swagger. Las operaciones de escritura modifican datos reales de la instalación.
Los DELETE de portafolios/posiciones requieren el cuerpo JSON con `version`.
El esquema describe HTTP/SSE; el protocolo WebSocket se documenta al final de
esta guía. CI valida OpenAPI y falla ante advertencias de generación.

```bash
python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
```

Base: `/api/`. JSON UTF-8. Excepto registro, login, refresh, índice y documentación,
se exige `Authorization: Bearer <access>`. ADMIN, ANALISTA y VIEWER consultan;
las escrituras y objetos se restringen como se indica abajo. `/health/` consulta
conectividad con PostgreSQL y devuelve 200 o 503 sin publicar configuración.

## Autenticación

| Método | Endpoint | Entrada / resultado |
| --- | --- | --- |
| POST | `/auth/register/` | `email`, `nombre_completo`, `password`; crea VIEWER activo (201). |
| POST | `/auth/login/` | `email`, `password`; devuelve `access` y `refresh`. |
| POST | `/auth/refresh/` | `refresh`; devuelve nuevo `access`. |
| GET | `/auth/me/` | Perfil propio. |
| PUT | `/auth/me/` | `email` y `nombre_completo` obligatorios; `password` opcional. No permite cambiar rol ni privilegios. |

Access dura 5 minutos y refresh un día. Una contraseña cambiada o una cuenta
inactiva revocan el acceso; refresh no rota. Email normalizado a minúsculas.
Registro/perfil aplican validadores de contraseña (mínimo 6 caracteres, similitud,
contraseñas comunes y solo numéricas). No se devuelven contraseñas ni hashes.

La actualización del perfil bloquea y vuelve a consultar al usuario antes de
guardar. Conserva cambios simultáneos de rol/privilegios y solo escribe los
campos editables enviados. Si la cuenta se desactivó o cambió su contraseña
después de autenticar la petición, devuelve 401 sin guardar el perfil ni su
evento de edición; hay que iniciar sesión de nuevo. Dos cambios simultáneos
de contraseña autenticados con las mismas credenciales no se sobrescriben:
uno puede completar y el otro se rechaza con 401.

## Países y datos económicos

| Método | Endpoint | Filtros / permisos |
| --- | --- | --- |
| GET | `/paises/` | `region`, `search`, `ordering`, `page`, `page_size`. |
| GET | `/paises/{codigo_iso}/` | País activo, moneda e indicadores. |
| GET | `/paises/{codigo_iso}/indicadores/` | `tipo`, `anio`, `ordering`, paginación. |
| GET | `/paises/{codigo_iso}/tipo-cambio/` | `fecha_inicio`, `fecha_fin`, `ordering`, paginación. Par local -> USD. |
| POST | `/paises/sync-indicadores/` | Solo ADMIN; cuerpo opcional `paises`, `anio_inicio`, `anio_fin`; presupuesto HTTP de 25 segundos. |

Tipos: PIB, INFLACION, DESEMPLEO, BALANZA_COMERCIAL, DEUDA_PIB, PIB_PERCAPITA.
PIB y PIB per cápita se expresan en USD, los otros en PORCENTAJE. Decimales
serializados como cadenas. `es_simulado` identifica demostraciones.
Fechas ISO `AAAA-MM-DD`, inclusivas. USD/USD es identidad calculada para Ecuador;
no es una cotización descargada ni se almacena. Variación diaria nula cuando
falta el día calendario anterior. La sincronización conserva datos manuales
reales y puede reemplazar simulaciones; informa errores por país y etapas
pendientes de riesgo, alertas y auditoría. Si falla todo devuelve 503.

## Riesgo

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/riesgo/` | Último índice por país activo; orden predeterminado IRPC descendente. Paginado. |
| GET | `/riesgo/{codigo_iso}/` | `ultimo` sin filtros e `historico` paginado; filtros de fechas sobre el histórico. |
| GET | `/riesgo/{codigo_iso}/historico/` | `fecha_inicio`, `fecha_fin`, `ordering`, paginación. |
| POST | `/riesgo/calcular/` | Solo ADMIN; `{}` para todos o `{"paises":["CO","EC"]}`; genera alertas y auditoría. |

Ranking añade `variacion` en puntos frente al cálculo anterior (no porcentaje)
y `tendencia`: MEJORA, EMPEORA, ESTABLE o SIN_HISTORICO. Un IRPC creciente
representa menor riesgo. Empates de fecha se resuelven por id descendente.
Se exponen tres scores, compuesto, nivel, color, versión y evidencia histórica.
Ausencia de índice no equivale a cero; revisar `detalle_calculo.datos_parciales`
y `contiene_simulaciones`, incluso con un compuesto alto.

## Alertas

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/alertas/` | Globales y privadas propias; `leida=true/false`, `tipo_alerta`, `severidad`, `ordering`, paginación. |
| PUT | `/alertas/{id}/leer/` | Marca lectura exclusivamente para el usuario autenticado. |
| PUT | `/alertas/leer-todas/` | Marca todas las visibles; operación idempotente. |
| GET | `/alertas/resumen/` | Conteos por tipo/severidad y no leídas del usuario. |

Una alerta privada ajena nunca es visible, tampoco para ADMIN. Las lecturas
globales son independientes por usuario. Se generan alertas por IRPC crítico,
caídas superiores a 15 puntos, magnitud cambiaria estrictamente superior a 3 %,
inflación superior a 50 % y nuevos datos tras sincronización. Clave de evento
única evita duplicados por la misma evidencia.

Los lotes INFO y el trabajo de alertas de cada índice se guardan junto con sus
datos económicos o cálculo. Se recuperan después de un fallo, incluso si hay
índices posteriores o la siguiente sincronización no modifica valores.
Las respuestas de sincronización/recálculo incluyen
`alertas={creadas, errores, pendientes}`; `pendientes` suma **índices sin procesar
y lotes INFO sin entregar** del alcance después de los intentos. Cuenta trabajos,
no alertas; un índice sin reglas también requiere procesamiento. `errores`
identifica `pais` y `indice` o `lote`, con mensaje seguro. El cliente debe comprobar
`alertas_pendientes`, que también considera errores de generación/riesgo.
Las sincronizaciones reflejan ese flag en `recalculo_y_alertas_pendientes` y
quedan PARCIAL si resta trabajo. El presupuesto común es 100 trabajos por
invocación, por antigüedad. El comando `generar_alertas --limite 1000` admite
1–1000 y recupera ambos tipos sin reenviar evidencia ni ids; `--paises` limita
selección/conteo, incluidos países inactivos. Emite JSON y sale con error si
restan trabajos o hay errores. [Política de migración y detalles](alerts/README.md).
No añade endpoints ni cambia la privacidad de las lecturas.

En actualizaciones cambiarias, cada elemento de `datos_nuevos` incluye
`revision` (entero) junto al `id` de la cotización. La revisión identifica una
escritura efectiva y forma parte de la evidencia INFO: tasas A → B → A generan
tres eventos distintos, aunque compartan par y fecha. Reintentar una entrega
reutiliza la revisión persistida; una consulta sin cambios no crea otra.

## Portafolios y posiciones

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/portafolios/` | Propios y públicos; ADMIN consulta todos. `search`, `es_publico`, `propios`, `ordering`, paginación. |
| POST | `/portafolios/` | ADMIN/ANALISTA; `nombre`, `descripcion` opcional, `es_publico` opcional. |
| GET | `/portafolios/validar-nombre/` | ADMIN/ANALISTA; `nombre` obligatorio, `excluir` opcional (ID del portafolio a editar); devuelve nombre recortado y disponibilidad. |
| GET | `/portafolios/{id}/` | Datos, posiciones y resumen. |
| PUT | `/portafolios/{id}/` | `version` obligatoria más campos a modificar. |
| DELETE | `/portafolios/{id}/` | `version` obligatoria; eliminación lógica; solo propietario con escritura o ADMIN. |
| POST | `/portafolios/{id}/posiciones/` | `version`, `pais`, `tipo_activo`, `monto_inversion_usd`, `fecha_entrada`; `fecha_salida` y `notas` opcionales. |
| PUT | `/portafolios/{id}/posiciones/{id}/` | `version` y campos a modificar. |
| DELETE | `/portafolios/{id}/posiciones/{id}/` | `version` y `fecha_salida` opcional; cierra sin borrar fila. |
| GET | `/portafolios/{id}/resumen/` | Capital activo, riesgo ponderado y distribuciones por país, activo y riesgo. |
| GET | `/portafolios/{id}/export/pdf/` | Permiso de lectura; `application/pdf`, descarga `portafolio-{id}.pdf`, caché privada deshabilitada. |

ANALISTA edita propios y públicos; ADMIN todos; VIEWER nunca modifica. Cambiar
visibilidad o eliminar exige propietario con permiso de escritura o ADMIN.
Nombre único por propietario, 3-100 caracteres; descripción hasta 500.
Montos entre 1.000 y 10.000.000 USD, dos decimales; fecha de entrada no futura,
salida estrictamente posterior, notas hasta 200 caracteres. Máximo dos posiciones
activas por país/tipo en un portafolio y 50.000.000 USD de capital activo.
MONEDA no se admite para países cuya moneda principal es USD.

### Validación asíncrona del nombre

```http
GET /api/portafolios/validar-nombre/?nombre=Latam
Authorization: Bearer <access>
```

```json
{"nombre": "Latam", "disponible": true}
```

`nombre` usa la misma validación que crear/editar: se recortan espacios extremos
y luego se exige longitud 3–100. La comparación distingue mayúsculas (`Latam`
y `latam` son diferentes). Un nombre ocupado devuelve 200 con `disponible: false`,
incluidos los portafolios eliminados. Sin `excluir`, consulta solo al propietario
autenticado; otros usuarios pueden usar ese mismo nombre.

Al editar, enviar `?nombre=Latam&excluir=42`. `excluir` debe ser un entero positivo
que identifique un portafolio activo editable por el actor. Se omite únicamente
ese registro y se usa su propietario real, también al editar un público ajeno o
cuando ADMIN edita un privado ajeno. El resultado solo comunica disponibilidad;
no devuelve datos del portafolio que ocupa el nombre.

Solo se admiten los parámetros `nombre` y `excluir`; no hay selección libre de
usuario/propietario. Entrada inválida o parámetros desconocidos: 400 con el
sobre de errores habitual; sin JWT: 401; VIEWER: 403 para un alcance visible;
ID inexistente, eliminado o privado ajeno no accesible: 404.
La consulta no crea registros, no cambia versiones y responde con
`Cache-Control: private, no-store`. Aplica el límite general de solicitudes.

Contrato para el formulario: consultar después de la validación local y una
pausa breve al escribir; cancelar o descartar respuestas de nombres anteriores.
En edición enviar siempre el ID original como `excluir`. Mostrar duplicado solo
si responde 200 con `disponible: false`; un fallo de red, 401/403/404 o 429 no
equivale a nombre libre. La consulta **no reserva** el nombre: POST/PUT mantienen
validación y restricción única, y pueden devolver 400 en `nombre` si otra petición
ocupa el nombre antes de guardar. Conservar también el tratamiento de versión 409.
El frontend aplica este contrato al crear y editar; no infiere unicidad desde
el listado de portafolios activos.

Toda modificación envía la versión del portafolio; posiciones comparten esa
versión. Un éxito la incrementa. Conflicto devuelve 409; recargar y revisar antes
de reenviar. El resumen pondera solo posiciones activas con riesgo disponible;
informa capital/países sin índice. PDF incluye activas y cerradas, distribuciones,
scores, fechas y señales de simulación/datos incompletos; registra EXPORT.

## Dashboard

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/dashboard/resumen/` | `total_paises`, `alertas_activas` (no leídas visibles), `portafolios_usuario` (propios activos), `promedio_irpc`, `paises_con_riesgo`, `paises_con_datos_parciales`. |
| GET | `/dashboard/mapa/` | Países activos con coordenadas, moneda, último IRPC, fecha, nivel, color y señales de evidencia. Paginado; `ordering=codigo_iso,nombre,irpc` con prefijo `-` por campo. |
| GET | `/dashboard/tendencias/` | `tipo=PIB` por defecto, `paises=CO,BR,MX` por defecto; entre uno y tres códigos distintos separados por comas. Paginado por país; `ordering=codigo_iso` o `nombre`. |

El promedio regional usa únicamente el último índice de cada país activo y es
null si no hay índices. Los países sin cálculo aparecen en mapa con IRPC/fecha
null, nivel SIN_DATOS y color gris `#94a3b8`; nunca se dibujan como riesgo cero.
Tendencias cubre los últimos cinco años UTC completos, excluyendo el actual.
Devuelve `tipo`, `unidad`, `anio_inicio`, `anio_fin` y el sobre paginado; cada
resultado contiene `pais`, `nombre_pais`, `datos_parciales` y cinco `valores`
con año, valor, fuente y es_simulado. Un año ausente tiene valor/fuente/señal
null; un valor económico cero se conserva.

## Contratos transversales

Listados usan `count`, `next`, `previous`, `results`; `page_size` por defecto 20,
máximo 100. Ordenamientos inválidos devuelven 400; `search` está disponible en países y
portafolios. Booleanos query
aceptan las cadenas exactas `true` y `false`.

Errores incluyen `error: {codigo, mensaje, detalles}`. Por compatibilidad se
conservan además los campos de validación originales al nivel superior:

```json
{
  "ordering": "Campos de ordenamiento inválidos.",
  "error": {
    "codigo": "validacion",
    "mensaje": "Revise los datos enviados.",
    "detalles": {"ordering": "Campos de ordenamiento inválidos."}
  }
}
```

Códigos HTTP principales: 400 validación, 401 autenticación, 403 permisos,
404 recurso inexistente/no visible, 405 método, 409 versión, 429 límite y
500 error interno sin información sensible. Sincronización y recálculo devuelven
503 `servicio_no_disponible` si hay errores y no se procesó ningún país/cálculo.
Conservan los campos del resultado de la tarea y añaden el mismo sobre `error`;
`error.detalles.errores` contiene los errores seguros por país. Si se procesó
parte del lote, devuelven 200 con sus resultados y errores: el cliente debe revisar
`errores`, las etapas pendientes y, en sincronización, `estado` y `faltantes`.
Un resultado vacío sin errores conserva 200. Los errores de persistencia se
traducen a mensajes seguros en español, sin publicar nombres de tablas,
restricciones, SQL ni textos originales de excepciones de la base de datos.

Throttling DRF: 100/min por usuario y 20/min por IP anónima; 429 conserva
`Retry-After`. Con Redis configurado y DJANGO_THROTTLE_REDIS=true, los contadores
se comparten entre instancias; se conserva fallback local. Los contadores DRF
son aproximados ante concurrencia.

Por defecto `DJANGO_NUM_PROXIES=0`: la identidad anónima usa `REMOTE_ADDR` e
ignora `X-Forwarded-For`. Alterar esa cabecera no reinicia el contador. Detrás
de proxies confiables, configurar el número real de saltos, sanear cabeceras
y restringir el acceso directo según la [guía de despliegue](deployment/README.md).
Esta opción es independiente de `DJANGO_TRUST_PROXY`, que configura HTTPS.

CORS admite exclusivamente `CORS_ALLOWED_ORIGINS` en `/api/`, soporta preflight
y expone Content-Disposition/Retry-After. Logs JSON registran método, ruta sin
query, actor autenticado, duración y estado; nunca cuerpos, tokens ni cabeceras.
Auditoría usa metadatos tipados para CRUD, consultas, login, tareas y EXPORT.

La documentación también se sirve en `/api/docs/` como JSON con contenido Markdown.

## Tiempo real y resumen asincrónico

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/realtime/resumen/` | JWT; `alertas_no_leidas` visibles y `paises_activos`, contados mediante ORM async. |
| GET | `/realtime/stream/` | JWT en Authorization; SSE incremental, requiere Redis. |
| WebSocket | `/ws/notificaciones/` (fuera de `/api/`) | Origin permitido y JWT; avisos de alertas visibles y dashboard. |

Resumen y SSE solo admiten GET (405 en otros métodos). Autenticación ausente,
inactiva o expirada: 401; límite de solicitudes: 429; Redis ausente/fallido al
abrir SSE: 503. Se aplica el mismo límite por usuario de la API.

WebSocket acepta protocolos `datapulse` y `bearer.<access>` para navegadores,
y selecciona únicamente `datapulse`. Clientes que admitan Authorization pueden
usarlo. No se aceptan tokens por URL. Eventos JSON: `conexion.lista`,
`alerta.creada` (solo `id`), `dashboard.actualizado` y `ping`.
El cliente puede enviar `{"accion":"ping"}` una vez por segundo y recibe `pong`.
Mensajes no admitidos cierran con 4400; exceso de pings con 4429.

JWT y usuario se revalidan antes de cada aviso y cada 15 segundos.
Revocación/expiración cierra WebSocket (4401); SSE emite
`autenticacion.expirada` y termina. SSE usa los mismos nombres en el campo
`event` y un objeto JSON en `data`. Un fallo de Redis durante SSE emite
`servicio.no_disponible` y termina. Reabrir con un access vigente y refrescar REST.
Estos avisos no incluyen mensajes privados ni proporcionan reproducción de eventos.
[Configuración y ejemplos de cliente](realtime/README.md).
