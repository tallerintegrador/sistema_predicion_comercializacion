/**
 * Vistas y filtros SOBRE EL RESULTADO de Ventas (funciones puras y testeables).
 *
 * Principio (igual que Compras/Almacén): todo sale de las filas reales del pronóstico que
 * devuelve la API; nunca se inventan valores. El usuario pronostica una vez y explora el
 * mismo resultado de varias formas (total / por dimensión / valores concretos) sin
 * recalcular. Como los valores salen de la respuesta, funcionan para cualquier canal,
 * también Excel.
 */
import type { ForecastItem } from '../api/types'

// Solo se desglosa/filtra por columnas identificadoras del histórico (R2).
export type DimKey = 'store_id' | 'product_id'

/** Valores distintos de una dimensión en el resultado, en orden natural (es, numérico). */
export function valoresDimension<T extends Record<DimKey, string>>(rows: T[], dim: DimKey): string[] {
  const vals = new Set<string>()
  for (const r of rows) vals.add(String(r[dim]))
  return Array.from(vals).sort((a, b) => a.localeCompare(b, 'es', { numeric: true }))
}

/** Filtra filas por valores concretos de una dimensión; una selección vacía = «todas». */
export function filtrarPorValores<T extends Record<DimKey, string>>(
  rows: T[],
  dim: DimKey,
  selected: string[],
): T[] {
  if (selected.length === 0) return rows
  const set = new Set(selected)
  return rows.filter((r) => set.has(String(r[dim])))
}

/** Demanda total por período (suma sobre todas las series), ordenada por fecha. */
export function totalesPorPeriodo(forecast: ForecastItem[]): { date: string; total: number }[] {
  const m = new Map<string, number>()
  for (const f of forecast) m.set(f.date, (m.get(f.date) ?? 0) + f.forecast_demand)
  return Array.from(m, ([date, total]) => ({ date, total })).sort((a, b) =>
    a.date.localeCompare(b.date),
  )
}

/** Filas del desglose por dimensión, ordenadas por la dimensión elegida y luego por fecha. */
export function filasPorDimension(forecast: ForecastItem[], dim: DimKey): ForecastItem[] {
  return [...forecast].sort((a, b) => {
    const k = String(a[dim]).localeCompare(String(b[dim]))
    return k !== 0 ? k : a.date.localeCompare(b.date)
  })
}

/** Nº de series distintas (tienda×producto) presentes en el resultado. */
export function contarSeries(forecast: ForecastItem[]): number {
  return new Set(forecast.map((f) => `${f.store_id}|${f.product_id}`)).size
}
