/**
 * Funciones puras de la predicción guiada: resúmenes en lenguaje natural y resolución de
 * los controles extra del Paso 2 (granularidad, horizonte, percentil). Sin JSX, para que
 * los módulos que sí exportan componentes (resultados, configs) cumplan la regla de
 * fast-refresh (un archivo = solo componentes).
 */
import type { AutoRow, Granularity } from '../../api/types'
import { fmtNum } from '../../utils/format'

const PERIODO: Record<Granularity, [string, string]> = {
  day: ['día', 'días'],
  week: ['semana', 'semanas'],
  month: ['mes', 'meses'],
}

// Explicación en lenguaje claro de cómo se obtiene «cuánto reponer» (ADR-0022). El backend
// envía la fórmula cruda en `justification`; aquí se describe sin exponerla.
export const PORQUE =
  'Demanda estimada durante el tiempo de entrega más la cobertura, y unas existencias de seguridad.'

export function resumenVentas(forecast: AutoRow[], granularity: Granularity, target: string): string {
  if (forecast.length === 0) return 'No hay pronóstico para mostrar.'
  const total = forecast.reduce((a, f) => a + (Number(f.forecast_demand) || 0), 0)
  const periodos = new Set(forecast.map((f) => String(f.date))).size
  const [sing, plur] = PERIODO[granularity]
  return `Se estima un total de aproximadamente ${fmtNum(total)} de «${target}» en ${fmtNum(
    periodos,
  )} ${periodos === 1 ? sing : plur}.`
}

export function resumenCompras(recs: AutoRow[]): string {
  if (recs.length === 0) return 'No hay recomendaciones para mostrar.'
  const aReponer = recs.filter((r) => Number(r.replenishment_quantity) > 0)
  const total = aReponer.reduce((a, r) => a + (Number(r.replenishment_quantity) || 0), 0)
  if (aReponer.length === 0) {
    return 'Por ahora no necesitas reponer ninguno de estos productos: tus existencias cubren la demanda estimada.'
  }
  return `Conviene reponer alrededor de ${fmtNum(total)} unidades repartidas en ${fmtNum(
    aReponer.length,
  )} ${aReponer.length === 1 ? 'producto' : 'productos'}.`
}

const enRiesgo = (a: AutoRow) => a.stockout_risk === true || a.stockout_risk === 'true'

export function resumenAlmacen(alerts: AutoRow[]): string {
  if (alerts.length === 0) return 'No hay productos para evaluar.'
  const riesgo = alerts.filter(enRiesgo).length
  if (riesgo === 0) {
    return `Ninguno de los ${fmtNum(alerts.length)} productos evaluados tiene riesgo de agotarse por ahora.`
  }
  return `${fmtNum(riesgo)} ${riesgo === 1 ? 'producto tiene' : 'productos tienen'} riesgo de agotarse, de ${fmtNum(
    alerts.length,
  )} evaluados. Revisa el nivel de existencias sugerido.`
}

// === Resolución de los controles extra del Paso 2 ===========================
export const granularidadDe = (
  extra: Record<string, unknown>,
  opts: { granularities?: { name: Granularity }[] } | null,
): Granularity => (extra.granularity as Granularity) ?? opts?.granularities?.[0]?.name ?? 'day'

export const horizonteDe = (
  extra: Record<string, unknown>,
  opts: { horizon?: { default: number } } | null,
): number => (extra.horizon as number) ?? opts?.horizon?.default ?? 7

export const percentilDe = (extra: Record<string, unknown>): number => (extra.percentil as number) ?? 75
