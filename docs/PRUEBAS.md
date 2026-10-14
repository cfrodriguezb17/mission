# Pruebas

## Integracion continua

El workflow [CI](../.github/workflows/ci.yml) se ejecuta en GitHub Actions para
push a `main`, pull requests y ejecución manual. Utiliza permisos de lectura,
cancela ejecuciones anteriores de la misma rama y tiene tiempos máximos por job.
Las acciones están fijadas a revisiones concretas. Las bases, cuentas DEMO y
credenciales del pipeline son temporales; no accede a la base de Railway.

| Job | Comprobaciones |
| --- | --- |
| Backend y OpenAPI | Django, ausencia de migraciones pendientes, migración desde cero, estáticos, esquema válido sin advertencias, suite completa y tareas programadas |
| Frontend y build | Instalación con lockfile, pruebas unitarias/integración y compilación de producción con configuración de Railway |
| Navegador con API real | PostgreSQL y Redis temporales, API con seed, Chromium, flujos reales y casos con API controlada |

La prueba `realtime-live.spec.ts` requiere su runner específico y se omite en
este job; los tests de backend incluyen conexiones reales y los escenarios
de navegador de reconexión usan eventos controlados. Ante fallos del navegador,
GitHub conserva el reporte, capturas/trazas y log de la API durante siete días.

En Railway, **Wait for CI** debe estar activo en `mission`, `frontend` y
`cotizaciones`. Un resultado fallido bloquea la publicación automática de ese
commit. Los watch paths siguen limitando reconstrucciones a cada carpeta.

## Backend

Desde backend, con el entorno virtual activado y PostgreSQL de pruebas. El rol
necesita CREATEDB y acceso a la base de mantenimiento postgres.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
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
python manage.py test common.tests.test_openapi --noinput
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
