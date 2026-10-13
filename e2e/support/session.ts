import { Page } from '@playwright/test';
export const envelope = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});
export const country = {
  codigo_iso: 'CO',
  nombre: 'Colombia',
  moneda_codigo: 'COP',
  moneda_nombre: 'Peso colombiano',
  region: 'ANDINA',
  poblacion: 52000000,
  latitud: '4.57',
  longitud: '-74.29',
  bandera_url: '',
};
export async function session(page: Page, role = 'ANALISTA', authenticated = true) {
  if (authenticated)
    await page.addInitScript(() => {
      localStorage.setItem('datapulse.access', 'test-access');
      localStorage.setItem('datapulse.refresh', 'test-refresh');
    });
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body =
      path === '/api/auth/me/'
        ? {
            id: 1,
            email: 'test@datapulse.com',
            nombre_completo: 'Usuario de prueba',
            rol: role,
            activo: true,
          }
        : path === '/api/alertas/resumen/'
          ? { total: 0, no_leidas: 0 }
          : path === '/api/dashboard/resumen/'
            ? {
                total_paises: 1,
                alertas_activas: 0,
                portafolios_usuario: 0,
                promedio_irpc: null,
                paises_con_datos_parciales: 0,
              }
            : path === '/api/dashboard/tendencias/'
              ? { ...envelope([]), tipo: 'PIB', unidad: 'USD', anio_inicio: 2021, anio_fin: 2025 }
              : path === '/api/paises/'
                ? envelope([country])
                : envelope([]);
    await route.fulfill({ json: body });
  });
}
