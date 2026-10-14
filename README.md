# DataPulse Latam

Plataforma de monitoreo económico de diez países latinoamericanos, cálculo del
índice de riesgo país (IRPC), alertas y portafolios de inversión simulados.
Backend Django/DRF y PostgreSQL; frontend Angular con Material y Chart.js.
Incluye exportación PDF y notificaciones en tiempo real mediante Redis/WebSockets.

## Acceso

| Recurso | Dirección |
| --- | --- |
| Código fuente | https://github.com/cfrodriguezb17/mission |
| Frontend local | http://localhost:4200 |
| API local | http://127.0.0.1:8000/api/ |
| Documentación API local | http://127.0.0.1:8000/api/docs/ |
| Frontend público | https://frontend-production-c7a6.up.railway.app |
| API pública | https://mission-production-ab1c.up.railway.app/api/ |
| Documentación API pública | https://mission-production-ab1c.up.railway.app/api/docs/ |
| Swagger interactivo | https://mission-production-ab1c.up.railway.app/api/swagger/ |
| Esquema OpenAPI JSON | https://mission-production-ab1c.up.railway.app/api/schema/ |

Publicación DEMO verificada el 14 de octubre de 2026: acceso con los tres roles,
35 comprobaciones HTTP, operaciones de portafolios, PDF y conexión WebSocket.
La rama `main` despliega automáticamente los cambios de cada servicio.

## Estructura

```text
backend/       API, modelos, migraciones y pruebas Django
frontend/      SPA Angular, pruebas y herramientas de desarrollo
deployment/    Guía de publicación en Railway
docs/          Colección Postman y guía de pruebas
```

## Requisitos y ejecución local

Python 3.12+, PostgreSQL, Node.js compatible con Angular 22 y pnpm 11.24.
El entorno verificado utiliza Node 24.20. Redis permite las notificaciones en
vivo; si no está disponible, el frontend consulta las alertas periódicamente.

1. Preparar la base PostgreSQL e instalar el backend siguiendo
   [backend/README.md](backend/README.md).
2. Crear `backend/.env` desde `backend/.env.example`, completar las variables,
   aplicar migraciones y ejecutar `python manage.py seed_data`.
3. Instalar el frontend con `pnpm install --frozen-lockfile`, desde `frontend`.
4. Iniciar ambos servicios desde la raíz:

```bash
./run-local.sh
```

El script requiere Linux, Bash 4.3+, `setsid` y `curl`. Comprueba dependencias,
puertos, PostgreSQL y migraciones; usa `backend/.venv` y
`frontend/node_modules`. Ctrl+C detiene ambos servicios. Para iniciar cada uno
por separado, consultar las guías de [backend](backend/README.md) y
[frontend](frontend/README.md).

## Usuarios de demostración

`seed_data` crea estas cuentas con contraseña **DataPulse2026!**:

| Email | Rol |
| --- | --- |
| admin@datapulse.com | ADMIN |
| analista@datapulse.com | ANALISTA |
| viewer@datapulse.com | VIEWER |

El seed es repetible y conserva registros existentes. Si una cuenta DEMO existe
con datos incompatibles, aborta sin reemplazarla. El rol ADMIN de negocio no
concede acceso automático al administrador Django; crear un superusuario propio
con `python manage.py createsuperuser` si se necesita.

Los datos precargados incluyen diez países, cinco años de seis indicadores,
31 cotizaciones por moneda no USD, dos portafolios y los índices de riesgo.
Los históricos son simulados y aparecen identificados como tales.

## Funcionalidades

- Autenticación JWT, perfil y permisos ADMIN, ANALISTA y VIEWER.
- Dashboard con KPI, mapa de Latinoamérica, ranking IRPC y tendencias.
- Países con indicadores, históricos cambiarios y desglose de riesgo.
- Portafolios propios/públicos, posiciones, validaciones, previsualización y PDF.
- Alertas con filtros, lecturas por usuario y actualización en vivo.
- Sincronización de proveedores, recálculo de riesgo y registro de actividad.

## Documentación

- [Arquitectura y decisiones técnicas](ARQUITECTURA.md).
- [Modelo relacional y restricciones](backend/MODELO_DATOS.md).
- [Contrato de API](backend/API.md); `/api/docs/` conserva el contrato como Markdown en JSON.
- Swagger en `/api/swagger/` y OpenAPI 3 en `/api/schema/`, generados con drf-spectacular.
- [Fórmula IRPC](backend/risk/README.md).
- [Ejecución de pruebas](docs/PRUEBAS.md).
- [Publicación en GitHub y Railway](deployment/RAILWAY.md).

Importar [la colección Postman](docs/DataPulse.postman_collection.json).
Configurar `base_url=http://127.0.0.1:8000`, `password_demo=DataPulse2026!`
y una `password_registro` válida. Los logins guardan los tokens por rol. La
colección realiza escrituras y sincronizaciones; ejecutarla sobre una base DEMO.

## Integración y entrega continua

[GitHub Actions](https://github.com/cfrodriguezb17/mission/actions/workflows/ci.yml)
ejecuta el pipeline [CI](.github/workflows/ci.yml) en cada push a `main` y pull request:
pruebas Django con PostgreSQL, validación OpenAPI, pruebas Angular, build de
producción y pruebas de navegador con API y Redis aislados. No necesita secretos
de producción. Railway recibe los cambios de GitHub; activar **Wait for CI** en
los servicios `mission`, `frontend` y `cotizaciones` para condicionar su publicación
al resultado del pipeline. [Detalles](docs/PRUEBAS.md#integracion-continua).

## Operación

Los errores de API incluyen `error.codigo`, `mensaje` y `detalles`; los de campo
se presentan en los formularios. Los logs JSON registran método, ruta, usuario,
duración y estado. La tabla LogActividad conserva acciones CRUD, consultas,
login y exportaciones, con metadatos tipados.

Las sincronizaciones pueden ser parciales: revisar `estado`, `errores`,
`faltantes` y etapas pendientes. Los faltantes no se convierten en cero.
Un IRPC alto representa menor riesgo y debe leerse junto con su evidencia.
Las reglas de recuperación se explican en [alertas](backend/alerts/README.md).
