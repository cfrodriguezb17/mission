# DataPulse Latam — Frontend

SPA en español implementada sobre Angular 22.2, TypeScript estricto, Angular
Material y Chart.js. Consume exclusivamente la API Django para datos de negocio.
El contrato de integración está en [backend/API.md](../backend/API.md) y el
alcance en [IMPLEMENTACION.md](IMPLEMENTACION.md).

## Ejecutar localmente

Requisitos: Node.js compatible con Angular 22 (verificado con Node 24.20), pnpm
11.24 y backend Django con PostgreSQL, migraciones y datos precargados.

Desde `backend`, siguiendo su [README](../backend/README.md):

```bash
python manage.py migrate
python manage.py seed_data
python manage.py runserver 127.0.0.1:8000
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
    auth/          sesión, guards de autenticación/rol, interceptor JWT
    models/        contratos tipados y catálogos
    services/      API, países, riesgo, portafolios, alertas, carga y avisos
  features/
    auth/          login y registro
    dashboard/     KPI, mapa, ranking y tendencias
    countries/     listado y detalle
    portfolios/    listado, creación, detalle y diálogos de edición
    alerts/        panel y filtros
    profile/       edición del perfil
  layout/          navegación autenticada y usuario
  shared/          gráficos, confirmación, validadores, estados y 404
```

Las rutas cargan componentes standalone de forma diferida. Se usan signals y
`computed` para estado local/derivado; AlertService publica estado mediante
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
  Los totales y distribuciones proceden del resumen del backend y se refrescan
  después de cada modificación. Los flags de permisos gobiernan las acciones.
- El PDF se descarga como Blob con nombre de Content-Disposition, se libera el
  Object URL y se interpreta el JSON de error si el servidor responde con uno.

## Verificación

```bash
pnpm build
pnpm test:unit
pnpm test:integration
pnpm test:e2e
```

`pnpm test:pyramid` ejecuta **unitarias → integración → e2e** y se detiene ante
el primer fallo. `pnpm test --watch=false` sigue ejecutando todas las pruebas de
Vitest juntas. Resultado verificado: **43 unitarias, 34 integradas y 14 de
navegador**, todas pasan.

Las unitarias e integradas no necesitan servidores. Playwright inicia Angular
si hace falta; la suite completa requiere Django local con los datos de
demostración. Instalar Chromium una vez con `pnpm exec playwright install chromium`.
`e2e/frontend.spec.ts` usa el backend real para login, roles, gráficos, país,
CRUD, PDF y conflicto 409. Crea un portafolio temporal y lo elimina lógicamente
al terminar. Los otros dos archivos e2e controlan las respuestas HTTP para
registro/perfil, filtros, alertas, errores y renovación tardía de sesión.

La guía de [pruebas y evidencia Red → Green → Refactor](docs/testing/README.md)
explica la cobertura por nivel, los defectos reproducidos antes de corregirlos,
los logs de cada fase y cómo ejecutar cada suite. Incluye regresiones para
fechas imposibles y respuestas tardías después de cerrar sesión. Axe comprueba
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
Django y nunca hacia el fallback HTML. La aplicación está implementada y probada
localmente; la publicación y la URL pública quedan a cargo del despliegue.
