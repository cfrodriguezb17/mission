import { test, expect, Page, WebSocketRoute } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { session, envelope } from './support/session';

async function setup(page: Page) {
  await session(page);
  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket('**/ws/notificaciones/', (socket) => {
    sockets.push(socket);
    socket.send(JSON.stringify({ event: 'conexion.lista' }));
  });
  let count = 0;
  let summaryRequests = 0;
  const queries: string[] = [];
  await page.route('**/api/alertas/resumen/', (route) => {
    summaryRequests++;
    return route.fulfill({ json: { total: count, no_leidas: count } });
  });
  await page.route('**/api/dashboard/resumen/', (route) =>
    route.fulfill({
      json: {
        total_paises: 1,
        alertas_activas: count,
        portafolios_usuario: 0,
        promedio_irpc: count ? '24.00' : '30.00',
        paises_con_datos_parciales: 0,
      },
    }),
  );
  await page.route('**/api/alertas/?*', (route) => {
    queries.push(new URL(route.request().url()).search);
    return route.fulfill({
      json: envelope(
        count
          ? [
              {
                id: 7,
                pais: 'CO',
                tipo_alerta: 'RIESGO',
                severidad: 'CRITICAL',
                titulo: 'Riesgo crítico',
                mensaje: 'IRPC de Colombia: 24 (<25).',
                fecha_creacion: '2026-10-13T10:00:00Z',
                leida: false,
              },
            ]
          : [],
      ),
    });
  });
  return {
    summaryRequests: () => summaryRequests,
    sockets,
    queries,
    addAlert: () => {
      count = 1;
    },
  };
}

test('WebSocket actualiza campanita y dashboard sin recargar la página', async ({ page }) => {
  const fixture = await setup(page);
  await page.goto('/dashboard');
  const metric = page
    .locator('.kpi-card')
    .filter({ hasText: 'IRPC promedio regional' })
    .locator('.kpi-value');
  await expect(metric).toContainText('30');
  await expect.poll(() => fixture.sockets.length).toBe(1);
  await expect.poll(fixture.summaryRequests).toBeGreaterThan(1);
  fixture.addAlert();
  fixture.sockets[0].send(JSON.stringify({ event: 'alerta.creada', id: 7 }));
  fixture.sockets[0].send(JSON.stringify({ event: 'dashboard.actualizado' }));
  await expect(page.getByRole('link', { name: 'Alertas, 1 sin leer' })).toBeVisible({
    timeout: 10000,
  });
  await expect(metric).toContainText('24', { timeout: 10000 });
  await expect(
    page.locator('mat-snack-bar-container').filter({ hasText: 'Hay nuevas alertas' }),
  ).toBeVisible();
  expect(fixture.sockets).toHaveLength(1);
});

test('WebSocket refresca el listado conservando filtros y accesibilidad', async ({ page }) => {
  const fixture = await setup(page);
  await page.goto('/alertas');
  await expect(page.getByRole('status').filter({ hasText: 'se actualizan en vivo' })).toBeVisible();
  await page.getByLabel('Severidad', { exact: true }).click();
  await page.getByRole('option', { name: 'Crítica', exact: true }).click();
  fixture.addAlert();
  fixture.sockets[0].send(JSON.stringify({ event: 'alerta.creada', id: 7 }));
  await expect(page.getByRole('heading', { name: 'Riesgo crítico' })).toBeVisible({
    timeout: 10000,
  });
  expect(new URLSearchParams(fixture.queries.at(-1)).get('severidad')).toBe('CRITICAL');
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
});

test('reconexión recupera una alerta perdida y logout cierra el socket', async ({ page }) => {
  const fixture = await setup(page);
  let closed = false;
  await page.goto('/alertas');
  await expect(page.getByRole('status').filter({ hasText: 'se actualizan en vivo' })).toBeVisible();
  fixture.sockets[0].close({ code: 1011, reason: 'Interrupción de prueba' });
  fixture.addAlert();
  await expect.poll(() => fixture.sockets.length, { timeout: 10000 }).toBe(2);
  await expect(page.getByRole('heading', { name: 'Riesgo crítico' })).toBeVisible({
    timeout: 10000,
  });
  await expect(
    page.locator('mat-snack-bar-container').filter({ hasText: 'Hay nuevas alertas' }),
  ).toHaveCount(0);
  fixture.sockets[1].onClose(() => {
    closed = true;
  });
  await page.getByRole('button', { name: 'Abrir menú de usuario' }).click();
  await page.getByRole('menuitem', { name: 'Cerrar sesión' }).click();
  await expect(page).toHaveURL(/login$/);
  await expect.poll(() => closed).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem('datapulse.access'))).toBeNull();
});

test('sin WebSocket conserva sesión y recupera el contador por consulta periódica', async ({
  page,
}) => {
  await page.clock.install();
  const fixture = await setup(page);
  await page.routeWebSocket('**/ws/notificaciones/', (socket) => socket.close({ code: 1011 }));
  await page.goto('/alertas');
  await expect(page.getByRole('link', { name: 'Alertas, 0 sin leer' })).toBeVisible();
  fixture.addAlert();
  await page.clock.runFor(31000);
  await expect(page.getByRole('link', { name: 'Alertas, 1 sin leer' })).toBeVisible();
  await expect(
    page.getByRole('status').filter({ hasText: 'se consultan periódicamente' }),
  ).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('datapulse.access'))).toBe('test-access');
});
