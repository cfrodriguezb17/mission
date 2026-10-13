# Despliegue del backend

El repositorio contiene un arranque portable para un servicio Python o una imagen
Docker. La publicación requiere elegir proveedor, conectar repositorio y disponer
de PostgreSQL. No hay una URL pública configurada ni credenciales de nube en este
proyecto. El repositorio backend tampoco tiene remoto Git configurado actualmente.

## Servicio Python

Directorio del servicio: `backend` si se publica el repositorio conjunto; la raíz
si se publica solo este repositorio backend. Build: `pip install -r requirements.txt`.
Start: `sh deployment/start.sh`. Ejecuta migraciones incrementales, collectstatic
y Gunicorn con 2 workers (configurable) y timeout de 90 segundos. Health: `/health/`.
Seed es un paso explícito: `python manage.py seed_data`; no se ejecuta en cada arranque.

Variables de producción:

| Variable | Valor / finalidad |
| --- | --- |
| DJANGO_DEBUG | false |
| DJANGO_SECRET_KEY | Secreto aleatorio propio del entorno. |
| DJANGO_ALLOWED_HOSTS | Dominio del backend, sin esquema ni rutas. |
| POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT | Credenciales del PostgreSQL administrado. |
| DJANGO_DB_CONN_MAX_AGE | Segundos de reutilización por conexión; 60 por defecto, 0 para desactivarla. Entero >= 0. |
| CORS_ALLOWED_ORIGINS | Origen HTTPS del cliente; sin barra final. |
| CSRF_TRUSTED_ORIGINS | Origen HTTPS del admin si se usa un dominio distinto. |
| DJANGO_SECURE_SSL_REDIRECT | true |
| DJANGO_SECURE_HSTS_SECONDS | 31536000 tras verificar HTTPS. |
| DJANGO_TRUST_PROXY | true solo si el proxy sobrescribe X-Forwarded-Proto. |
| DJANGO_NUM_PROXIES | Entero >= 0; por defecto 0. Número de proxies confiables para identificar clientes en el límite de solicitudes. |
| DJANGO_CACHE_LOCATION | Directorio escribible compartido entre workers de esta instancia. |
| DJANGO_REDIS_URL | URL privada de Redis para la caché de datos compartidos; vacía la desactiva. |
| DJANGO_DATA_CACHE_TTL | Caducidad de datos en segundos: 60 por defecto, 0 para desactivar; entero >= 0. |
| DJANGO_DATA_CACHE_PREFIX | Prefijo exclusivo del proyecto y entorno en Redis; separar pruebas y producción. |
| REST_COUNTRIES_API_KEY | Clave v5 para sincronización real de datos generales. |
| PORT, WEB_CONCURRENCY | Puerto del proveedor y número de workers. |

El proveedor debe suministrar HTTPS y un proxy confiable. Confirmar que health
recibe el protocolo correcto o permite seguir la redirección HTTPS. Los archivos
estáticos del admin se sirven con WhiteNoise. PostgreSQL sigue siendo persistente
y externo al contenedor. Para varias instancias, sustituir FileBasedCache por una
caché compartida central y validar throttling; DRF no garantiza conteos estrictos
bajo concurrencia. No se considera autenticado un proxy por el simple encabezado.

Con `DJANGO_NUM_PROXIES=0`, DRF usa `REMOTE_ADDR` e ignora `X-Forwarded-For`,
evitando que el cliente cambie su contador mediante una cabecera inventada.
Si existe un proxy, este valor agrupa las solicitudes anónimas que comparten
su dirección. Para distinguir clientes detrás de él, establecer el número real
de proxies confiables: con uno, `DJANGO_NUM_PROXIES=1`. DRF selecciona desde
la derecha de la cadena X-Forwarded-For según ese número.

Antes de habilitar un valor positivo, asegurar que cada salto confiable sanea
o añade la dirección de su conexión de forma controlada y que la aplicación
solo acepta tráfico a través de esa cadena. No permitir acceso directo a Gunicorn
desde clientes externos. Verificar que cabeceras aportadas por el cliente no
alteran su identidad y que dos clientes distintos conservan contadores distintos.
`DJANGO_TRUST_PROXY` controla X-Forwarded-Proto/HTTPS; no habilita esta confianza
de direcciones. Valores negativos o no enteros de DJANGO_NUM_PROXIES impiden
el arranque para evitar una configuración ambigua.

Comprobar configuración antes de publicar:

```bash
python manage.py check --deploy
python manage.py migrate --check
python manage.py seed_data
```

Verificar tras publicar: `/health/`, `/api/`, `/api/docs/`, login de los tres roles,
dashboard, PDF y CORS desde el origen permitido. Registrar URL y resultados en el
README cuando exista una publicación real. Credenciales DEMO están exigidas por
la prueba; los datos históricos de seed son simulados.

## Conexiones PostgreSQL

El arranque actual usa Gunicorn WSGI. Django conserva cada conexión durante un
máximo de 60 segundos y comprueba su disponibilidad antes de reutilizarla en
una petición. `DJANGO_DB_CONN_MAX_AGE=0` restaura el cierre al finalizar cada
petición. Los valores negativos o no enteros impiden el arranque.

Cada worker/hilo puede mantener su propia conexión: dimensionar el número de
workers e instancias junto con los comandos programados y el límite de conexiones
del proveedor. Si se migra a ASGI, establecer `DJANGO_DB_CONN_MAX_AGE=0`; un pool
de psycopg requiere además instalar/configurar `psycopg[pool]` y conservar ese
valor en cero. No se activa un pool ni PgBouncer en esta entrega.

## Caché de datos compartidos

Definir `DJANGO_REDIS_URL` para habilitar el alias `data` con Redis nativo de
Django. Se admiten `redis://`, `rediss://` (TLS) y `unix://`. En Railway, conectar
el servicio Redis por su URL privada desde el mismo proyecto y entorno. No
publicar credenciales en el repositorio. Redis es opcional: sin URL se consulta
PostgreSQL directamente. Los timeouts de conexión y lectura son de 0.5 segundos.

Se almacenan datos compartidos de países, mapa, tendencias y métricas comunes
del dashboard; los conteos privados de cada usuario permanecen frescos. Las
escrituras invalidan tras commit y el TTL limita la antigüedad si falla Redis.
La caché no reemplaza permisos, auditoría ni throttling. El alias `default` de
throttling conserva su configuración: centralizarlo también antes de escalar a
varias instancias. No usar Redis como almacenamiento permanente de los datos.

[Implementación, invalidación y verificaciones](../docs/performance-medium-20261013/INFORME.md).

## Docker

```bash
docker build -t datapulse-backend .
docker run --env-file .env -p 8000:8000 datapulse-backend
```

El contenedor usa un usuario sin privilegios. `POSTGRES_HOST` debe ser accesible
desde él; localhost no apunta a la base del host. `.dockerignore` excluye secretos,
entornos locales, Git, cachés y artefactos. El Dockerfile está preparado; no se
afirma una construcción verificada mientras no se ejecute Docker.

## Programación en un servidor Linux

Las unidades systemd incluidas son plantillas para `/opt/datapulse/backend`, un
usuario de sistema datapulse y un entorno `/etc/datapulse/backend.env`. Adaptar
rutas/usuario al servidor; copiar los cuatro archivos a `/etc/systemd/system/`
y habilitar los dos timers. Los secretos quedan en el archivo de entorno con
permisos restringidos, nunca en las unidades.

Cotizaciones: diario 03:00 UTC. Indicadores: diario 03:15 UTC. Ambas tareas llaman
workflows y recalculan riesgo/alertas. Persistent recupera una ejecución omitida;
systemd evita solapar una misma unidad. Revisar journal y salida ante errores
parciales; los comandos devuelven fallo para exigir atención/reintento.
En hosting administrado usar su scheduler con estos mismos comandos y variables.
Las unidades se entregan preparadas; no están instaladas ni activas en el equipo.

Tras aplicar `economics.0003_lotes_actualizacion`, los fallos INFO conservan lotes
en PostgreSQL. Para recuperación independiente de los proveedores, programar
`python manage.py generar_alertas --limite 1000` con las mismas variables del
backend. El comando devuelve `pendientes` y salida distinta de cero si hay errores
o falta vaciar el alcance: volver a ejecutarlo y supervisar la cola de trabajos en
el administrador de consulta. Sincronizaciones posteriores también reintentan
sus países. Esta tarea adicional se documenta; no se activa automáticamente.

Con `risk.0002_indice_alertas_procesadas`, el mismo comando recupera índices
pendientes, incluidos históricos, y lotes INFO. `--limite` es un presupuesto
**conjunto** de 1–1000 trabajos (100 por defecto), por antigüedad; `pendientes`
suma ambos tipos dentro de `--paises`, o todos si no hay filtro. Índices sin
reglas también consumen un turno. Una salida con pendientes exige otra ejecución.
Detener productores y recuperadores durante la migración/despliegue: solo el
último índice previo por país queda para revisión; los anteriores se excluyen
de revisión retrospectiva para evitar una avalancha. Se conservan todos los
datos y alertas. Reanudar los workers con el código nuevo tras migrar.
[Contrato y política completa](../alerts/README.md).
