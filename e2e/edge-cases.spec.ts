import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { country, envelope, session } from './support/session';
test('ADMIN informa sincronización parcial y recálculo completo', async ({ page }) => {
  await session(page, 'ADMIN');
  await page.route('**/api/paises/sync-indicadores/', (route) =>
    route.fulfill({
      json: {
        estado: 'PARCIAL',
        errores: [],
        faltantes: [{ pais: 'CO' }],
        recalculo_y_alertas_pendientes: true,
      },
    }),
  );
  await page.route('**/api/riesgo/calcular/', (route) =>
    route.fulfill({
      json: { calculados: [1], errores: [], alertas: { creadas: 0, pendientes: 0, errores: [] } },
    }),
  );
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Sincronizar indicadores' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Proceso parcial:' })).toBeVisible();
  await page.getByRole('button', { name: 'Recalcular riesgos' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Proceso completado.' })).toBeVisible();
});
test('red sin conexión muestra error, conserva navegación y permite reintentar', async ({
  page,
}) => {
  await session(page);
  let offline = true;
  await page.route('**/api/paises/?*', async (route) => {
    if (offline) await route.abort('internetdisconnected');
    else await route.fulfill({ json: envelope([country]) });
  });
  await page.goto('/paises');
  await expect(
    page.getByRole('heading', { name: 'No pudimos cargar la información' }),
  ).toBeVisible();
  offline = false;
  await page.getByRole('button', { name: 'Reintentar' }).click();
  await expect(page.getByRole('heading', { name: 'Colombia', exact: true })).toBeVisible();
});
test('sesión expirada vuelve al login sin bucle', async ({ page }) => {
  await session(page);
  await page.route('**/api/auth/me/', (route) =>
    route.fulfill({ status: 401, json: { error: { mensaje: 'Token expirado' } } }),
  );
  await page.route('**/api/auth/refresh/', (route) =>
    route.fulfill({ status: 401, json: { error: { mensaje: 'Refresh expirado' } } }),
  );
  await page.goto('/paises');
  await expect(page).toHaveURL(/login/);
  await expect(page.getByRole('heading', { name: 'Inicia sesión', exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('datapulse.access'))).toBeNull();
});
test('alertas, filtros, lecturas y badge mantienen el estado', async ({ page }) => {
  await session(page);
  let read = false;
  const alert = () => ({
    id: 99,
    pais: 'CO',
    tipo_alerta: 'RIESGO',
    severidad: 'WARNING',
    titulo: 'Cambio de riesgo de prueba',
    mensaje: 'El IRPC disminuyó respecto al cálculo anterior.',
    fecha_creacion: '2026-10-13T10:00:00Z',
    leida: read,
  });
  await page.route('**/api/alertas/resumen/', (route) =>
    route.fulfill({ json: { total: 1, no_leidas: read ? 0 : 1 } }),
  );
  await page.route('**/api/alertas/?*', (route) => route.fulfill({ json: envelope([alert()]) }));
  await page.route('**/api/alertas/99/leer/', (route) => {
    read = true;
    return route.fulfill({ json: alert() });
  });
  await page.route('**/api/alertas/leer-todas/', (route) => {
    read = true;
    return route.fulfill({ json: { marcadas: 1 } });
  });
  await page.goto('/alertas');
  await expect(page.getByRole('link', { name: 'Alertas, 1 sin leer' })).toBeVisible();
  await page.getByLabel('Severidad', { exact: true }).click();
  await page.getByRole('option', { name: 'Advertencia', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Cambio de riesgo de prueba' })).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await page.getByRole('button', { name: 'Marcar como leída: Cambio de riesgo de prueba' }).click();
  await expect(page.getByRole('link', { name: 'Alertas, 0 sin leer' })).toBeVisible();
  await page.getByRole('button', { name: 'Marcar todas como leídas' }).click();
});
test('registro, perfil y 404 son accesibles', async ({ page }) => {
  await page.goto('/registro');
  await expect(page.getByRole('heading', { name: 'Crea tu cuenta' })).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await session(page);
  await page.goto('/perfil');
  await expect(page.getByRole('heading', { name: 'Mi perfil', exact: true })).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await page.goto('/ruta-inexistente');
  await expect(page.getByRole('heading', { name: 'Esta página no está disponible' })).toBeVisible();
});

test('RGR sesión: cerrar sesión durante refresh no restaura credenciales', async ({ page }) => {
  await session(page);
  let releaseRefresh!: () => void;
  const released = new Promise<void>((resolve) => (releaseRefresh = resolve));
  let refreshStarted!: () => void;
  const started = new Promise<void>((resolve) => (refreshStarted = resolve));
  let refreshFinished!: () => void;
  const finished = new Promise<void>((resolve) => (refreshFinished = resolve));
  await page.route('**/api/paises/?*', (route) =>
    route.fulfill({ status: 401, json: { error: { mensaje: 'Access expirado' } } }),
  );
  await page.route('**/api/auth/refresh/', async (route) => {
    refreshStarted();
    await released;
    // The browser may have cancelled the HTTP request after logout.
    await route.fulfill({ json: { access: 'late-access' } }).catch(() => {});
    refreshFinished();
  });
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Panorama de Latinoamérica' })).toBeVisible();
  await started;
  await page.getByRole('button', { name: 'Abrir menú de usuario' }).click();
  await page.getByRole('menuitem', { name: 'Cerrar sesión' }).click();
  await expect(page).toHaveURL(/login$/);
  releaseRefresh();
  await finished;
  await page.waitForFunction(() =>
    performance.getEntriesByType('resource').some((entry) => entry.name.endsWith('/auth/refresh/')),
  );
  // Two animation frames let pending response microtasks update application state.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  expect(await page.evaluate(() => localStorage.getItem('datapulse.access'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('datapulse.refresh'))).toBeNull();
  await expect(page.getByRole('heading', { name: 'Inicia sesión', exact: true })).toBeVisible();
});
