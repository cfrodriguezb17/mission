# DataPulse Latam — Frontend

SPA en español implementada sobre Angular 22.2, TypeScript estricto, Angular
Material y Chart.js. Consume exclusivamente la API Django para datos de negocio.
El contrato de integración está en [backend/API.md](../backend/API.md) y el
alcance en [IMPLEMENTACION.md](IMPLEMENTACION.md).

## Ejecutar localmente

Requisitos: Node.js compatible con Angular 22 (verificado con Node 24.20), pnpm
11.24 y backend Django con PostgreSQL, migraciones y datos precargados.

Con el backend preparado, puedes iniciar ambos servicios desde esta carpeta:

```bash
pnpm local
```

O ejecutar `./run-local.sh` desde la raíz de la entrega. El
[script](tools/run-local.sh) valida dependencias, puertos, PostgreSQL y migraciones;
configura los orígenes CORS locales para el proceso y arranca ambos servidores
con recarga automática. Ctrl+C los detiene juntos. Requiere Linux, Bash 4.3+,
`setsid` y `curl`; PostgreSQL debe estar iniciado. No aplica migraciones ni carga
datos al arrancar. Para la preparación inicial o el arranque por separado:

Desde `backend`, siguiendo su [README](../backend/README.md):

```bash
python manage.py migrate
python manage.py seed_data
python -m uvicorn backend.asgi:application --host 127.0.0.1 --port 8000 --reload --lifespan off --no-proxy-headers
```

En `backend/.env`, habilitar el origen donde se abre el navegador:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
```

Reiniciar el backend si cambia esa configuración. Desde `frontend`:

```bash
pnpm install --frozen-lockfile
pnpm start
```

Abrir [http://localhost:4200](http://localhost:4200). La API de desarrollo es
`http://127.0.0.1:8000/api`, configurable en
[src/environments/environment.ts](src/environments/environment.ts).

Las cuentas de demostración creadas por `seed_data` son `admin@datapulse.com`,
`analista@datapulse.com` y `viewer@datapulse.com`, con contraseña
`DataPulse2026!`. Un registro nuevo recibe el rol VIEWER desde el backend.

## Funcionalidades

- Login, registro, persistencia y renovación JWT, perfil editable, cierre de sesión.
- Dashboard con cuatro KPI, mapa geográfico de diez países, ranking por IRPC y
  comparación de indicadores de cinco años entre uno y tres países.
- Países con búsqueda y regiones; detalle con indicadores, fuentes, simulaciones,
  cambio de 30 días, desglose de scores, evidencia e histórico completo de IRPC.
- Portafolios propios/públicos, formularios de creación/edición, posiciones,
  cierre con fecha, gráficos pie/donut y exportación PDF.
- Alertas filtrables, lectura individual/masiva y badge actualizado cada 30
  segundos. El polling se cancela al cerrar sesión.
- Acciones ADMIN de sincronización/recálculo que distinguen resultados parciales,
  faltantes y etapas pendientes, aun con respuesta HTTP 200.
- Pantalla 404, estados de carga/vacío/error, reintentos, navegación por teclado,
  foco después de navegación y menú de tablet con contención de foco y Escape.

Un IRPC alto representa **menor** riesgo. La interfaz conserva `null` como
sin datos y muestra advertencias de evidencia incompleta/simulada. El tipo de
cambio conserva el par del servidor: **USD por moneda local**.

## Arquitectura y decisiones

```text
src/app/
  core/
    auth/
      services/auth.service.ts
      guards/auth.guard.ts
      guards/role.guard.ts
      interceptors/jwt.interceptor.ts
    services/
      api.service.ts
      pais.service.ts
      portafolio.service.ts
      riesgo.service.ts
      alerta.service.ts
      loading.service.ts
      notify.service.ts
    interceptors/
      error.interceptor.ts
      loading.interceptor.ts
    models/
  modules/
    auth/          login/, register/, auth-form/
    dashboard/     mapa-riesgo/, kpi-cards/, tabla-ranking/, grafico-tendencias/
    paises/        lista-paises/, detalle-pais/
    portafolios/   lista/, crear/, detalle/, posicion-form/, distribucion-chart/
    alertas/       panel-alertas/, alerta-badge/
    perfil/
  shared/
    loading-spinner/
    confirm-dialog/
    pipes/         catalogo.pipe.ts
    directives/    role.directive.ts
    charts/
    page-state/
    risk-badge/
    not-found/
    utils/
  layout/
  testing/
```

La organización sigue el árbol de la sección 2.1 del documento. Cada bloque del
dashboard y el badge de alertas tiene su propio componente. Login y registro
cuentan con entradas independientes y reutilizan el formulario de autenticación.
La directiva compartida `appRole` muestra las acciones administrativas según el
rol; `catalogo` traduce códigos de riesgo para la presentación. Los guards y los
interceptores se mantienen en archivos individuales.

Las rutas cargan componentes standalone de forma diferida. Se usan signals y
`computed` para estado local/derivado; AlertaService publica estado mediante
`BehaviorSubject`/`Observable`. Los formularios usan ReactiveFormsModule, conforme
al requisito, y las peticiones se cancelan al cambiar filtros o salir de la vista.
Los servicios singleton usan `@Service`, disponible en Angular 22.

Material ofrece campos, autocompletado, selects, diálogos, menús, paginación y
snackbars. Chart.js permite gráficos ligeros y accesibles mediante tablas de
valores alternativas. El mapa usa SVG y geografía Natural Earth distribuida por
`world-atlas` (dominio público), sin servicios de mapas externos; la geometría se
regenera con `pnpm map:generate`. Fuentes e iconos se sirven localmente, sin
necesitar Google Fonts al compilar ni navegar.

## Integración y validaciones

- ApiService recorre todas las páginas de históricos/gráficos, con máximo 100
  resultados por solicitud, sin reenviar credenciales a URLs de paginación ajenas.
- Interceptores agregan JWT solo a la API configurada, comparten una renovación
  para solicitudes concurrentes y evitan bucles. Si falla la renovación, limpian
  sesión y redirigen a login. Los errores 403 no cierran una sesión válida.
- La carga cuenta solicitudes simultáneas; el polling no bloquea la interfaz.
  Errores de campo se conservan en el formulario y los errores de red/HTTP se
  muestran también como avisos. Un 429 muestra `Retry-After`.
- Los nombres se recortan y verifican con 350 ms de espera y cancelación. La
  edición envía `excluir=id`. Un error al verificar nunca significa disponible.
- El dinero se conserva como cadena al enviar y se valida en **centavos enteros**.
  El input muestra miles con coma y decimales con punto, p. ej. `1,234.56`;
  las lecturas se presentan con formato español. Se validan los límites de cada
  posición, capital activo de 50 millones, dos posiciones por país/tipo, moneda
  USD y fechas, excluyendo la posición que se edita de las sumas.
- Cada escritura y DELETE envía `version`. Ante 409, se recarga el portafolio,
  se conserva el borrador y se exige revisar los cambios antes de reintentar.
  Los totales y distribuciones guardados proceden del resumen del backend y se refrescan
  después de cada modificación. Los flags de permisos gobiernan las acciones.
- Al agregar/editar una posición se muestra «Así quedaría tu portafolio», con
  total activo, IRPC ponderado y cantidad de posiciones. Consulta los últimos
  índices al abrir el diálogo; los cambios del formulario se calculan localmente
  con centavos e IRPC de dos decimales mediante BigInt y redondeo HALF_UP, igual
  que el backend. Excluye posiciones cerradas y sustituye la editada sin duplicar.
  Señala capital sin riesgo, evidencia parcial/simulada y fallos de consulta con
  reintento. No guarda ni hace peticiones por cada cambio. El backend confirma
  las cifras al guardar; una recarga por 409 actualiza también la estimación.
- El PDF se descarga como Blob con nombre de Content-Disposition, se libera el
  Object URL y se interpreta el JSON de error si el servidor responde con uno.

## Alertas y dashboard en vivo

La sesión abre un único WebSocket en `/ws/notificaciones/`. La campanita, el centro
de alertas y el dashboard se refrescan al recibir avisos. Los filtros y datos
visibles se conservan durante las consultas de fondo. Un aviso discreto anuncia
las nuevas alertas; el detalle y las lecturas personales se obtienen por REST.

El endpoint se deriva de `apiBaseUrl`: HTTP usa `ws`, HTTPS usa `wss`; producción
con `/api` usa el mismo origen. El JWT se envía en el subprotocolo, nunca en la URL.
La conexión se renueva antes de expirar el access, se recupera con espera creciente
y se cierra al salir de la sesión. Cada reconexión consulta el estado actual para
recuperar cambios ocurridos durante la interrupción.

Los avisos se agrupan desde 250 ms, con una recarga como máximo cada cinco segundos
durante ráfagas. Con WebSocket conectado se suspende el polling; si falla se
consultan el contador y el listado de alertas cada 30 segundos. Sin red se
conservan los datos y se reintenta al recuperar conexión.

El backend requiere Uvicorn, Redis (`DJANGO_REALTIME_REDIS_URL`, o
`DJANGO_REDIS_URL`) y el origen del frontend en `CORS_ALLOWED_ORIGINS`.
El proxy de producción debe enviar `/ws/` a Uvicorn con `Upgrade` y `Connection`;
[deployment/nginx.conf](deployment/nginx.conf) incluye esta ruta.
[Evidencia y prueba real reproducible](docs/realtime-20261013/INFORME.md).

## Verificación

```bash
pnpm build
pnpm test:unit
pnpm test:integration
pnpm test:e2e
```

`pnpm test:pyramid` ejecuta **unitarias → integración → e2e** y se detiene ante
el primer fallo. `pnpm test --watch=false` sigue ejecutando todas las pruebas de
Vitest juntas. La integración WebSocket se verifica con **120 pruebas unitarias
e integradas**, pruebas de navegador con eventos controlados y una prueba aislada
con Django, PostgreSQL y Redis reales. Los resultados de la entrega anterior
fueron 60 unitarias, 39 integradas y 17 de navegador.

Las unitarias e integradas no necesitan servidores. Playwright inicia Angular
si hace falta; la suite completa requiere Django local con los datos de
demostración. Instalar Chromium una vez con `pnpm exec playwright install chromium`.
`e2e/frontend.spec.ts` usa el backend real para login, roles, gráficos, país,
CRUD, PDF y conflicto 409. Crea un portafolio temporal y lo elimina lógicamente
al terminar. Los archivos e2e de flujos, casos límite y previsualización controlan las respuestas HTTP para
registro/perfil, filtros, alertas, errores y renovación tardía de sesión.

La guía de [pruebas y evidencia Red → Green → Refactor](docs/testing/README.md)
explica la cobertura por nivel, los defectos reproducidos antes de corregirlos,
los logs de cada fase y cómo ejecutar cada suite. Incluye regresiones para
fechas imposibles y respuestas tardías después de cerrar sesión. `e2e/realtime.spec.ts`
añade eventos WebSocket, reconexión, recuperación y polling de respaldo.
`e2e/realtime-live.spec.ts` solo se activa mediante `tools/verify-realtime.py`, que
crea y elimina una base temporal; no utiliza la base de demostración. Axe comprueba
WCAG A/AA en las pantallas principales; el navegador verifica escritorio y tablet.

La configuración admite `E2E_BASE_URL` y `E2E_PASSWORD` opcionales. Los artefactos
de cada ejecución se guardan en `test-results/` y `playwright-report/`
(ignorados por Git).

## Producción

```bash
pnpm build
```

El resultado está en `dist/frontend/browser`. Producción usa `/api` en el mismo
origen por defecto; configurar un proxy a Django o editar
[src/environments/environment.production.ts](src/environments/environment.production.ts)
con la URL HTTPS del backend **antes de compilar** si está en otro dominio.
Estos archivos solo contienen configuración pública; no incluir secretos.

Configurar HTTPS, CORS con el origen público exacto y fallback SPA a `index.html`
para rutas como `/paises/CO`. Un servidor Nginx de referencia está en
[deployment/nginx.conf](deployment/nginx.conf). `/api/` debe resolverse hacia
Django y nunca hacia el fallback HTML. Lo mismo aplica a `/ws/`, incluyendo la
actualización de protocolo y un timeout superior al intervalo de ping.
La aplicación está implementada y probada
localmente; la publicación y la URL pública quedan a cargo del despliegue.
