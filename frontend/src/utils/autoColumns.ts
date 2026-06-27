/**
 * Columnas dinámicas para los resultados del motor agnóstico (ADR-0023).
 *
 * Las respuestas de `/auto/*` traen registros de columnas LIBRES (el esquema lo declara el
 * cliente). Esta tabla arma encabezados y formato sin hardcodear columnas: une las claves de
 * todas las filas y aplica etiquetas/formato conocidos cuando existen, o el valor tal cual.
 *
 * Compartido por «Predicción a tu medida» (AutoPage) y «Ventas» (SalesPage, que ahora usa el
 * mismo motor agnóstico).
 */
import type { AutoRow } from '../api/types'
import type { Column } from '../components/ResultTable'
import { fmtInt, fmtNum, fmtPct } from './format'

/** Etiquetas en español para las columnas de salida conocidas (las demás se muestran tal cual). */
export const COL_LABEL: Record<string, string> = {
  almacen: 'Almacén',
  sku: 'SKU',
  date: 'Fecha',
  fecha: 'Fecha',
  // ventas
  forecast_demand: 'Demanda pronosticada',
  // compras
  expected_demand_horizon: 'Demanda esperada',
  reorder_point: 'Punto de reorden',
  replenishment_quantity: 'Cantidad a reponer',
  justification: 'Cálculo',
  // inventario
  demand_class: 'Nivel de demanda',
  high_demand_probability: 'Prob. demanda alta',
  stockout_risk: 'Riesgo de quiebre',
  recommended_stock: 'Stock recomendado',
  safety_stock: 'Stock de seguridad',
  volume_segment: 'Segmento de volumen',
}

/** Columnas de cantidad: enteros (no tiene sentido «1392,8 unidades» a reponer). */
export const COL_ENTERA = new Set([
  'forecast_demand', 'expected_demand_horizon', 'reorder_point',
  'replenishment_quantity', 'recommended_stock', 'safety_stock',
])

/** Columnas que son probabilidad 0–1 → se muestran como porcentaje. */
export const COL_PROB = new Set(['high_demand_probability'])

/** Valores categóricos traducidos. */
export const VALOR_ES: Record<string, Record<string, string>> = {
  demand_class: { high: 'Alta', low: 'Baja' },
}

/** Justificaciones (fórmulas fijas del backend) en lenguaje claro. */
export const JUSTIFICACION_ES: Record<string, string> = {
  'forecast_demand(lead + coverage) + safety_stock - current_stock':
    'Demanda pronosticada (entrega + cobertura) + stock de seguridad − stock actual',
}

/** Columnas dinámicas: unión de las claves de todas las filas (esquema arbitrario). */
export function columnasDinamicas(rows: AutoRow[]): Column<AutoRow>[] {
  const claves: string[] = []
  for (const r of rows) for (const k of Object.keys(r)) if (!claves.includes(k)) claves.push(k)
  return claves.map((k) => ({
    header: COL_LABEL[k] ?? k,
    align: typeof rows[0]?.[k] === 'number' ? 'right' : 'left',
    render: (row: AutoRow) => {
      const v = row[k]
      if (k === 'justification' && typeof v === 'string') return JUSTIFICACION_ES[v] ?? v
      if (k in VALOR_ES && typeof v === 'string') return VALOR_ES[k][v] ?? v
      if (typeof v === 'number') {
        if (COL_PROB.has(k)) return fmtPct(v)
        if (COL_ENTERA.has(k)) return fmtInt(v)
        return fmtNum(v)
      }
      if (typeof v === 'boolean') return v ? 'Sí' : 'No'
      return v == null ? '—' : String(v)
    },
  }))
}
