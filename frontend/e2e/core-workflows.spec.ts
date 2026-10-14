import { test, expect } from '@playwright/test';
import { country, envelope, session } from './support/session';

test('login bloquea datos inválidos y presenta credenciales rechazadas', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/auth/login/', (route) => {
    attempts++;
    expect(route.request().postDataJSON()).toEqual({
      email: 'test@example.com',
      password: 'incorrecta',
    });
    return route.fulfill({
      status: 401,
      json: { error: { mensaje: 'Credenciales incorrectas.' } },
    });
  });
  await page.goto('/login');
  const submit = page.getByRole('button', { name: 'Iniciar sesión', exact: true });
  await expect(submit).toBeDisabled();
  await page.getByLabel('Correo electrónico').fill('correo-invalido');
  await page.getByLabel('Contraseña', { exact: true }).fill('incorrecta');
  await expect(submit).toBeDisabled();
  expect(attempts).toBe(0);
  await page.getByLabel('Correo electrónico').fill('test@example.com');
  await submit.click();
  await expect(page.getByRole('alert')).toHaveText('Credenciales incorrectas.');
  expect(attempts).toBe(1);
  expect(await page.evaluate(() => localStorage.getItem('datapulse.access'))).toBeNull();
  await expect(submit).toBeEnabled();
});

test('registro válido realiza login, consulta el perfil VIEWER y abre dashboard', async ({
  page,
}) => {
  await session(page, 'VIEWER', false);
  const operations: string[] = [];
  await page.route('**/api/auth/register/', (route) => {
    operations.push('register');
    expect(route.request().postDataJSON()).toEqual({
      email: 'nuevo@example.com',
      nombre_completo: 'Nueva Persona',
      password: 'DemoSegura2026!',
    });
    return route.fulfill({ status: 201, json: { id: 2, rol: 'VIEWER' } });
  });
  await page.route('**/api/auth/login/', (route) => {
    operations.push('login');
    expect(route.request().postDataJSON()).toEqual({
      email: 'nuevo@example.com',
      password: 'DemoSegura2026!',
    });
    return route.fulfill({ json: { access: 'registered-access', refresh: 'registered-refresh' } });
  });
  await page.goto('/registro');
  await page.getByLabel('Nombre completo').fill('Nueva Persona');
  await page.getByLabel('Correo electrónico').fill('nuevo@example.com');
  await page.getByLabel('Contraseña', { exact: true }).fill('12345');
  await expect(page.getByRole('button', { name: 'Crear cuenta' })).toBeDisabled();
  await page.getByLabel('Contraseña', { exact: true }).fill('DemoSegura2026!');
  const profile = page.waitForRequest('**/api/auth/me/');
  await page.getByRole('button', { name: 'Crear cuenta' }).click();
  expect((await profile).headers()['authorization']).toBe('Bearer registered-access');
  await expect(page).toHaveURL(/dashboard$/);
  await expect(page.getByRole('button', { name: 'Abrir menú de usuario' })).toContainText('VIEWER');
  expect(operations).toEqual(['register', 'login']);
  expect(await page.evaluate(() => localStorage.getItem('datapulse.refresh'))).toBe(
    'registered-refresh',
  );
});

test('perfil omite contraseña vacía, actualiza usuario y cierra sesión al cambiar contraseña', async ({
  page,
}) => {
  await session(page);
  const writes: Record<string, string>[] = [];
  await page.route('**/api/auth/me/', (route) => {
    const profile = {
      id: 1,
      email: 'test@datapulse.com',
      nombre_completo: 'Usuario de prueba',
      rol: 'ANALISTA',
      activo: true,
    };
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON();
      writes.push(body);
      return route.fulfill({ json: { ...profile, ...body } });
    }
    return route.fulfill({ json: profile });
  });
  await page.goto('/perfil');
  await page.getByLabel('Nombre completo').fill('Nombre actualizado');
  await page.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(page.getByRole('button', { name: 'Abrir menú de usuario' })).toContainText(
    'Nombre actualizado',
  );
  expect(writes).toEqual([{ email: 'test@datapulse.com', nombre_completo: 'Nombre actualizado' }]);
  await page.getByLabel('Nueva contraseña (opcional)').fill('NuevaClave2026!');
  await page.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(page).toHaveURL(/login$/);
  expect(writes[1]['password']).toBe('NuevaClave2026!');
  expect(await page.evaluate(() => localStorage.getItem('datapulse.access'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('datapulse.refresh'))).toBeNull();
});

test('búsqueda y región consultan la API y muestran el estado vacío recuperable', async ({
  page,
}) => {
  await session(page);
  await page.route('**/api/paises/?*', (route) => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: envelope(query.get('search') === 'inexistente' ? [] : [country]),
    });
  });
  await page.goto('/paises');
  await expect(page.getByRole('heading', { name: 'Colombia', exact: true })).toBeVisible();
  await page.getByLabel('Región', { exact: true }).click();
  const regionRequest = page.waitForRequest(
    (r) => new URL(r.url()).searchParams.get('region') === 'ANDINA',
  );
  await page.getByRole('option', { name: 'Andina', exact: true }).click();
  await regionRequest;
  const searchRequest = page.waitForRequest(
    (r) => new URL(r.url()).searchParams.get('search') === 'inexistente',
  );
  await page.getByLabel('Buscar país').fill('inexistente');
  expect(new URL((await searchRequest).url()).searchParams.get('region')).toBe('ANDINA');
  await expect(page.getByRole('heading', { name: 'No encontramos países' })).toBeVisible();
  await page.getByLabel('Buscar país').fill('Colombia');
  await expect(page.getByRole('heading', { name: 'Colombia', exact: true })).toBeVisible();
});

test('dashboard cambia indicador, distingue nulos y cero y limita la selección a tres países', async ({
  page,
}) => {
  await session(page);
  await page.route('**/api/paises/?*', (route) =>
    route.fulfill({
      json: envelope([
        country,
        { ...country, codigo_iso: 'BR', nombre: 'Brasil' },
        { ...country, codigo_iso: 'MX', nombre: 'México' },
        { ...country, codigo_iso: 'EC', nombre: 'Ecuador' },
      ]),
    }),
  );
  await page.route('**/api/dashboard/tendencias/?*', (route) =>
    route.fulfill({
      json: {
        ...envelope([
          {
            pais: 'CO',
            nombre_pais: 'Colombia',
            datos_parciales: true,
            valores: [
              { anio: 2024, valor: null, fuente: null, es_simulado: null },
              { anio: 2025, valor: '0.00', fuente: 'Prueba', es_simulado: true },
            ],
          },
        ]),
        tipo: new URL(route.request().url()).searchParams.get('tipo'),
        unidad: 'PORCENTAJE',
        anio_inicio: 2021,
        anio_fin: 2025,
      },
    }),
  );
  await page.goto('/dashboard');
  await page.getByLabel('Indicador', { exact: true }).click();
  const request = page.waitForRequest(
    (r) => new URL(r.url()).searchParams.get('tipo') === 'INFLACION',
  );
  await page.getByRole('option', { name: 'Inflación', exact: true }).click();
  expect(new URL((await request).url()).searchParams.get('paises')).toBe('CO,BR,MX');
  await page.locator('summary').filter({ hasText: 'Ver datos de tendencias económicas' }).click();
  const table = page.locator('app-chart table');
  await expect(table.getByRole('row').filter({ hasText: '2024' })).toContainText('Sin datos');
  await expect(table.getByRole('row').filter({ hasText: '2025' }).getByRole('cell')).toHaveText(
    '0',
  );
  await page.getByLabel('Países (máximo 3)', { exact: true }).click();
  await expect(page.getByRole('option', { name: 'Ecuador', exact: true })).toBeDisabled();
  await page.getByRole('option', { name: 'Brasil', exact: true }).click();
  await expect(page.getByRole('option', { name: 'Ecuador', exact: true })).toBeEnabled();
  await page.keyboard.press('Escape');
});
