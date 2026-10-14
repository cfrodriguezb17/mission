# Decisiones técnicas del backend

Estas son las decisiones técnicas del backend de DataPulse Latam, excluyendo las
herramientas obligatorias de la prueba.

**\*** indica una alternativa de comparación; no consta como evaluada formalmente.

| Elección | Por qué se eligió | Alternativas consideradas |
| --- | --- | --- |
| **Monolito modular** | Separa responsabilidades por dominio y mantiene transacciones y despliegue sencillos. | **Microservicios:** añadirían coordinación sin una necesidad demostrada de escalado independiente. |
| **PostgreSQL** | Sus restricciones, decimales y bloqueos de fila protegen importes y posiciones ante modificaciones simultáneas. | **SQLite:** simplifica el desarrollo, pero no permite verificar los mismos bloqueos concurrentes. |
| **psycopg con pool** | Reutiliza conexiones a PostgreSQL. Las mediciones locales respaldaron conservar el pool y las consultas preparadas. | **Conexiones nuevas por petición:** empeoraron el rendimiento medido. Pools mayores no mejoraron todos los escenarios. |
| **SimpleJWT** | Implementa la autenticación JWT requerida mediante una librería integrada con DRF. | **Implementación propia\*:** exigiría mantener firma, validación y renovación de tokens. |
| **Comandos Django + tareas programadas** | Reutilizan servicios de negocio para sincronizar datos, calcular riesgo y recuperar alertas sin una cola adicional. | **Celery:** se reconsideraría para trabajos largos, seguimiento y ejecución asíncrona bajo demanda. |
| **Redis** | Comparte caché y transporta avisos entre workers, mientras PostgreSQL conserva los datos persistentes. | **Memoria local\*:** no coordina procesos. La consulta directa a PostgreSQL se mantiene como respaldo de la caché. |
| **Uvicorn + ASGI + Channels + channels-redis** | Permiten HTTP, WebSockets y SSE con coordinación entre workers, conservando las transacciones síncronas del CRUD. | **Gunicorn con WSGI:** utilizado como referencia de rendimiento; no cubre por sí solo WebSockets. |
| **ReportLab** | Genera PDF en memoria, con tablas multipágina y sin navegador ni servicio externo. | **WeasyPrint o navegador headless\*:** permitirían reutilizar HTML/CSS, con otras dependencias de renderizado. |
| **urllib** | Los clientes HTTP implementan tiempos límite y reintentos usando la biblioteca estándar de Python. | **Requests o HTTPX\*:** ofrecen otra interfaz; no está documentado el motivo histórico de no incorporarlos. |
| **WhiteNoise** | Sirve los archivos estáticos de Django con compresión y caché desde la aplicación. | **Nginx o almacenamiento/CDN separado\*:** requieren infraestructura adicional para esos archivos. |
| **drf-spectacular con sidecar** | Genera y valida OpenAPI e incluye los recursos de documentación interactiva. | **drf-yasg\*:** otra opción admitida para documentar la API. |
| **pypdf + redislite** | Permiten comprobar el contenido de los PDF y ejecutar pruebas con Redis temporal. Son dependencias de desarrollo. | **Inspección manual y Redis externo\*:** requieren más preparación y ofrecen menor automatización. |
| **Docker** | Empaqueta el backend con sus dependencias y un arranque reproducible. | **Instalación directa en servidor\*:** exige mantener el entorno por separado. |
| **Railway** | Integra el backend, PostgreSQL, Redis y tareas programadas en un mismo entorno. | **Render, Fly.io o una máquina virtual\*:** no consta una comparación formal de proveedores. |
| **GitHub Actions** | Ejecuta pruebas, verifica migraciones y valida OpenAPI antes de publicar. | **Otro sistema de CI o verificaciones manuales\*:** requieren mantener otro flujo de validación. |

## Fuentes

- [Arquitectura y decisiones técnicas](ARQUITECTURA.md).
- [Configuración de ASGI, pool y tiempo real](backend/realtime/README.md).
- [Contrato de API y exportación PDF](backend/API.md).
