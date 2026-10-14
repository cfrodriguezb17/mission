# ASGI y tiempo real

El backend sirve HTTP y WebSockets con Uvicorn. Redis conecta los workers y
PostgreSQL mantiene los datos. No requiere nuevas tablas ni migraciones.

## Configurar

Instalar `requirements.txt` y definir en el entorno del backend:

```dotenv
DJANGO_DB_CONN_MAX_AGE=0
DJANGO_DB_POOL=true
DJANGO_DB_POOL_MIN_SIZE=1
DJANGO_DB_POOL_MAX_SIZE=4
DJANGO_DB_PREPARE_THRESHOLD=5
DJANGO_REALTIME_REDIS_URL=redis://localhost:6379/0
DJANGO_REALTIME_PREFIX=datapulse:realtime:desarrollo
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
```

Usar la URL privada del servicio Redis en producción, sin guardar credenciales en
Git. Si se deja vacía `DJANGO_REALTIME_REDIS_URL`, usa `DJANGO_REDIS_URL` de la
caché de datos. Sin ninguna URL, el resumen funciona y los streams rechazan su
apertura. Separar prefijos de producción, desarrollo y pruebas.

Arranque local, desde backend con su entorno virtual activo:

```bash
python -m uvicorn backend.asgi:application --host 127.0.0.1 --port 8000 --reload --lifespan off --no-proxy-headers
```

En producción, `sh deployment/start.sh`. Usa dos workers por defecto y pool
independiente de hasta cuatro conexiones por worker. Los streams no retienen
una conexión PostgreSQL mientras esperan avisos. El pool adquiere conexiones
para autenticar y consultar, y las devuelve después. La suite comprueba la
reutilización física y `pg_prepared_statements` en PostgreSQL.

`server_side_binding=True` permite preparar consultas parametrizadas. El umbral
es por conexión: por defecto se prepara después de cinco ejecuciones de la misma
consulta. El valor vacío desactiva la preparación para poolers incompatibles.
No se modifican SQL ni límites globales de PostgreSQL.
[Presupuesto de conexiones y proxy](../deployment/README.md).

## Resumen async

`GET /api/realtime/resumen/`, con `Authorization: Bearer <access>`:

```json
{"alertas_no_leidas": 3, "paises_activos": 10}
```

Usa `acount()` y conserva visibilidad/lecturas por usuario. Los nuevos endpoints
son vistas Django async. El CRUD existente mantiene sus transacciones, bloqueos
y DRF síncrono, ejecutados en un solo tramo de middleware/vista/renderizado
dentro de ASGI. Las vistas async conservan el handler nativo.
`DJANGO_ASGI_SYNC_REST=false` desactiva esa agrupación del CRUD. Cambiar de servidor no hace async
automáticamente todas las vistas ni garantiza una reducción de latencia.

## WebSocket en un navegador

Usar un access obtenido mediante login. No poner JWT en query strings:

```javascript
const ws = new WebSocket('ws://127.0.0.1:8000/ws/notificaciones/', [
  'datapulse', `bearer.${access}`
]);
ws.onmessage = ({data}) => {
  const notice = JSON.parse(data);
  if (notice.event === 'alerta.creada') {
    // Refrescar /api/alertas/ con Authorization.
  }
  if (notice.event === 'dashboard.actualizado') {
    // Refrescar /api/dashboard/resumen/ con Authorization.
  }
};
// Al abandonar la pantalla:
// ws.close();
```

Usar `wss://` en producción y abrir desde un Origin permitido. El servidor
selecciona `datapulse`, sin devolver el JWT como subprotocolo. También admite
Authorization para clientes que puedan establecer ese encabezado.

Se reciben `conexion.lista`, `alerta.creada` con id, `dashboard.actualizado` y
`ping`. Mensaje entrante permitido: `{"accion":"ping"}`, máximo uno por segundo,
con respuesta `pong`. El canal sirve para avisos; las escrituras usan REST.

## Streaming SSE

`GET /api/realtime/stream/` envía eventos conforme ocurren, sin construir toda
la respuesta en memoria. Para probar con un access vigente:

```bash
curl -N -H "Authorization: Bearer $ACCESS_TOKEN" http://127.0.0.1:8000/api/realtime/stream/
```

Primer evento:

```text
event: conexion.lista
data: {"event": "conexion.lista"}

```

Desde navegador usar `fetch()` con Authorization y leer `response.body`
incrementalmente; el `EventSource` nativo no permite ese encabezado. Cancelar con
`AbortController` al abandonar la pantalla. Manejar fragmentos parciales y
separadores de eventos (`\n\n`), porque un fragmento de red no equivale a un evento.
No cambiar a tokens por URL para facilitar la integración.

## Permisos y entrega

Se autentica y audita cada apertura, con el límite por usuario ya configurado.
Solo se notifican alertas globales o privadas propias, incluso para ADMIN;
la visibilidad se vuelve a consultar antes de enviarlas. Los cambios de país,
indicador o índice de riesgo notifican `dashboard.actualizado`. Las señales
publican después del commit; una transacción revertida no genera avisos.
`bulk_create`, `QuerySet.update`, borrados y SQL directo no emiten estos eventos.

Cada 15 segundos y antes de cada aviso se vuelve a comprobar el access, la cuenta
y la revocación por contraseña. Un JWT vencido requiere reconectar con otro
access: WebSocket cierra 4401; SSE envía `autenticacion.expirada` y termina.
Los pings mantienen actividad y renuevan membresías de grupos; las membresías
abandonadas caducan en 60 segundos si falla la limpieza por desconexión.

Redis transporta avisos de refresco sin garantía de reproducción: al reconectar,
consultar REST para recuperar el estado. Su caída no revierte las escrituras en
PostgreSQL; nuevas conexiones SSE devuelven 503. El proxy debe admitir WebSockets
y no almacenar/bufferizar SSE. El frontend Angular conecta la campanita, el centro
de alertas y el dashboard a estos avisos, con reconexión y recuperación por REST.
[Guía de pruebas](../../docs/PRUEBAS.md).

## Verificación

```bash
python manage.py test realtime common.tests.test_database_settings common.tests.test_async_middleware --noinput
python manage.py verify_migrations
```

Las pruebas lanzan Uvicorn con dos workers, Redis temporal y PostgreSQL de prueba.
Comprueban entrega incremental, privacidad, commit/rollback, JWT/origen, revocación,
mensajes inválidos, caída de Redis y CRUD concurrente/PDF bajo ASGI.
[Configuración de producción](../../deployment/RAILWAY.md).
