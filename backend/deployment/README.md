# Despliegue del backend

La guía vigente es [GitHub y Railway](../../deployment/RAILWAY.md).
El servicio usa el Dockerfile de backend y `sh deployment/start.sh`, que aplica
migraciones, genera estáticos y arranca Uvicorn. Seed se ejecuta por separado.

La plantilla [.env.railway.example](../.env.railway.example) contiene referencias
a PostgreSQL y Redis y las variables necesarias para HTTPS, CORS y WebSockets.
Los secretos se configuran en Railway.

`/health/` comprueba PostgreSQL y admite el chequeo HTTP interno de Railway;
la API conserva redirección HTTPS. ALLOWED_HOSTS debe incluir el dominio público
y `healthcheck.railway.app`.

Uvicorn usa dos workers y un pool de hasta cuatro conexiones PostgreSQL por
worker, más las conexiones de comandos y migraciones. Mantener
`DJANGO_DB_CONN_MAX_AGE=0`. Los límites de trabajo HTTP, WebSockets y SSE son
independientes por worker.

`DJANGO_TRUST_PROXY` permite interpretar X-Forwarded-Proto únicamente detrás de
un proxy que lo sanee. `DJANGO_NUM_PROXIES` controla la identificación de clientes
para throttling; mantener 0 hasta comprobar los saltos reales. Los proxies deben
sanear X-Forwarded-For y restringir el acceso directo a la aplicación.
