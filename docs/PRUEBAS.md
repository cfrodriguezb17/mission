# Pruebas

## Backend

Desde backend, con el entorno virtual activado y PostgreSQL de pruebas. El rol
necesita CREATEDB y acceso a la base de mantenimiento postgres.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
```

Para verificar migraciones originales desde una base nueva y ejecutar la suite:

```bash
python manage.py verify_migrations
```

El verificador elimina su base temporal al pasar y la conserva ante fallos para
diagnóstico. No modifica la base principal. Las pruebas cubren modelos,
serializadores, reglas IRPC, roles, validaciones, concurrencia, JWT/HTTP,
sincronizaciones parciales, auditoría, PDF, Redis y WebSockets.

La prueba de documentación pública puede ejecutarse sin base de datos:

```bash
python manage.py test common.tests.test_documentation --noinput
```

La auditoría HTTP de operaciones usa una base temporal exclusiva y guarda su
salida en backend/output/auditoria-endpoints:

```bash
python tools/audit_endpoints.py
```

## Frontend

Desde frontend, con las dependencias instaladas:

```bash
pnpm build
pnpm test:unit
pnpm test:integration
pnpm exec playwright install chromium
pnpm test:e2e
```

`pnpm test:pyramid` ejecuta unitarias, integración y navegador en orden.
Las unitarias/integradas no requieren servidores. Playwright arranca Angular;
la suite completa requiere Django local con seed_data.

Los casos con API controlada comprueban formularios, filtros, errores, tokens,
conflictos, previsualización y reconexión. Los casos con Django comprueban login,
roles, gráficos, países, CRUD, PDF y versiones. Axe revisa accesibilidad A/AA;
los escenarios incluyen escritorio y tablet.

La prueba en vivo de WebSockets usa PostgreSQL y Redis temporales, dos workers
Uvicorn y el navegador. Requiere permiso de crear bases y redislite, incluido
en requirements-dev.txt:

```bash
../backend/.venv/bin/python tools/verify-realtime.py
```

Esta herramienta guarda resultados en frontend/output/realtime, elimina su base
temporal y detiene sus procesos. El caso realtime-live.spec.ts se omite cuando
no se ejecuta mediante ese runner. Las salidas generadas están excluidas de Git.

## Comprobación de producción

La validación pública se realiza después de desplegar: salud, HTTPS, tres roles,
CORS, rutas SPA, datos precargados, posiciones, PDF, WebSockets, tareas y
persistencia. [Pasos de Railway](../deployment/RAILWAY.md#5-comprobar-y-registrar-la-entrega).
