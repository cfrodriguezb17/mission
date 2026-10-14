import { Position, Risk } from '../../../core/models/api.models';
import { cents } from '../../../shared/utils/form-utils';

export type PreviewPosition = Pick<Position, 'pais' | 'monto_inversion_usd' | 'fecha_salida'>;
export type PreviewRisk = Pick<Risk, 'pais' | 'indice_compuesto' | 'detalle_calculo'>;
export interface PortfolioPreview {
  total_invertido_usd: string;
  riesgo_promedio_ponderado: string | null;
  posiciones_activas: number;
  monto_sin_riesgo_usd: string;
  paises_sin_riesgo: string[];
  riesgo_incompleto: boolean;
  contiene_simulaciones: boolean;
  datos_parciales: boolean;
}

export function previewPortfolio(
  positions: readonly Position[],
  draft: PreviewPosition,
  risks: readonly PreviewRisk[],
  editingId?: number,
): PortfolioPreview | null {
  const draftAmount = cents(draft.monto_inversion_usd);
  if (!draft.pais || draftAmount === null || draftAmount < 100000n || draftAmount > 1000000000n)
    return null;
  const projected: readonly PreviewPosition[] = [
    ...positions.filter((position) => position.id !== editingId),
    draft,
  ];
  const active = projected.filter((position) => position.fecha_salida === null);
  const indices = new Map(risks.map((risk) => [risk.pais, risk]));
  const missing = new Set<string>();
  let total = 0n,
    known = 0n,
    weighted = 0n;
  let simulated = false,
    partial = false;
  for (const position of active) {
    const amount = cents(position.monto_inversion_usd);
    if (amount === null) return null;
    total += amount;
    const index = indices.get(position.pais);
    const score = index ? cents(index.indice_compuesto) : null;
    if (score === null || score > 10000n) {
      missing.add(position.pais);
      continue;
    }
    known += amount;
    weighted += amount * score;
    simulated ||= !!index?.detalle_calculo.contiene_simulaciones;
    partial ||= !!index?.detalle_calculo.datos_parciales;
  }
  return {
    total_invertido_usd: decimal(total),
    // Scores have two decimal places. Round the exact ratio HALF_UP, as Django does.
    riesgo_promedio_ponderado: known ? decimal(roundHalfUp(weighted, known)) : null,
    posiciones_activas: active.length,
    monto_sin_riesgo_usd: decimal(total - known),
    paises_sin_riesgo: [...missing].sort(),
    riesgo_incompleto: known !== total,
    contiene_simulaciones: simulated,
    datos_parciales: partial,
  };
}

function decimal(value: bigint): string {
  return `${value / 100n}.${String(value % 100n).padStart(2, '0')}`;
}

function roundHalfUp(numerator: bigint, denominator: bigint): bigint {
  const quotient = numerator / denominator;
  const remainder = numerator % denominator;
  return quotient + (remainder * 2n >= denominator ? 1n : 0n);
}
