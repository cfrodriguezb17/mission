# Backend — DataPulse Latam

API Django 5.2, Django REST Framework, JWT y PostgreSQL. Incluye indicadores,
cotizaciones, IRPC, portafolios, alertas, dashboard, PDF y tiempo real.
[Contrato de API](API.md) · [Modelo de datos](MODELO_DATOS.md).

## Instalación local

Requisitos: Python 3.12+ y PostgreSQL accesible. Crear una base vacía y un rol con
permisos de conexión y migración. Las pruebas necesitan permiso CREATEDB y
acceso a la base de mantenimiento `postgres`.

Desde esta carpeta:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Completar `DJANGO_SECRET_KEY` y `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`. Las variables exportadas
tienen prioridad sobre `.env`; sus valores no se interpolan. Para el frontend:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
```

Preparar y arrancar:

```bash
python manage.py check
python manage.py migrate
python manage.py seed_data
python -m uvicorn backend.asgi:application --host 127.0.0.1 --port 8000 --reload --lifespan off --no-proxy-headers
```

API: http://127.0.0.1:8000/api/. Documentación: `/api/docs/`. Salud PostgreSQL:
`/health/`. Administrador Django: `/admin/`; crear un superusuario propio con
`python manage.py createsuperuser`. El rol ADMIN de negocio no concede staff.
Para iniciar Angular y Django juntos, usar `../run-local.sh` desde esta carpeta.

## Datos de demostración

`seed_data` crea ADMIN, ANALISTA y VIEWER con los emails y contraseña del
[README principal](../README.md#usuarios-de-demostración). También carga diez
países, 300 observaciones, 279 cotizaciones, dos portafolios y cuatro posiciones,
y calcula los índices de los diez países.

Las cotizaciones son 31 días por cada una de nueve monedas distintas de USD;
Ecuador usa identidad calculada USD/USD. Los indicadores y cotizaciones son
simulados y se señalan mediante `es_simulado`. El seed es repetible, conserva
registros y aborta si una identidad DEMO existente es incompatible.

## Sincronización y tareas

```bash
python manage.py sync_indicadores
python manage.py update_tipos_cambio
python manage.py sync_countries
python manage.py calcular_riesgos
python manage.py generar_alertas --limite 1000
```

World Bank y ExchangeRate tienen timeouts, reintentos acotados y fallos parciales
por país. REST Countries necesita `REST_COUNTRIES_API_KEY` para sincronizar;
la precarga funciona sin ella. Se conservan datos manuales reales.
Los workflows guardan primero datos válidos y coordinan riesgo, alertas y auditoría.
Los comandos terminan con error si quedan fallos o etapas pendientes.
En HTTP, un 200 parcial exige revisar `estado`, `errores`, `faltantes` y flags.

Los lotes INFO y los índices conservan trabajo de alertas en PostgreSQL;
`generar_alertas` recupera ambos con un presupuesto conjunto, sin duplicarlos.
[Contrato y límites](alerts/README.md). Los cálculos de riesgo conservan entradas,
fuentes y faltantes; [fórmula IRPC y ambigüedades](risk/README.md).

## Permisos y concurrencia

VIEWER consulta y exporta; no modifica. ANALISTA crea y edita propios/públicos;
ADMIN accede a todos. Solo propietario con escritura o ADMIN elimina o cambia
visibilidad. Las alertas privadas son visibles solo para su destinatario.

Cada cambio de portafolio o posición exige `version`, bloquea el portafolio y
comprueba límites dentro de una transacción. El éxito incrementa la versión;
conflicto devuelve 409 para recargar y revisar. No hay sobrescritura automática.

## Errores, logs y auditoría

DRF entrega `error.codigo/mensaje/detalles` y conserva errores de campo. Un 500
no publica excepciones. Logs JSON registran método, ruta sin query, actor,
duración y estado. LogActividad registra CRUD, consultas, login, tareas y EXPORT
con metadatos tipados, sin credenciales ni cuerpos de peticiones.

Las escrituras transaccionales se revierten si falla su auditoría. Un fallo del
resumen final de una tarea conserva los datos, informa PARCIAL y
`auditoria_pendiente=true`; no reconstruye automáticamente el evento perdido.
Revisar la ejecución antes de repetirla; el recuperador de alertas no repara auditoría.

Throttling: 100/min por usuario y 20/min por IP anónima; 429 conserva Retry-After.
Con Redis configurado se comparten contadores entre instancias, con fallback
local. CORS limita los orígenes autorizados. `DJANGO_NUM_PROXIES=0` ignora
X-Forwarded-For; cambiarlo requiere verificar la cadena real de proxies.

## Verificación y despliegue

[Guía de pruebas](../docs/PRUEBAS.md) y [publicación en Railway](../deployment/RAILWAY.md).
Conservar las migraciones aplicadas. El Dockerfile arranca Uvicorn, aplica
migraciones y genera estáticos; seed se ejecuta por separado.
[Configuración de WebSockets y SSE](realtime/README.md).
