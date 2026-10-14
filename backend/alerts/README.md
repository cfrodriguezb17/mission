# Alertas y recuperación

Alerta guarda país, destinatario opcional, tipo, severidad, título, mensaje,
fecha, clave_evento y evidencia. Destinatario null significa global.
LecturaAlerta guarda una lectura por usuario/alerta; leer una alerta global
no modifica las lecturas de otros usuarios.

## API y permisos

[Contrato completo](../API.md#alertas). JWT obligatorio para los tres roles.
Solo son visibles alertas globales y privadas propias; ADMIN no amplía esa
visibilidad. Las lecturas individuales/masivas son idempotentes y bloquean
al usuario para serializar peticiones simultáneas.

## Generación

backend.workflows coordina sincronización, IRPC y alertas. El recálculo manual
también genera alertas. Los servicios básicos de economics y risk guardan sus
datos sin importar el módulo alerts.

| Regla | Tipo | Severidad |
| --- | --- | --- |
| IRPC <25 | RIESGO | CRITICAL |
| Caída estrictamente >15 puntos respecto al cálculo anterior | RIESGO | WARNING |
| Magnitud de variación diaria estrictamente >3 % | TIPO_CAMBIO | WARNING |
| Inflación estrictamente >50 % | INDICADOR | CRITICAL |
| Datos nuevos o actualizados efectivamente tras sincronización | INDICADOR o TIPO_CAMBIO | INFO |

Las alertas automáticas son globales. Sus valores proceden de la instantánea
del cálculo; los faltantes no generan comparaciones inventadas. La regla
cambiaria usa magnitud absoluta para incluir apreciación y depreciación del
par local → USD, comparando días consecutivos. USD/USD no genera alerta cambiaria.

INFO se agrupa por país/lote. Datos sin cambios o manuales conservados no generan
nuevos eventos. Una revisión persistente distingue cambios A → B → A en una
cotización, incluso con la misma fecha. Reintentar una entrega reutiliza su
clave; clave_evento única impide duplicados por la misma evidencia.

## Persistencia y recuperación

Economics guarda cada LoteActualizacion junto con el cambio económico.
Risk guarda cada índice con fecha_alertas_procesadas=null. Alerts confirma los
eventos y su marcador en una transacción común; ante fallo se revierten ambos
y el trabajo sigue pendiente. También se marca un índice que no activa reglas.
Dos trabajadores no duplican entregas.

```bash
python manage.py generar_alertas --limite 1000
python manage.py generar_alertas --paises CO BR --limite 100
```

El recuperador atiende índices históricos pendientes y lotes INFO, incluidos
países inactivos. El límite conjunto admite 1–1000 trabajos, 100 por defecto,
ordenados por antigüedad. Un candidato ocupa un turno aunque falle o no active
reglas. No se reintenta dos veces en la misma ejecución.

La salida es `{creadas, errores, pendientes}`. Pendientes cuenta índices sin
procesar y lotes sin entregar, no notificaciones. El filtro de países limita
selección y conteos. Si quedan errores o pendientes, el comando termina con
error; revisar la causa y repetir. Los workflows reflejan el resultado en
alertas_pendientes y recalculo_y_alertas_pendientes.

## Migraciones y límites

Conservar las migraciones aplicadas. Al instalar la migración
risk.0002_indice_alertas_procesadas, solo el último índice previo por país queda
pendiente; los anteriores se excluyen de revisión retrospectiva. Esa marca no
acredita una entrega anterior. Los índices posteriores sí son recuperables
aunque se calculen otros después.

Las revisiones de economics.0004 conservan cotizaciones, lotes y eventos previos;
los lotes antiguos pendientes siguen recuperables. No reconstruyen eventos
perdidos antes de conservar su evidencia. Detener productores/recuperadores
durante una actualización que aplique estas migraciones.

El recuperador no reconstruye resúmenes de auditoría perdidos. Un fallo de esa
etapa se comunica como PARCIAL y auditoria_pendiente=true; revisar la ejecución
antes de repetirla. PostgreSQL conserva los trabajos; Redis transporta avisos
de refresco y no sustituye esa persistencia.

Configuración de tareas: [Railway](../../deployment/RAILWAY.md#4-tareas).
