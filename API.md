# Contrato de API - DataPulse Latam

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

## Portafolios y posiciones

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/portafolios/` | Propios y públicos; ADMIN consulta todos. `search`, `es_publico`, `propios`, `ordering`, paginación. |
| POST | `/portafolios/` | ADMIN/ANALISTA; `nombre`, `descripcion` opcional, `es_publico` opcional. |
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
máximo 100. Ordenamientos inválidos devuelven 400. Campos permitidos detallados
en los README de cada módulo; `search` en países y portafolios. Booleanos query
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
500 error interno sin información sensible. Throttling DRF: 100/min por usuario
y 20/min por IP anónima; 429 conserva `Retry-After`. La caché local de desarrollo
es en memoria; producción usa archivo compartido entre workers de una instancia.
Los contadores DRF son aproximados ante concurrencia; múltiples instancias
necesitan una caché centralizada para compartir el límite.

CORS admite exclusivamente `CORS_ALLOWED_ORIGINS` en `/api/`, soporta preflight
y expone Content-Disposition/Retry-After. Logs JSON registran método, ruta sin
query, actor autenticado, duración y estado; nunca cuerpos, tokens ni cabeceras.
Auditoría usa metadatos tipados para CRUD, consultas, login, tareas y EXPORT.

La documentación también se sirve en `/api/docs/` como JSON con contenido Markdown.
