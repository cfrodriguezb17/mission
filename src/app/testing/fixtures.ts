import { Country, PortfolioDetail, Position, Risk } from '../core/models/api.models';

export function country(overrides: Partial<Country> = {}): Country {
  return {
    codigo_iso: 'CO',
    nombre: 'Colombia',
    moneda_codigo: 'COP',
    moneda_nombre: 'Peso colombiano',
    region: 'ANDINA',
    latitud: '4.57',
    longitud: '-74.29',
    poblacion: 52000000,
    bandera_url: '',
    ...overrides,
  };
}
export function position(overrides: Partial<Position> = {}): Position {
  return {
    id: 1,
    pais: 'CO',
    nombre_pais: 'Colombia',
    tipo_activo: 'RENTA_FIJA',
    monto_inversion_usd: '1000.00',
    fecha_entrada: '2020-01-01',
    fecha_salida: null,
    notas: '',
    ...overrides,
  };
}
export function portfolio(overrides: Partial<PortfolioDetail> = {}): PortfolioDetail {
  return {
    id: 7,
    nombre: 'Estrategia Latam',
    descripcion: 'Diversificación regional',
    usuario: 1,
    es_publico: false,
    es_propio: true,
    version: 3,
    puede_editar: true,
    puede_eliminar: true,
    puede_cambiar_visibilidad: true,
    fecha_modificacion: '2026-10-13T10:00:00Z',
    posiciones: [],
    resumen: {
      total_invertido_usd: '0.00',
      posiciones_activas: 0,
      riesgo_promedio_ponderado: null,
      riesgo_incompleto: false,
      monto_sin_riesgo_usd: '0.00',
      distribucion_por_pais: [],
      distribucion_por_tipo_activo: [],
      distribucion_por_riesgo: [],
    },
    ...overrides,
  };
}

export function risk(overrides: Partial<Risk> = {}): Risk {
  return {
    id: 1,
    pais: 'CO',
    nombre_pais: 'Colombia',
    fecha_calculo: '2026-10-13T10:00:00Z',
    score_economico: '80.00',
    score_cambiario: '80.00',
    score_estabilidad: '80.00',
    indice_compuesto: '80.00',
    nivel_riesgo: 'BAJO',
    color: '#22c55e',
    detalle_calculo: {},
    ...overrides,
  };
}
