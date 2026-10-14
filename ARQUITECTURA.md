# Arquitectura de la solución — DataPulse Latam

Arquitectura de referencia de la prueba técnica. Backend y frontend están
implementados; ASGI, Redis y notificaciones en tiempo real se incorporaron en
etapas posteriores. El estado de implementación y las verificaciones se recogen
en [Estado de entrega](docs/ENTREGA.md). Las secciones de evolución describen
alternativas, no componentes obligatorios pendientes.

Estado del backend: `accounts`, `countries`, `economics`, `risk`, `alerts`,
`portfolios`, `audit`, `dashboard` y `reporting` están implementados, con Usuario, Moneda, Pais, TipoIndicador,
IndicadorEconomico, TipoCambio, IndiceRiesgo, Alerta, LecturaAlerta, Portafolio,
Posicion y LogActividad. `backend.workflows` coordina
sincronización, riesgo y alertas. Dashboard aporta KPI, mapa y tendencias; reporting
exporta PDF con permisos y auditoría. Frontend y publicación pública tienen
seguimiento separado. Common ya conecta errores uniformes, throttling, CORS y
logs de requests. Arranque de producción y timers preparados; publicación y
activación pendientes de infraestructura.

La recuperación de INFO añade `economics.LoteActualizacion` como almacenamiento
técnico de evidencia pendiente. Economics registra el lote junto a cada cambio,
sin depender de alerts. Alerts consume esos lotes y confirma alerta/marcador
juntos. El comando `generar_alertas` y los workflows reintentan sin necesitar la
respuesta original de sincronización; PostgreSQL mantiene la idempotencia.

Se utilizará un monolito modular en Django, con capas ligeras dentro de cada
módulo, una SPA Angular y PostgreSQL. Las integraciones externas y el cálculo
del IRPC se separan para poder probarlos sin depender de proveedores HTTP.

## Diagrama general

```text
                          +-------------------------+
                          | Usuario                 |
                          | ADMIN / ANALISTA / VIEWER|
                          +------------+------------+
                                       |
                                     HTTPS
                                       v
             +------------------------------------------------+
             | FRONTEND: ANGULAR + ANGULAR MATERIAL           |
             |                                                |
             | Auth | Dashboard | Paises | Portafolios | Alertas|
             |                                                |
             | Rutas lazy + guards + formularios + estado      |
             | Servicios HTTP + interceptores JWT/error/carga  |
             +-------------------------+----------------------+
                                       |
                                 HTTPS / REST / JSON
                                       v
 +--------------------------------------------------------------------------+
 | BACKEND: DJANGO + DJANGO REST FRAMEWORK — MONOLITO MODULAR                |
 |                                                                          |
 | API: urls/routers -> views -> serializers / permisos                      |
 | Transversal: JWT, filtros, paginacion, throttling, errores y request logs   |
 |                                                                          |
 | +-------------------+ +-------------------+ +--------------------------+ |
 | | accounts          | | countries         | | economics                | |
 | | Usuario / roles   | | Paises / monedas  | | Indicadores / cotizaciones| |
 | | Registro / perfil | | Datos generales   | | Historicos / sincronizar  | |
 | +-------------------+ +-------------------+ +--------------------------+ |
 | +-------------------+ +-------------------+ +--------------------------+ |
 | | portfolios        | | risk              | | alerts                   | |
 | | Posiciones        | | Calculo IRPC      | | Alertas / lecturas       | |
 | | Reglas / resumen  | | Scores / historico| | Resumen / severidad      | |
 | +-------------------+ +-------------------+ +--------------------------+ |
 | +-------------------+ +-------------------+ +--------------------------+ |
 | | reporting         | | dashboard         | | audit                    | |
 | | Exportacion PDF   | | KPIs / mapa       | | Registro de actividad    | |
 | |                   | | Tendencias        | |                          | |
 | +-------------------+ +-------------------+ +--------------------------+ |
 |                                                                          |
 | Servicios de negocio + consultas (selectors) + modelos Django             |
 |                                                                          |
 | +----------------------------------------------------------------------+ |
 | | integrations: clientes HTTP, timeouts, reintentos limitados y mapeo    | |
 | | World Bank                 ExchangeRate                REST Countries| |
 | +----------------------------------------------------------------------+ |
 +-------------------------+----------------------------+-------------------+
                           |                            |
                        ORM Django                  HTTPS / JSON
                           v                            v
                 +-------------------+        +----------------------------+
                 | PostgreSQL        |        | APIs externas              |
                 | Datos / historico |        | World Bank / ExchangeRate  |
                 | Constraints      |        | REST Countries             |
                 +-------------------+        +----------------------------+

 +------------------------------+
 | Scheduler                    |
 | Sincronizaciones programadas |
 +---------------+--------------+
                 |
                 v
 +----------------------------------+
 | Comandos Django                  |
 | Sync indicadores / tipos cambio  |
 | Reutilizan servicios del backend |
 +----------------------------------+

 Evolucion opcional para ejecucion asincrona bajo demanda:

 API / Scheduler -> Redis (cola) -> Worker Celery -> mismos servicios Django
                                              -> PostgreSQL / APIs externas
```

Frontend y backend pueden desplegarse por separado. El backend conserva una
única aplicación y una base de datos compartida. Un worker Celery ejecuta el
mismo código de negocio en otro proceso; no es un microservicio.

## Estructura objetivo

```text
mission/
|-- ARQUITECTURA.md
|-- backend/
|   |-- manage.py
|   |-- backend/                 Configuracion, rutas principales, ASGI/WSGI
|   |-- accounts/                Usuario personalizado, JWT, perfil y roles
|   |-- countries/               Pais y Moneda
|   |-- economics/               Indicadores, tipos de cambio y sincronizacion
|   |-- portfolios/              Portafolios, posiciones y sus reglas
|   |-- risk/                    IRPC y resultados historicos
|   |-- alerts/                  Alertas y lecturas por usuario
|   |-- reporting/               Reportes PDF
|   |-- dashboard/               Consultas agregadas para KPIs, mapa y graficos
|   |-- audit/                   LogActividad
|   |-- integrations/            Adaptadores de proveedores externos
|   `-- common/                  Errores, paginacion y utilidades transversales
`-- frontend/
    `-- src/app/
        |-- core/                Sesion, guards e interceptores
        |-- features/
        |   |-- auth/
        |   |-- dashboard/
        |   |-- countries/
        |   |-- portfolios/
        |   `-- alerts/
        `-- shared/              Componentes, pipes y directivas compartidos
```

Dentro de cada módulo de negocio, crear únicamente los archivos necesarios:

```text
urls.py -> views.py -> services.py -> models.py -> PostgreSQL
              |            |
              |            `-> Servicios publicos de otros modulos
              |                o adaptadores externos
              |-- serializers.py: formato, validacion de entrada y salida
              |-- permissions.py: acceso a endpoints y objetos
              `-- selectors.py: consultas y agregaciones de lectura

Otros archivos: admin.py, migrations/, tests/ y, cuando aplique,
management/commands/ o tasks.py.
```

## Límites y dependencias

- `accounts` gestiona identidad. Los modelos relacionados referencian al usuario
  mediante `settings.AUTH_USER_MODEL`.
- `countries` es dueño de países y monedas; `economics` los referencia para
  almacenar indicadores y cotizaciones.
- `risk` consulta datos económicos y ejecuta funciones de cálculo independientes
  de HTTP. Guarda scores, datos faltantes y el desglose de cada cálculo.
- `portfolios` gestiona posiciones y consulta los resultados de riesgo para
  calcular exposición y riesgo ponderado.
- `alerts` almacena notificaciones y lecturas; los servicios de sincronización y
  riesgo se coordinan con su generación mediante `backend.workflows`, sin
  importar alerts desde esos módulos. Su clave única identifica eventos por
  regla/evidencia; las lecturas son independientes por usuario.
- `dashboard` y `reporting` consumen consultas de los módulos. No duplican reglas
  de cálculo ni mantienen copias de las entidades de negocio.
- `audit` registra acciones realizadas. `common` contiene infraestructura
  reutilizable y no depende de los módulos de negocio ni contiene sus reglas.
  Ya aporta paginación, ordenamiento estricto, entrada JSON estricta, filtros
  de fechas/booleanos, comprobaciones generales de rol y logging JSON.
  Consumidores y contratos en [common](backend/common/README.md).
- `audit` registra explícitamente las escrituras dentro de sus transacciones,
  las consultas GET autorizadas y los resúmenes de tareas desde workflows.
  Sus metadatos tipados excluyen secretos y valores de formularios. El admin
  es de consulta para ADMIN. [Contratos y cobertura](backend/audit/README.md).
- Las lecturas simples pueden usar el ORM; las operaciones que modifican datos
  de otro módulo pasan por sus servicios públicos. Evitar dependencias cíclicas.

## Datos y normalización

El diccionario completo, las restricciones y las decisiones de almacenamiento
están en [Modelo de datos normalizado](backend/MODELO_DATOS.md). Ese documento
es la referencia del esquema vigente. Los diagramas HTML de docs se actualizaron
desde las doce entidades; incluyen TipoIndicador y LecturaAlerta. Se conserva
la versión anterior en docs/historial y el SVG en backend/docs/modelo-normalizado.svg.

```text
Usuario 1 ----- N Portafolio 1 ----- N Posicion N ----- 1 Pais
   |                                                      |
   |                                                      +-- N:1 Moneda
   |                                                      +-- 1:N IndicadorEconomico
   |                                                      +-- 1:N IndiceRiesgo
   |                                                      `-- 1:N Alerta
   +-- 1:N Alerta (destinatario opcional; null = global)
   +-- 1:N LogActividad
   `-- 1:N LecturaAlerta N:1 Alerta

Moneda 1 ----- N TipoCambio (moneda_origen)
Moneda 1 ----- N TipoCambio (moneda_destino)
TipoIndicador 1 ----- N IndicadorEconomico
```

Separar `Moneda` evita repetir su nombre y permite cotizaciones entre monedas,
sin utilizar un código monetario de país como identificador único. La lectura de
alertas globales se registra por usuario; el campo `leida` de la API se obtiene
para el usuario autenticado. `TipoIndicador` concentra la unidad y el código
World Bank; las observaciones guardan país, tipo, año, valor y procedencia.
Usuario ya usa únicamente email como identidad de acceso: la migración
incremental `accounts.0002_remove_username` eliminó la columna duplicada.
Variación cambiaria y nivel de riesgo se calculan para la API; los resultados
IRPC se conservan como instantáneas históricas con versión de fórmula.

Constraints: indicador único por país/tipo/año; portafolio único por
usuario/nombre; cotización diaria única por origen/destino/fecha (una observación
por par y día, con su fuente); lectura única por usuario/alerta; salida posterior a entrada;
scores entre 0 y 100. Usar decimales para montos y cotizaciones.

## Flujos principales

```text
Crear posicion:
Angular -> POST API -> JWT y permisos -> serializer -> servicio portfolios
        -> transaccion + bloqueo del portafolio
        -> validar monto total, moneda y posiciones activas
        -> guardar posicion + auditoria -> respuesta

Sincronizar indicadores:
ADMIN o scheduler -> servicio economics -> adaptador World Bank
        -> guardar datos validos por pais -> registrar fallos parciales
        -> recalcular IRPC -> guardar desglose -> generar alertas

Actualizar cotizaciones:
Scheduler -> servicio economics -> adaptador ExchangeRate
        -> normalizar sentido del par -> guardar tasa diaria
        -> calcular variacion -> alertar si supera el umbral

Exportar portafolio:
Angular -> GET API -> permiso de lectura -> consulta de resumen
        -> capturar posiciones y últimos riesgos bajo bloqueo del portafolio
        -> liberar bloqueo -> servicio reporting -> PDF -> EXPORT -> descarga
```

### Permisos de portafolios y edición simultánea

Regla acordada: un portafolio público es visible para todos los usuarios
autenticados y editable por ANALISTA y ADMIN. Esto incluye agregar, editar y
cerrar posiciones. Un portafolio privado solo puede ser editado por su
propietario con rol ANALISTA o ADMIN, o por cualquier ADMIN.

| Acción | ADMIN | ANALISTA | VIEWER |
| --- | --- | --- | --- |
| Consultar portafolios y exportar PDF | Todos | Propios y públicos | Propios y públicos |
| Crear portafolios | Sí | Sí | No |
| Editar portafolios privados y sus posiciones | Todos | Propios | No |
| Editar portafolios públicos y sus posiciones | Todos | Todos los públicos | No |
| Eliminar portafolios o cambiar su visibilidad | Todos | Propios | No |

Hacer público un portafolio debe indicar en la interfaz que los analistas
podrán editarlo. El propietario se conserva aunque otro analista lo modifique.

El cliente envía la versión del portafolio en cada operación que modifica el
portafolio o sus posiciones. El backend bloquea la fila del portafolio, comprueba
los permisos actuales y la versión, valida las reglas y guarda los cambios
incrementando la versión dentro de la misma transacción. Si la versión ya cambió,
devuelve HTTP 409 con un mensaje en español; el cliente debe recargar los datos
y permitir revisar los cambios antes de reenviarlos, sin sobrescritura automática.
Así, dos analistas que abren la versión 7 no pueden sobrescribirse: el primer
guardado crea la versión 8 y el segundo recibe un conflicto.

Las llamadas externas se realizan fuera de transacciones largas de base de datos.

## Decisiones de implementación

- Empezar con comandos Django programados, permitidos por la prueba. Para el
  endpoint bajo demanda, reutilizar el servicio con tiempos acotados; si se
  necesita responder inmediatamente, añadir Celery y devolver un identificador
  de trabajo consultable. No ejecutar trabajos con hilos improvisados en la API.
- Guardar datos obtenidos y permitir fallos parciales por país. Las consultas del
  usuario utilizan datos persistidos, sin depender de una API externa en cada visita.
- Datos seed para poder demostrar la aplicación sin conectividad. Identificar
  expresamente los históricos simulados y su procedencia.
- Aplicar la matriz de roles y propiedad en el backend; los guards de Angular
  complementan la experiencia de uso. Público habilita lectura para todos y
  edición para ANALISTA y ADMIN; eliminar o cambiar visibilidad queda reservado
  al propietario con permiso de escritura o a ADMIN.
- Configurar HTTPS, CORS, secretos por entorno y logging estructurado.
- Ampliar `common` de forma incremental conforme los módulos necesiten piezas
  compartidas: paginación, comprobaciones generales de rol, errores y logging.
  Incorporar cada pieza con sus consumidores y comprobaciones. Las reglas de
  propiedad, posiciones, capital y riesgo permanecen en sus módulos de negocio.
- Probar especialmente IRPC, permisos, reglas de posiciones, concurrencia y
  errores parciales de sincronización.
- IRPC implementado con la transcripción de la sección 1.4 proporcionada por
  el usuario. Reglas y decisiones de `irpc-v1` en [risk](backend/risk/README.md):
  indicadores en riesgo, años completos, faltantes, volatilidad poblacional y
  depreciación del par local/USD. Contrastado con prueba.md: 9,2 % penaliza
  10 puntos según el algoritmo; su ejemplo resta 25. Se documenta esa discrepancia
  y un ejemplo consistente con irpc-v1, sin modificar la fórmula.

Los microservicios se reconsiderarían si aparecen necesidades comprobadas de
despliegue independiente, equipos distintos o escalado específico por dominio.
