import { position } from '../../../testing/fixtures';
import { previewPortfolio, PreviewRisk } from './previsualizacion';

const draft = { pais: 'BR', monto_inversion_usd: '3,000.00', fecha_salida: null };
const risks: PreviewRisk[] = [
  { pais: 'CO', indice_compuesto: '80.00', detalle_calculo: {} },
  { pais: 'BR', indice_compuesto: '20.00', detalle_calculo: {} },
];
describe('RGR previsualización exacta del portafolio', () => {
  it('incluye el borrador, ignora cerradas y pondera según capital activo', () => {
    const result = previewPortfolio(
      [
        position(),
        position({ id: 2, monto_inversion_usd: '10000000.00', fecha_salida: '2021-01-01' }),
      ],
      draft,
      risks,
    );
    expect(result).toMatchObject({
      total_invertido_usd: '4000.00',
      riesgo_promedio_ponderado: '35.00',
      posiciones_activas: 2,
      monto_sin_riesgo_usd: '0.00',
      riesgo_incompleto: false,
    });
  });
  it('sustituye la posición editada, incluyendo un cambio de país, sin duplicar capital', () => {
    const original = position();
    expect(previewPortfolio([original], draft, risks, original.id)).toMatchObject({
      total_invertido_usd: '3000.00',
      riesgo_promedio_ponderado: '20.00',
      posiciones_activas: 1,
    });
    expect(original.monto_inversion_usd).toBe('1000.00');
  });
  it('solo divide por capital con índice disponible y señala el faltante', () => {
    expect(previewPortfolio([position()], { ...draft, pais: 'EC' }, risks)).toMatchObject({
      total_invertido_usd: '4000.00',
      riesgo_promedio_ponderado: '80.00',
      monto_sin_riesgo_usd: '3000.00',
      paises_sin_riesgo: ['EC'],
      riesgo_incompleto: true,
    });
  });
  it('sin índices no presenta cero como riesgo conocido', () => {
    expect(previewPortfolio([], draft, [])).toMatchObject({
      riesgo_promedio_ponderado: null,
      monto_sin_riesgo_usd: '3000.00',
      riesgo_incompleto: true,
    });
  });
  it('un IRPC cero sí es conocido y participa en el denominador', () => {
    expect(
      previewPortfolio([position()], { ...draft, monto_inversion_usd: '1000.00' }, [
        risks[0],
        { ...risks[1], indice_compuesto: '0.00' },
      ]),
    ).toMatchObject({ riesgo_promedio_ponderado: '40.00', riesgo_incompleto: false });
  });
  it('redondea mitades hacia arriba, igual que Decimal ROUND_HALF_UP del backend', () => {
    expect(
      previewPortfolio([position()], { ...draft, monto_inversion_usd: '1000.00' }, [
        { ...risks[0], indice_compuesto: '80.00' },
        { ...risks[1], indice_compuesto: '80.01' },
      ])?.riesgo_promedio_ponderado,
    ).toBe('80.01');
  });
  it('conserva un centavo al sumar montos grandes', () => {
    const positions = Array.from({ length: 4 }, (_, id) =>
      position({ id, monto_inversion_usd: '10000000.00' }),
    );
    expect(
      previewPortfolio(positions, { ...draft, monto_inversion_usd: '9,999,999.99' }, risks)
        ?.total_invertido_usd,
    ).toBe('49999999.99');
  });
  it('editar una posición cerrada no agrega capital ni riesgo activo', () => {
    const closed = position({ fecha_salida: '2021-01-01' });
    expect(
      previewPortfolio([closed], { ...draft, fecha_salida: '2021-01-01' }, risks, closed.id),
    ).toMatchObject({
      total_invertido_usd: '0.00',
      posiciones_activas: 0,
      riesgo_promedio_ponderado: null,
      riesgo_incompleto: false,
    });
  });
  it('propaga la evidencia parcial y simulada de los índices usados', () => {
    expect(
      previewPortfolio([], draft, [
        { ...risks[1], detalle_calculo: { datos_parciales: true, contiene_simulaciones: true } },
      ]),
    ).toMatchObject({ datos_parciales: true, contiene_simulaciones: true });
  });
  it.each(['', '999.99', '10000000.01', '1e6', '1000.001'])(
    'no inventa una estimación para el monto inválido %s',
    (amount) => {
      expect(previewPortfolio([], { ...draft, monto_inversion_usd: amount }, risks)).toBeNull();
    },
  );
  it('un índice malformado se trata como ausente', () => {
    expect(previewPortfolio([], draft, [{ ...risks[1], indice_compuesto: 'NaN' }])).toMatchObject({
      riesgo_promedio_ponderado: null,
      riesgo_incompleto: true,
    });
  });
});
