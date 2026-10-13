import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
const password = process.env['E2E_PASSWORD'] ?? 'DataPulse2026!';
async function login(page: import('@playwright/test').Page, role = 'analista') {
  await page.goto('/login');
  await page.getByLabel('Correo electrónico').fill(`${role}@datapulse.com`);
  await page.getByLabel('Contraseña', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Panorama de Latinoamérica' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ranking regional' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sincronizar indicadores' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Recalcular riesgos' })).toHaveCount(0);
}
test('login, gráficos, detalle de país, accesibilidad y tablet', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Inicia sesión', exact: true })).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await login(page);
  await expect(page.locator('canvas')).toHaveCount(1);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 1920);
  await page.screenshot({
    path: 'test-results/dashboard-desktop.png',
    fullPage: true,
    animations: 'disabled',
  });
  const accessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    accessibility.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => ({ target: n.target, reason: n.failureSummary })),
    })),
  ).toEqual([]);
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 768);
  await page.screenshot({
    path: 'test-results/dashboard-tablet.png',
    fullPage: true,
    animations: 'disabled',
  });
  await page.getByRole('button', { name: 'Abrir navegación' }).click();
  await page.getByRole('link', { name: 'Países y mercados' }).click();
  await page.getByLabel('Buscar país').fill('Colombia');
  await expect(page.getByRole('heading', { name: 'Colombia', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Explorar', exact: true })).toHaveCount(1);
  await page.getByRole('link', { name: 'Explorar', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Índice de riesgo país', exact: true }),
  ).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(2);
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  expect(errors).toEqual([]);
});
test('VIEWER no puede abrir creación ni editar portafolios', async ({ page }) => {
  await login(page, 'viewer');
  await page.goto('/portafolios');
  await expect(page.getByRole('heading', { name: 'Portafolios', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Nuevo portafolio' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Ver portafolio' }).first().click();
  await expect(page.getByRole('button', { name: 'Agregar posición' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Editar', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Exportar PDF' })).toBeVisible();
  await page.goto('/portafolios/nuevo');
  await expect(page).toHaveURL(/dashboard$/);
});
test('crear, editar, posición, conflicto conservando borrador, PDF y eliminación', async ({
  page,
}) => {
  await login(page);
  await page.goto('/portafolios/nuevo');
  const name = `Prueba frontend ${Date.now()}`;
  await page.getByLabel('Nombre', { exact: true }).fill(name);
  await page
    .getByLabel('Descripción', { exact: true })
    .fill('Portafolio temporal de verificación automática.');
  await expect(page.getByRole('button', { name: 'Crear portafolio' })).toBeEnabled();
  await page.getByRole('button', { name: 'Crear portafolio' }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  const id = page.url().split('/').pop()!;
  try {
    await page.getByRole('button', { name: 'Agregar posición' }).click();
    await page.getByLabel('País', { exact: true }).fill('Col');
    await page.getByRole('option', { name: 'Colombia · COP' }).click();
    await page.getByLabel('Tipo de activo').click();
    await page.getByRole('option', { name: 'Renta fija', exact: true }).click();
    await page.getByLabel('Monto en USD').fill('1,234.56');
    await page.getByLabel('Fecha de entrada').fill('2020-01-01');
    await page.getByLabel('Notas (opcional)').fill('Borrador conservado');
    const preview = page.getByRole('region', { name: 'Previsualización del portafolio' });
    await expect(preview.getByTestId('preview-risk')).toHaveText(/\d.*\/ 100/);
    const projectedTotal = (await preview.getByTestId('preview-total').innerText())
      .replace(/\s+/g, ' ')
      .trim();
    const projectedRisk = (await preview.getByTestId('preview-risk').innerText())
      .replace(/\s+/g, ' ')
      .trim();

    // Real concurrency: another request updates the portfolio after this form loaded.
    await page.evaluate(async (id) => {
      const token = localStorage.getItem('datapulse.access');
      const url = `http://127.0.0.1:8000/api/portafolios/${id}/`;
      const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
      const p = await (await fetch(url, { headers })).json();
      await fetch(url, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ version: p.version, descripcion: 'Modificado en otra sesión' }),
      });
    }, id);
    await page.getByRole('button', { name: 'Guardar posición' }).click();
    await expect(page.getByText('El portafolio cambió.', { exact: false })).toBeVisible();
    await expect(page.getByLabel('Notas (opcional)')).toHaveValue('Borrador conservado');
    await page.getByRole('button', { name: 'Revisé los cambios' }).click();
    await page.getByRole('button', { name: 'Guardar posición' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('cell', { name: /US\$\s*1\.234,56/ })).toBeVisible();
    await expect(
      page
        .locator('section.panel')
        .filter({ has: page.locator('.metric-label', { hasText: 'Capital activo invertido' }) })
        .locator('.metric-value'),
    ).toHaveText(projectedTotal);
    await expect(
      page
        .locator('section.panel')
        .filter({ has: page.locator('.metric-label', { hasText: 'IRPC promedio ponderado' }) })
        .locator('.metric-value'),
    ).toHaveText(projectedRisk);

    await page.getByRole('button', { name: 'Editar posición de Colombia' }).click();
    await page.getByLabel('Monto en USD').fill('2,000.00');
    await page.getByRole('button', { name: 'Guardar posición' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('cell', { name: /US\$\s*2\.000,00/ })).toBeVisible();
    await page.getByRole('button', { name: 'Editar', exact: true }).click();
    await page.getByLabel('Descripción', { exact: true }).fill('Descripción revisada');
    await page.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Exportar PDF' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`portafolio-${id}.pdf`);
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([]);
    await page.getByRole('button', { name: 'Cerrar posición de Colombia' }).click();
    await page.getByRole('button', { name: 'Confirmar cierre' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText('Cerrada ·', { exact: false })).toBeVisible();
    await page.getByRole('button', { name: 'Eliminar portafolio' }).click();
    await page.getByRole('button', { name: 'Eliminar', exact: true }).click();
    await expect(page).toHaveURL(/portafolios$/);
  } finally {
    // Remove only the portfolio created by this test if an assertion interrupts the flow.
    await page.evaluate(async (id) => {
      const headers = {
        Authorization: `Bearer ${localStorage.getItem('datapulse.access')}`,
        'Content-Type': 'application/json',
      };
      const url = `http://127.0.0.1:8000/api/portafolios/${id}/`;
      const response = await fetch(url, { headers });
      if (response.ok) {
        const p = await response.json();
        await fetch(url, {
          method: 'DELETE',
          headers,
          body: JSON.stringify({ version: p.version }),
        });
      }
    }, id);
  }
});
