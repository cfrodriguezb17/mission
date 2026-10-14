# DataPulse Latam

Monitoreo económico de diez países de Latinoamérica, cálculo de riesgo país
(IRPC), alertas y portafolios de inversión. Estado al **14 de octubre de 2026**
(America/Bogota).

## Proyectos y estado de entrega

| Proyecto | Estado | Guía |
| --- | --- | --- |
| Backend | API Django/DRF con JWT, PostgreSQL, dashboard, PDF y notificaciones en tiempo real implementados. | [Instalación y operación](backend/README.md) |
| Frontend | SPA Angular/Material implementada: sesión, dashboard, países, portafolios, alertas y perfil; integrada y verificada con la API. | [Proyecto Angular](frontend/README.md) |
| Repositorio público | Pendiente de publicación B06; copia conjunta local preparada con ambos historiales conservados. | [Plan de entrega](PENDIENTES_BACKEND_ENTREGA.md#b06-publicar-código-y-cambios-pendientes-en-github) |
| URL pública del backend | Pendiente de despliegue B07 y verificación B10. | [Guía de despliegue](backend/deployment/README.md) |
| URL pública del frontend | Implementado localmente; pendiente de publicación. | [Arquitectura](ARQUITECTURA.md) |

Las URLs locales siguientes sirven para ejecutar la solución en este equipo;
las capturas de servidores temporales en `docs/` son evidencia histórica.

## Iniciar backend y frontend juntos

Después de preparar las dependencias, `backend/.env`, PostgreSQL y las
migraciones según las secciones siguientes, desde la raíz:

```bash
./run-local.sh
```

También puedes ejecutar `pnpm local` desde `frontend`. El script canónico está
en [frontend/tools/run-local.sh](frontend/tools/run-local.sh), dentro del
repositorio del frontend. Funciona en Linux con Bash 4.3+, `setsid` (util-linux),
`curl`, Node y pnpm. Utiliza `backend/.venv` y `frontend/node_modules` existentes.

Comprueba configuración, conexión a PostgreSQL y migraciones antes de arrancar.
No instala dependencias, aplica migraciones ni ejecuta seed automáticamente.
Inicia Django y Angular con recarga automática, espera a que ambos respondan y
muestra sus logs en la misma terminal. Abre [http://localhost:4200](http://localhost:4200).
**Ctrl+C detiene ambos servicios y sus procesos hijos**. Si uno falla, cierra el
otro; si los puertos 8000/4200 están ocupados, avisa sin detener servidores ajenos.

Para este arranque habilita DEBUG, HTTP y los hosts/orígenes locales únicamente
en el entorno de los procesos; conserva `backend/.env` sin cambios. PostgreSQL
debe estar iniciado por separado. `./run-local.sh --help` muestra los requisitos.

## Ejecutar el backend

Requisitos: Python 3.12+ y PostgreSQL accesible. Crear una base vacía y un rol
con permisos de conexión y migración; las pruebas necesitan `CREATEDB` y acceso
a la base de mantenimiento `postgres`. Desde la raíz de esta entrega:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Completar en `.env` los valores `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` y un `DJANGO_SECRET_KEY`
propio. La clave `REST_COUNTRIES_API_KEY` solo es necesaria para sincronizar ese
proveedor; la precarga y las lecturas locales funcionan sin ella.

```bash
python manage.py check
python manage.py migrate
python manage.py seed_data
python -m uvicorn backend.asgi:application --reload --lifespan off --no-proxy-headers
```

API: [http://127.0.0.1:8000/api/](http://127.0.0.1:8000/api/).
Documentación pública local: [API docs](http://127.0.0.1:8000/api/docs/).
Salud de PostgreSQL: [health](http://127.0.0.1:8000/health/).
El [README del backend](backend/README.md) detalla roles, datos, comandos y límites.
La [guía Angular](frontend/README.md) permite iniciar el frontend completo en
`http://localhost:4200/`, configurar CORS y ejecutar las pruebas.

## Usuarios DEMO y prueba de API

`seed_data` crea estas identidades si no existen:

| Email | Rol | Contraseña de demostración |
| --- | --- | --- |
| admin@datapulse.com | ADMIN | DataPulse2026! |
| analista@datapulse.com | ANALISTA | DataPulse2026! |
| viewer@datapulse.com | VIEWER | DataPulse2026! |

El seed conserva registros existentes y aborta si una identidad DEMO existente
no coincide con el rol, estado o contraseña esperados. ADMIN es un rol de negocio;
el administrador Django requiere además permisos staff/superuser.

```bash
curl --request POST http://127.0.0.1:8000/api/auth/login/ \
  --header 'Content-Type: application/json' \
  --data '{"email":"analista@datapulse.com","password":"DataPulse2026!"}'
```

Copiar `access` de la respuesta y usarlo como Bearer token:

```bash
curl 'http://127.0.0.1:8000/api/portafolios/validar-nombre/?nombre=Latam' \
  --header 'Authorization: Bearer <access>'
```

Importar [DataPulse.postman_collection.json](docs/backend-audit-20261010/DataPulse.postman_collection.json)
en Postman. Configurar `base_url` sin `/api` ni barra final
(`http://127.0.0.1:8000`), `password_demo=DataPulse2026!` y una
`password_registro` válida. Ejecutar en orden en una base de demostración:
la colección crea, modifica y elimina registros, y sincroniza World Bank real.
Los logins guardan los tokens de cada rol; los ejemplos de respuesta pertenecen
a la auditoría histórica. Incluye las consultas B03 de creación y edición.
Contrato vigente: [API.md](backend/API.md).

## Verificación

Desde `backend`, con el entorno activado y PostgreSQL de pruebas:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py verify_migrations
git diff --check
```

`verify_migrations` aplica las migraciones originales desde cero y ejecuta toda
la suite en una base temporal: la elimina al pasar y la conserva ante fallos
para diagnóstico. Para una comprobación enfocada puede usarse
`python manage.py test economics alerts risk portfolios common --noinput`.
Conservar siempre las migraciones aplicadas.

La última evidencia funcional previa a esta integración registra **381 pruebas
backend aprobadas** en una base aislada. Frontend registra **120 pruebas unitarias
e integradas**, **18 pruebas de navegador controladas** y una prueba real de
WebSockets. Los resultados históricos y las comprobaciones actuales se distinguen
en [Estado de entrega](docs/ENTREGA.md) y [Validación local](docs/VALIDACION_LOCAL.md).
No acreditan todavía una aplicación publicada.

## Publicación en GitHub y Railway

La guía vigente de servicios, variables, dominios, tareas y comprobación pública
está en [deployment/RAILWAY.md](deployment/RAILWAY.md). Backend y frontend se
construyen con sus propios Dockerfiles desde `/backend` y `/frontend`.
Los secretos se configuran en Railway; los archivos `.env.railway.example`
contienen únicamente referencias y marcadores. Falta registrar las URLs reales
tras publicar y verificar la aplicación.

## Límites y operación

- La precarga usa población ilustrativa, 300 observaciones y 279 cotizaciones
  simuladas (`es_simulado=true`). Ecuador usa identidad USD/USD. Los índices
  y PDF señalan simulación y evidencia incompleta; faltantes no equivalen a cero.
- Proveedores externos pueden entregar resultados parciales. Se conservan los
  datos válidos; revisar `errores`, `estado` y los flags de etapas pendientes.
  REST Countries tuvo una [verificación real satisfactoria para los diez países](docs/backend-audit-20261010/REST_COUNTRIES.md)
  en PostgreSQL temporal, sin modificar la base principal.
- Las alertas INFO y de índices conservan trabajo pendiente en PostgreSQL.
  `python manage.py generar_alertas --limite 1000` recupera ambos tipos, incluso
  índices históricos posteriores al corte de migración. Si quedan errores o
  trabajos, termina con fallo y debe repetirse tras revisar la causa.
  [Contrato, límite conjunto y política para históricos](backend/alerts/README.md).
- Un fallo del resumen de auditoría de una tarea conserva sus datos y devuelve
  `auditoria_pendiente=true`, estado PARCIAL y error en el comando. No hay cola
  ni reconstrucción automática de ese resumen: revisar la ejecución antes de
  repetir; la repetición no recupera el evento original.
  [Transacciones y límites de auditoría](backend/audit/README.md).
- Timers, recuperación programada, supervisión y restauración de respaldos
  requieren infraestructura y siguen pendientes. Dockerfile y plantillas están
  preparados; no acreditan un despliegue ni una construcción Docker verificada.

## Referencias de entrega

- [Pendientes vigentes B01–B10](PENDIENTES_BACKEND_ENTREGA.md) y
  [estado e historial del backend](PENDIENTES.md).
- [Arquitectura](ARQUITECTURA.md), [modelo y restricciones](backend/MODELO_DATOS.md)
  y [contrato API](backend/API.md).
- [B01/B02: 308 pruebas y recuperación](docs/backend-b02-20261010/README.md),
  [migraciones aplicadas localmente sin pérdida de datos](docs/backend-b02-20261010/main-database/README.md)
  y [B03: 325 pruebas y validación de nombres](docs/backend-b03-20261010/README.md).
- [Consolidación B04 y comprobaciones documentales](docs/backend-b04-20261010/README.md).
- [Cierre B05: versión, PostgreSQL y revisión de contratos](docs/backend-b05-20261010/README.md).
