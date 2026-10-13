import { hasOperationIssues } from './operation-result';
describe('Resultados parciales de administración', () => {
  it('no confunde países procesados con errores', () =>
    expect(
      hasOperationIssues({
        paises_procesados: ['CO'],
        riesgos: { calculados: [1], errores: [] },
        alertas: { creadas: 2, pendientes: 0, errores: [] },
      }),
    ).toBe(false));
  it('detecta errores de etapas anidadas', () =>
    expect(hasOperationIssues({ riesgos: { errores: [{ pais: 'CO' }] } })).toBe(true));
  it('detecta faltantes aunque HTTP sea 200', () =>
    expect(hasOperationIssues({ faltantes: [{ pais: 'CO', anio: 2020 }] })).toBe(true));
  it('detecta entregas pendientes', () =>
    expect(hasOperationIssues({ alertas: { pendientes: 1 } })).toBe(true));
});
