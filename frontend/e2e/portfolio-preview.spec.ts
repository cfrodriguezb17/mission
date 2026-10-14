import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { session, envelope } from './support/session';
import { country, portfolio, position, risk } from '../src/app/testing/fixtures';

async function setup(page: Page, failFirst = false) {
  await session(page);
  const stored = portfolio({
    posiciones: [position()],
    resumen: {
      ...portfolio().resumen,
      total_invertido_usd: '1000.00',
      posiciones_activas: 1,
      riesgo_promedio_ponderado: '80.00',
    },
  });
  let riskRequests = 0;
  let writes = 0;
  await page.route('**/api/portafolios/7/resumen/', (route) =>
    route.fulfill({ json: stored.resumen }),
  );
  await page.route('**/api/portafolios/7/', (route) => route.fulfill({ json: stored }));
  await page.route('**/api/paises/?*', (route) =>
    route.fulfill({
      json: envelope([
        country(),
        country({ codigo_iso: 'BR', nombre: 'Brasil', moneda_codigo: 'BRL' }),
        country({ codigo_iso: 'EC', nombre: 'Ecuador', moneda_codigo: 'USD' }),
      ]),
    }),
  );
  await page.route('**/api/riesgo/?*', (route) => {
    riskRequests++;
    if (failFirst && riskRequests === 1) return route.fulfill({ status: 503, json: {} });
    return route.fulfill({
      json: envelope([
        risk(),
        risk({ id: 2, pais: 'BR', nombre_pais: 'Brasil', indice_compuesto: '20.00' }),
      ]),
    });
  });
  await page.route('**/api/portafolios/7/posiciones/**', (route) => {
    writes++;
    return route.fulfill({ status: 201, json: position() });
  });
  await page.goto('/portafolios/7');
  await expect(page.getByRole('heading', { name: stored.nombre, exact: true })).toBeVisible();
  return { riskRequests: () => riskRequests, writes: () => writes };
}
async function fillDraft(page: Page, name = 'Brasil') {
  await page.getByRole('combobox', { name: 'País', exact: true }).fill(name);
  await page.getByRole('option', { name: new RegExp(`^${name} ·`) }).click();
  await page.getByLabel('Monto en USD').fill('3,000.00');
}
const preview = (page: Page) =>
  page.getByRole('region', { name: 'Previsualización del portafolio' });

test('previsualiza montos y riesgo sin guardar ni consultar por cada cambio', async ({ page }) => {
  const state = await setup(page);
  await page.getByRole('button', { name: 'Agregar posición' }).click();
  await fillDraft(page);
  await expect(preview(page).getByTestId('preview-total')).toHaveText(/US\$\s*4\.000,00/);
  await expect(preview(page).getByTestId('preview-risk')).toHaveText('35 / 100');
  await page.getByLabel('Monto en USD').fill('1,000.00');
  await expect(preview(page).getByTestId('preview-total')).toHaveText(/US\$\s*2\.000,00/);
  await expect(preview(page).getByTestId('preview-risk')).toHaveText('50 / 100');
  expect(state.riskRequests()).toBe(1);
  expect(state.writes()).toBe(0);
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: 'test-results/portfolio-preview.png', animations: 'disabled' });
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 768);
  await page.screenshot({
    path: 'test-results/portfolio-preview-tablet.png',
    animations: 'disabled',
  });
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await page.getByRole('button', { name: 'Editar posición de Colombia' }).click();
  await page.getByLabel('Monto en USD').fill('3,000.00');
  await expect(preview(page).getByTestId('preview-total')).toHaveText(/US\$\s*3\.000,00/);
  await expect(preview(page).getByTestId('preview-risk')).toHaveText('80 / 100');
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await expect(page.getByRole('cell', { name: /US\$\s*1\.000,00/ })).toBeVisible();
  expect(state.writes()).toBe(0);
});

test('distingue riesgo faltante y borra la estimación para datos inválidos', async ({ page }) => {
  await setup(page);
  await page.getByRole('button', { name: 'Agregar posición' }).click();
  await fillDraft(page, 'Ecuador');
  await expect(preview(page).getByTestId('preview-risk')).toHaveText('80 / 100');
  await expect(preview(page)).toContainText('Riesgo incompleto');
  await expect(preview(page)).toContainText('Ecuador');
  await expect(preview(page)).toContainText(/3\.000,00/);
  await page.getByLabel('Monto en USD').fill('999.99');
  await expect(preview(page)).toContainText('Selecciona un país y un monto válido');
  await expect(preview(page).getByTestId('preview-total')).toHaveCount(0);
});

test('un fallo de índices conserva el total y permite reintentar sin perder el borrador', async ({
  page,
}) => {
  const state = await setup(page, true);
  await page.getByRole('button', { name: 'Agregar posición' }).click();
  await fillDraft(page);
  await expect(preview(page).getByTestId('preview-total')).toHaveText(/US\$\s*4\.000,00/);
  await expect(preview(page).getByTestId('preview-risk')).toHaveText('No disponible');
  await preview(page).getByRole('button', { name: 'Reintentar índices' }).click();
  await expect(preview(page).getByTestId('preview-risk')).toHaveText('35 / 100');
  await expect(page.getByLabel('Monto en USD')).toHaveValue('3,000.00');
  expect(state.riskRequests()).toBe(2);
  expect(state.writes()).toBe(0);
});
