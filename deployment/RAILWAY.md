# Publicación en GitHub y Railway

Estado: publicación DEMO activa, verificada el 14 de octubre de 2026.
Frontend: https://frontend-production-c7a6.up.railway.app.
API: https://mission-production-ab1c.up.railway.app/api/.
La copia de entrega contiene el historial de ambos proyectos bajo `/backend` y
`/frontend`. Las instalaciones locales originales se conservan por separado.

## Servicios

Crear un proyecto Railway con estos servicios en el mismo entorno y región:

| Servicio | Fuente / directorio raíz | Arranque | Salud |
| --- | --- | --- | --- |
| Postgres | Base PostgreSQL de Railway, con volumen persistente | Gestionado por Railway | Gestionado por Railway |
| Redis | Base Redis de Railway | Gestionado por Railway | Gestionado por Railway |
| backend | Repositorio GitHub, `/backend` | CMD del Dockerfile: `sh deployment/start.sh` | `/health/` |
| frontend | Mismo repositorio, `/frontend` | CMD de Nginx de la imagen | `/health/` |
| cotizaciones | Mismo repositorio, `/backend` | `python deployment/scheduled.py` | Cron cada 15 minutos |

Mantener una réplica del backend en esta primera publicación. Su arranque aplica
migraciones, genera estáticos y ejecuta Uvicorn. El seed es un paso separado.
Los directorios raíz permiten que Railway detecte el Dockerfile de cada proyecto.
Configurar watch paths `/backend/**` y `/frontend/**` respectivamente.
Activar **Wait for CI** en `mission`, `frontend` y `cotizaciones`: el workflow
[CI](../.github/workflows/ci.yml) debe pasar antes de cada publicación automática.
No se necesita guardar un token de Railway en GitHub.

Esta guía usa los ajustes del servicio. No añade `railway.json`: Railway indica
que Config as Code está deprecado y que los servicios nuevos no pueden adoptarlo.
Si se automatiza la creación de infraestructura después, utilizar su IaC actual.

## 1. Repositorio de entrega

Código público: [cfrodriguezb17/mission](https://github.com/cfrodriguezb17/mission).
Clonar para preparar una instalación o conectar este repositorio a Railway:

```bash
git clone https://github.com/cfrodriguezb17/mission.git
cd mission
```

Backend y frontend son carpetas versionadas, no submódulos. La rama de entrega
es main y contiene el historial incremental depurado de ambos proyectos.

## 2. PostgreSQL, Redis y API

Crear Postgres y Redis con esos nombres para usar las referencias del archivo
[backend/.env.railway.example](../backend/.env.railway.example). Añadir el servicio
backend desde GitHub, seleccionar `/backend`, generar su dominio público y
completar Variables con las referencias y un `DJANGO_SECRET_KEY` aleatorio propio.
Los secretos se guardan en Railway, no en Git.

`DJANGO_ALLOWED_HOSTS` debe contener el dominio público exacto y
`healthcheck.railway.app`. El endpoint `/health/` permite el chequeo HTTP interno;
el resto de la API conserva la redirección HTTPS. Los enlaces a PostgreSQL y Redis
usan las referencias privadas de Railway. No publicar puertos de las bases.

`CORS_ALLOWED_ORIGINS` se completará con el dominio HTTPS exacto del frontend.
`DJANGO_TRUST_PROXY=true` requiere que el proxy de Railway sanee
`X-Forwarded-Proto`; comprobarlo al publicar. Mantener `DJANGO_NUM_PROXIES=0`
hasta verificar la cadena real de proxies; esto puede agrupar clientes anónimos
por la dirección del proxy. No asumir una cantidad de saltos.

Dejar Start Command vacío para usar el Dockerfile. Configurar healthcheck
`/health/`, timeout de 300 segundos y reinicio ON_FAILURE. El puerto lo inyecta
Railway. Comprobar logs de migraciones y `/health/` antes de continuar.

En una sesión dentro del contenedor backend, ejecutar una vez:

```bash
python manage.py check --deploy
python manage.py seed_data
python manage.py migrate --check
```

Como alternativa, configurar temporalmente Pre-deploy Command con
`sh deployment/prepare-demo.sh` y publicar una nueva versión. Este script aplica
migraciones, carga el DEMO y comprueba las migraciones. Tras verificar la carga,
vaciar Pre-deploy Command. Así se preparó la instalación pública conservando
la cuenta que ya se había registrado.

La precarga contiene los tres usuarios DEMO, diez países, cinco años de seis
indicadores, 31 cotizaciones por moneda no USD, dos portafolios e índices.
Los históricos de demostración están identificados como simulados.
Si se usa CLI, `railway ssh` ejecuta dentro del servicio; `railway run` ejecuta
localmente y no resuelve necesariamente las direcciones privadas de las bases.

## 3. Angular

Crear frontend desde el mismo repositorio, con `/frontend` como directorio raíz.
Antes de construir, configurar:

```dotenv
API_BASE_URL=https://DOMINIO_REAL_BACKEND/api
PORT=8080
```

`API_BASE_URL` es una URL pública de build. El Dockerfile la recibe como ARG,
configura Angular y compila; un valor vacío, inseguro o incorrecto detiene la
construcción. Cambiar el dominio backend exige reconstruir el frontend.
La construcción local admite HTTP únicamente para localhost.

La imagen final sirve los archivos con Nginx, escucha en PORT y admite rutas SPA
como `/paises/CO`. Angular llama directamente al backend por HTTPS y abre su
WebSocket por WSS; este servicio estático no hace de proxy de la API.

Generar el dominio público del frontend. Configurar su healthcheck `/health/` y
completar `CORS_ALLOWED_ORIGINS` en backend con ese origen, sin barra final.
El backend utiliza el mismo origen permitido para los WebSockets.
Reiniciar/republicar backend para aplicar el cambio.

## 4. Tareas

El plan gratuito permite cinco servicios en este proyecto. La instalación pública
agrupa las tareas en el servicio `cotizaciones`, desde `/backend`, con Start
Command `python deployment/scheduled.py`, cron `*/15 * * * *`, sin healthcheck y
política de reinicio NEVER. Comparte las variables mediante referencias a `mission`.
El proceso utiliza UTC para elegir la tarea diaria y recupera alertas en cada
ejecución, incluso si la sincronización falla. Un resultado parcial termina con
estado de error para que Railway lo muestre. Los comandos coordinan recálculo y
alertas. La programación es:

| Tarea | Comando | Horario UTC | Hora Bogotá |
| --- | --- | --- | --- |
| cotizaciones | `python manage.py update_tipos_cambio` | 03:00–03:14 | 22:00 del día anterior |
| indicadores | `python manage.py sync_indicadores` | 03:15–03:29 | 22:15 del día anterior |
| recuperar-alertas | `python manage.py generar_alertas --limite 1000` | Cada 15 minutos | Cada 15 minutos |

Para estos servicios, quitar healthchecks y usar política de reinicio NEVER.
No iniciar Uvicorn ni ejecutar seed. Las tareas deben terminar tras procesar su
lote; Railway omite una ejecución si la anterior sigue activa. Un fallo parcial
se revisa en logs y en los campos de pendientes. No configurar envíos de avisos
externos sin definir el destinatario.

Si Railway omite una ejecución o la retrasa fuera de su ventana diaria, esa
sincronización espera al día siguiente; ADMIN también puede iniciarla desde la
aplicación. Si el plan permite más servicios, se pueden separar las tres tareas
con los horarios `0 3 * * *`, `15 3 * * *` y `*/15 * * * *` respectivamente.

## 5. Comprobar y registrar la entrega

- API y frontend accesibles por HTTPS, salud correcta y rutas internas recargables.
- Swagger en `/api/swagger/`, esquema JSON en `/api/schema/` y recursos estáticos accesibles.
- Login con ADMIN, ANALISTA y VIEWER; VIEWER recibe 403 al escribir.
- Dashboard, gráficos, países, históricos y fuentes disponibles.
- Crear/editar portafolio y posiciones; límites y conflicto 409; descargar PDF.
- Alertas individuales/masivas; WebSocket, reconexión y recuperación por polling.
- Sincronización ADMIN y comandos con resultados parciales visibles.
- Datos disponibles después de reiniciar backend; PostgreSQL conserva su volumen.
- Actualizar README con URL del repositorio, frontend, API y versión desplegada.
- Grabar video de 5–8 minutos y preparar el correo de entrega.

El healthcheck de Railway valida el arranque y no sustituye monitoreo continuo.
Los respaldos y una restauración de prueba quedan como recomendación operativa.

La publicación pasó 35 comprobaciones HTTP: los tres roles, diez países, índices,
dashboard, históricos, portafolios, PDF, escritura denegada a VIEWER y conflicto
de versión 409. También se verificaron conexión y ping/pong WebSocket. El
portafolio temporal de verificación se retiró mediante baja lógica.
El despachador cron tiene tres pruebas locales de horarios y manejo de errores.
La ejecución de proveedores externos puede devolver resultados parciales;
consultar los logs de la tarea antes de afirmar que todos sus datos están actualizados.

## Referencias oficiales

Consultadas el 14 de octubre de 2026:

- [Directorios y monorepos](https://docs.railway.com/deployments/monorepo).
- [Dockerfiles y argumentos de build](https://docs.railway.com/builds/dockerfiles).
- [Healthchecks y hostname](https://docs.railway.com/deployments/healthchecks).
- [Tareas cron](https://docs.railway.com/cron-jobs).
- [Infraestructura como código vigente](https://docs.railway.com/infrastructure-as-code).
