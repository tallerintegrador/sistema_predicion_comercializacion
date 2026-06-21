/**
 * Resúmenes en **lenguaje natural** de los resultados (ADR-0019). Son funciones puras,
 * derivadas SOLO de los datos reales que devuelve la API (nunca inventan cifras), pensadas
 * para que un dueño de negocio entienda el resultado de un vistazo.
 */
import type { AlertItem, ForecastItem, Granularity, RecommendationItem } from '../api/types'
import { fmtNum } from './format'

const PERIODO: Record<Granularity, [string, string]> = {
  day: ['día', 'días'],
  week: ['semana', 'semanas'],
  month: ['mes', 'meses'],
}

/** Plural simple en español con el sustantivo correcto. */
function plural(n: number, sing: string, plur: string): string {
  return `${fmtNum(n)} ${n === 1 ? sing : plur}`
}

/** Resumen de Ventas: demanda total estimada y horizonte. */
export function resumenVentas(forecast: ForecastItem[], granularity: Granularity): string {
  if (forecast.length === 0) return 'No hay pronóstico para mostrar.'
  const total = forecast.reduce((acc, f) => acc + f.forecast_demand, 0)
  const periodos = new Set(forecast.map((f) => f.date)).size
  const [sing, plur] = PERIODO[granularity]
  return `Se estima una demanda total de aproximadamente ${fmtNum(total)} unidades en ${plural(
    periodos,
    sing,
    plur,
  )}.`
}

/** Resumen de Compras: cuántos productos reponer y cuántas unidades en total. */
export function resumenCompras(items: RecommendationItem[]): string {
  if (items.length === 0) return 'No hay recomendaciones para mostrar.'
  const aReponer = items.filter((r) => r.replenishment_quantity > 0)
  const totalUnidades = aReponer.reduce((acc, r) => acc + r.replenishment_quantity, 0)
  if (aReponer.length === 0) {
    return 'Por ahora no necesitas reponer ninguno de estos productos: tus existencias cubren la demanda estimada.'
  }
  return `Conviene reponer alrededor de ${fmtNum(totalUnidades)} unidades repartidas en ${plural(
    aReponer.length,
    'producto',
    'productos',
  )}.`
}

/** Resumen de Almacén: cuántos productos en riesgo de agotarse. */
export function resumenAlmacen(alerts: AlertItem[]): string {
  if (alerts.length === 0) return 'No hay productos para evaluar.'
  const enRiesgo = alerts.filter((a) => a.stockout_risk).length
  if (enRiesgo === 0) {
    return `Ninguno de los ${fmtNum(alerts.length)} productos evaluados tiene riesgo de agotarse por ahora.`
  }
  return `${plural(enRiesgo, 'producto tiene', 'productos tienen')} riesgo de agotarse, de ${fmtNum(
    alerts.length,
  )} evaluados. Revisa el nivel de existencias sugerido.`
}
