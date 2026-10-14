export type Decimal = string;
export type Role = 'ADMIN' | 'ANALISTA' | 'VIEWER';
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
export interface User {
  id: number;
  email: string;
  nombre_completo: string;
  rol: Role;
  activo: boolean;
}
export interface Tokens {
  access: string;
  refresh: string;
}
export type Params = Record<string, string | number | boolean | undefined>;
export interface Indicator {
  id: number;
  pais: string;
  tipo: string;
  valor: Decimal;
  unidad: string;
  anio: number;
  fuente: string;
  es_simulado: boolean;
}
export interface Country {
  codigo_iso: string;
  nombre: string;
  moneda_codigo: string;
  moneda_nombre: string;
  region: string;
  latitud: Decimal;
  longitud: Decimal;
  poblacion: number | null;
  bandera_url: string;
  indicadores?: Indicator[];
}
export interface Risk {
  id: number;
  pais: string;
  nombre_pais: string;
  fecha_calculo: string;
  score_economico: Decimal;
  score_cambiario: Decimal;
  score_estabilidad: Decimal;
  indice_compuesto: Decimal;
  nivel_riesgo: string;
  color: string;
  variacion?: Decimal | null;
  tendencia?: string;
  detalle_calculo: {
    datos_parciales?: boolean;
    contiene_simulaciones?: boolean;
    [key: string]: unknown;
  };
}
export interface MapCountry {
  codigo_iso: string;
  nombre: string;
  latitud: Decimal;
  longitud: Decimal;
  indice_compuesto: Decimal | null;
  nivel_riesgo: string;
  color: string;
  datos_parciales: boolean;
  contiene_simulaciones: boolean;
}
export interface Exchange {
  fecha: string;
  tasa: Decimal;
  moneda_origen: string;
  moneda_destino: string;
  variacion_porcentual: Decimal | null;
  es_simulado: boolean;
}
export interface TrendCountry {
  pais: string;
  nombre_pais: string;
  datos_parciales: boolean;
  valores: {
    anio: number;
    valor: Decimal | null;
    fuente: string | null;
    es_simulado: boolean | null;
  }[];
}
export interface Trends extends Page<TrendCountry> {
  tipo: string;
  unidad: string;
  anio_inicio: number;
  anio_fin: number;
}
export interface DashboardSummary {
  total_paises: number;
  alertas_activas: number;
  portafolios_usuario: number;
  promedio_irpc: Decimal | null;
  paises_con_datos_parciales: number;
}
export interface Distribution {
  codigo: string;
  monto_usd: Decimal;
  porcentaje: Decimal;
}
export interface PortfolioSummary {
  total_invertido_usd: Decimal;
  posiciones_activas: number;
  riesgo_promedio_ponderado: Decimal | null;
  riesgo_incompleto: boolean;
  monto_sin_riesgo_usd: Decimal;
  distribucion_por_pais: Distribution[];
  distribucion_por_tipo_activo: Distribution[];
  distribucion_por_riesgo: Distribution[];
}
export interface Position {
  id: number;
  pais: string;
  nombre_pais: string;
  tipo_activo: string;
  monto_inversion_usd: Decimal;
  fecha_entrada: string;
  fecha_salida: string | null;
  notas: string;
  version_portafolio?: number;
}
export interface Portfolio {
  id: number;
  nombre: string;
  descripcion: string;
  usuario: number;
  es_publico: boolean;
  es_propio: boolean;
  version: number;
  puede_editar: boolean;
  puede_eliminar: boolean;
  puede_cambiar_visibilidad: boolean;
  fecha_modificacion: string;
}
export interface PortfolioDetail extends Portfolio {
  posiciones: Position[];
  resumen: PortfolioSummary;
}
export interface Alert {
  id: number;
  pais: string;
  tipo_alerta: string;
  severidad: string;
  titulo: string;
  mensaje: string;
  fecha_creacion: string;
  leida: boolean;
}
export interface AlertSummary {
  total: number;
  no_leidas: number;
  por_tipo: Record<string, number>;
  por_severidad: Record<string, number>;
}
export const INDICATORS = [
  { code: 'PIB', label: 'PIB' },
  { code: 'INFLACION', label: 'Inflación' },
  { code: 'DESEMPLEO', label: 'Desempleo' },
  { code: 'BALANZA_COMERCIAL', label: 'Balanza comercial' },
  { code: 'DEUDA_PIB', label: 'Deuda / PIB' },
  { code: 'PIB_PERCAPITA', label: 'PIB per cápita' },
];
export const ASSETS = [
  { code: 'RENTA_FIJA', label: 'Renta fija' },
  { code: 'RENTA_VARIABLE', label: 'Renta variable' },
  { code: 'COMMODITIES', label: 'Commodities' },
  { code: 'MONEDA', label: 'Moneda' },
];
export const REGIONS = [
  { code: 'ANDINA', label: 'Andina' },
  { code: 'CONO_SUR', label: 'Cono Sur' },
  { code: 'CENTROAMERICA', label: 'Centroamérica' },
  { code: 'CARIBE', label: 'Caribe' },
];
export function label(value: string): string {
  return (
    [...INDICATORS, ...ASSETS, ...REGIONS].find((x) => x.code === value)?.label ??
    (
      {
        BAJO: 'Bajo',
        MODERADO: 'Moderado',
        ALTO: 'Alto',
        CRITICO: 'Crítico',
        SIN_DATOS: 'Sin datos',
        MEJORA: 'Mejora',
        EMPEORA: 'Empeora',
        ESTABLE: 'Estable',
        SIN_HISTORICO: 'Sin histórico',
        RIESGO: 'Riesgo',
        TIPO_CAMBIO: 'Tipo de cambio',
        INDICADOR: 'Indicador',
        INFO: 'Información',
        WARNING: 'Advertencia',
        CRITICAL: 'Crítica',
      } as Record<string, string>
    )[value] ??
    value
  );
}
