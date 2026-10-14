# Frontend — DataPulse Latam

SPA en español con Angular 22.2, TypeScript estricto, Angular Material y Chart.js.
Consume la [API Django](../backend/API.md) para datos de negocio.

## Ejecución local

Requiere Node compatible con Angular 22 (verificado con Node 24.20), pnpm 11.24
y backend con PostgreSQL, migraciones y precarga. Desde esta carpeta:

```bash
pnpm install --frozen-lockfile
pnpm start
```

Abrir http://localhost:4200. Desarrollo usa
`http://127.0.0.1:8000/api`, configurable en
[src/environments/environment.ts](src/environments/environment.ts).
El backend debe permitir el origen mediante `CORS_ALLOWED_ORIGINS`.
`pnpm local` inicia ambas capas cuando sus dependencias ya están preparadas.
Las cuentas DEMO están en el [README principal](../README.md#usuarios-de-demostración).

`pnpm-workspace.yaml` declara los scripts de dependencias permitidos para que
las instalaciones limpias con pnpm 11 sean reproducibles.

## Organización

```text
src/app/
  core/auth/       Sesión, guards e interceptor JWT
  core/services/   HTTP, países, portafolios, riesgo, alertas y tiempo real
  core/interceptors/  Errores y carga
  modules/         Auth, dashboard, países, portafolios, alertas y perfil
  shared/          Gráficos, diálogos, pipes, directivas y utilidades
  layout/          Navegación autenticada
```

Las rutas cargan componentes standalone de forma diferida. Signals y computed
mantienen estado local; alertas publica BehaviorSubject/Observable. Los formularios
usan ReactiveFormsModule. Material aporta campos, selects, autocompletado,
diálogos y avisos. Chart.js ofrece gráficos con tablas alternativas.
El mapa SVG usa geografía Natural Earth de world-atlas; `pnpm map:generate`
regenera sus coordenadas. Fuentes e iconos se sirven localmente.

## Integración

- JWT solo para la API configurada; una renovación compartida entre solicitudes.
  Si falla refresh, se limpia sesión y se redirige a login; 403 conserva sesión.
- Históricos/gráficos recorren todas las páginas; null significa sin datos.
- Nombres de portafolio con validación asíncrona y cancelación; edición envía excluir.
- Importes enviados como cadenas y validados con centavos enteros. Se comprueban
  monto, fechas, moneda USD, dos posiciones por país/tipo y capital de 50 millones.
- Toda escritura envía version. Un 409 conserva el borrador y exige revisar los
  datos recargados. Totales guardados proceden del backend.
- Previsualización local de capital e IRPC ponderado, con redondeo HALF_UP.
  El backend confirma las cifras al guardar. PDF se descarga como Blob.

La sesión abre un WebSocket en `/ws/notificaciones/`, con JWT en subprotocolo.
Refresca campanita, alertas y dashboard; conserva filtros y recupera estado por
REST al reconectar. Sin conexión en vivo usa polling cada 30 segundos.
El endpoint deriva de apiBaseUrl: HTTPS utiliza WSS. Configurar Redis y el
origen permitido en backend; [protocolo](../backend/realtime/README.md).

## Pruebas

[Comandos, requisitos y cobertura](../docs/PRUEBAS.md).
Los resultados generados quedan en output/, test-results/ y playwright-report/,
excluidos de Git.

## Producción

```bash
pnpm build
```

El resultado está en dist/frontend/browser. La configuración de producción del
repositorio usa `/api` en el mismo origen; para un build manual entre dominios,
editar [environment.production.ts](src/environments/environment.production.ts).

El Dockerfile de Railway recibe `API_BASE_URL=https://DOMINIO_BACKEND/api` antes
de compilar y configura Angular automáticamente. La imagen final sirve estáticos
con Nginx y fallback SPA; la API y WebSockets se consultan directamente por
HTTPS/WSS. [Guía y variables](../deployment/RAILWAY.md).
