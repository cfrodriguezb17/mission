import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

test('Django real: IRPC 30 → 24, lectura y alerta perdida durante reinicio', async ({ page }) => {
  test.skip(!process.env['REALTIME_LIVE_DIR'], 'Ejecutar con tools/verify-realtime.py');
  test.setTimeout(120000);
  const folder = process.env['REALTIME_LIVE_DIR']!;
  const errors: string[] = [];
  let ready = 0;
  let closed = 0;
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('websocket', (socket) => {
    expect(socket.url()).not.toContain('bearer');
    socket.on('framereceived', ({ payload }) => {
      if (typeof payload === 'string' && JSON.parse(payload).event === 'conexion.lista') ready++;
    });
    socket.on('close', () => closed++);
  });
  await page.goto('/login');
  await page.getByLabel('Correo electrónico').fill(process.env['REALTIME_LIVE_EMAIL']!);
  await page.getByLabel('Contraseña', { exact: true }).fill(process.env['REALTIME_LIVE_PASSWORD']!);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await expect(page).toHaveURL(/dashboard$/);
  await expect.poll(() => ready).toBe(1);
  const metric = page
    .locator('.kpi-card')
    .filter({ hasText: 'IRPC promedio regional' })
    .locator('.kpi-value');
  await expect(metric).toContainText('30');
  await expect(page.getByRole('link', { name: 'Alertas, 0 sin leer' })).toBeVisible();
  const start = Date.now();
  writeFileSync(join(folder, 'critical'), '24');
  await expect(metric).toContainText('24', { timeout: 15000 });
  await expect(page.getByRole('link', { name: 'Alertas, 1 sin leer' })).toBeVisible();
  const latency = Date.now() - start;
  await expect(
    page.locator('mat-snack-bar-container').filter({ hasText: 'Hay nuevas alertas' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Alertas, 1 sin leer' }).click();
  await expect(page.getByRole('heading', { name: /^Riesgo crítico/ })).toBeVisible();
  await expect(page.getByText('IRPC de Colombia: 24.00 (<25).', { exact: true })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'se actualizan en vivo' })).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole('button', { name: 'Marcar como leída: Riesgo crítico' }).click();
  await expect(page.getByRole('link', { name: 'Alertas, 0 sin leer' })).toBeVisible();
  writeFileSync(join(folder, 'restart'), '23');
  await expect.poll(() => ready, { timeout: 30000 }).toBeGreaterThan(1);
  await expect(page.getByRole('heading', { name: /^Riesgo crítico/ })).toHaveCount(2, {
    timeout: 15000,
  });
  await expect(page.getByRole('link', { name: 'Alertas, 1 sin leer' })).toBeVisible();
  const beforeLogout = closed;
  await page.getByRole('button', { name: 'Abrir menú de usuario' }).click();
  await page.getByRole('menuitem', { name: 'Cerrar sesión' }).click();
  await expect(page).toHaveURL(/login$/);
  await expect.poll(() => closed).toBeGreaterThan(beforeLogout);
  expect(errors).toEqual([]);
  writeFileSync(
    join(folder, 'browser-result.json'),
    JSON.stringify(
      {
        passed: true,
        initial_irpc: 30,
        critical_irpc: 24,
        latency_ms: latency,
        ready_connections: ready,
        recovered_missed_alert: true,
        read_updates_badge: true,
        axe_violations: accessibility.violations.length,
        page_errors: errors,
        logout_closes_socket: true,
      },
      null,
      2,
    ),
  );
});
