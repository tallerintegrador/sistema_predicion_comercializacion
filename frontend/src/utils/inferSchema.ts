/**
 * Inferencia de esquema para «Ventas» (ADR-0023). El módulo de Ventas usa el motor
 * agnóstico, pero NO le pide al usuario que escriba un esquema JSON a mano (como sí hace
 * «Predicción a tu medida»). En su lugar, lee las columnas de los datos subidos y propone:
 *   - qué columna es la fecha,
 *   - qué columnas identifican cada serie (tienda × producto),
 *   - qué columna pronosticar (target), con sugerencias por intención (unidades / dinero).
 * El usuario confirma o ajusta en menús; el resto de columnas pasan a ser «features».
 *
 * Todas las funciones son puras y testeables: derivan solo de los datos reales subidos.
 */
import type { AutoFeatureSpec, AutoRow, AutoSchemaSpec } from '../api/types'

export type ColKind = 'numeric' | 'categorical' | 'date'

export interface ColumnInfo {
  name: string
  kind: ColKind
  cardinality: number // nº de valores distintos
  sample: string // un valor de muestra (para previsualizar)
}

const RE_FECHA = /^\d{4}[-/]\d{1,2}[-/]\d{1,2}/

/** ¿El valor parece una fecha (ISO o con separadores)? */
function esFecha(v: unknown): boolean {
  if (v instanceof Date) return true
  if (typeof v !== 'string') return false
  return RE_FECHA.test(v.trim())
}

/** ¿El valor es un número (o cadena numérica no vacía)? */
function esNumero(v: unknown): boolean {
  if (typeof v === 'number') return Number.isFinite(v)
  if (typeof v === 'string' && v.trim() !== '') return Number.isFinite(Number(v))
  return false
}

/** Clasifica cada columna a partir de una muestra de filas (umbral 80% de no nulos). */
export function analizarColumnas(rows: AutoRow[]): ColumnInfo[] {
  if (rows.length === 0) return []
  const nombres: string[] = []
  for (const r of rows) for (const k of Object.keys(r)) if (!nombres.includes(k)) nombres.push(k)

  return nombres.map((name) => {
    const valores = rows.map((r) => r[name]).filter((v) => v != null && v !== '')
    const distintos = new Set(valores.map((v) => String(v)))
    const total = valores.length || 1
    const fechas = valores.filter(esFecha).length
    const nums = valores.filter(esNumero).length

    let kind: ColKind = 'categorical'
    if (fechas / total >= 0.8) kind = 'date'
    else if (nums / total >= 0.8) kind = 'numeric'

    return {
      name,
      kind,
      cardinality: distintos.size,
      sample: valores.length > 0 ? String(valores[0]) : '',
    }
  })
}

/** Sugiere la columna de fecha: por nombre conocido, o la primera columna tipo fecha. */
export function sugerirFecha(cols: ColumnInfo[]): string | null {
  const porNombre = cols.find((c) => /fecha|date|dia|día|periodo|período/i.test(c.name))
  if (porNombre) return porNombre.name
  return cols.find((c) => c.kind === 'date')?.name ?? null
}

/** Sugiere claves de serie: columnas identificadoras (tienda/producto) de baja cardinalidad. */
export function sugerirSeries(cols: ColumnInfo[], excluir: string[]): string[] {
  const libres = cols.filter((c) => !excluir.includes(c.name))
  const porNombre = libres.filter((c) =>
    /tienda|store|almacen|almacén|sucursal|sku|product|producto|item|articulo|artículo/i.test(c.name),
  )
  if (porNombre.length > 0) return porNombre.map((c) => c.name)
  // Si no hay nombres claros, las categóricas de menor cardinalidad son buenas candidatas.
  return libres
    .filter((c) => c.kind === 'categorical' && c.cardinality > 1)
    .sort((a, b) => a.cardinality - b.cardinality)
    .slice(0, 2)
    .map((c) => c.name)
}

/** Intención de pronóstico → patrón de nombre de columna sugerido. */
const PATRON_INTENCION: Record<'producto' | 'dinero', RegExp> = {
  producto: /unidad|venta|vendid|sold|units|qty|cantidad|demanda/i,
  dinero: /ingreso|revenue|monto|dinero|importe|amount|venta_?s?_?(monto|valor)|facturacion|facturación|total/i,
}

/** Sugiere el target según la intención, entre las columnas numéricas disponibles. */
export function sugerirTarget(
  cols: ColumnInfo[],
  intencion: 'producto' | 'dinero',
  excluir: string[],
): string | null {
  const numericas = cols.filter((c) => c.kind === 'numeric' && !excluir.includes(c.name))
  const match = numericas.find((c) => PATRON_INTENCION[intencion].test(c.name))
  if (match) return match.name
  return numericas[0]?.name ?? null
}

/** Columnas numéricas (candidatas a target «Otro»). */
export function columnasNumericas(cols: ColumnInfo[], excluir: string[] = []): ColumnInfo[] {
  return cols.filter((c) => c.kind === 'numeric' && !excluir.includes(c.name))
}

/**
 * Construye el `AutoSchemaSpec` a partir de las elecciones del usuario. Las columnas que no
 * son target/fecha/serie pasan a `features` con su tipo inferido. `known_future` queda en
 * `true` por defecto: si el cliente no aporta un bloque `future`, el backend arrastra el
 * último valor (categóricas) o asume 0 (numéricas) — decisión B del diseño de Ventas.
 */
export function construirEsquema(opts: {
  cols: ColumnInfo[]
  target: string
  date: string
  seriesKeys: string[]
}): AutoSchemaSpec {
  const { cols, target, date, seriesKeys } = opts
  const reservadas = new Set([target, date, ...seriesKeys])
  const features: AutoFeatureSpec[] = cols
    .filter((c) => !reservadas.has(c.name) && c.kind !== 'date')
    .map((c) => ({
      name: c.name,
      type: c.kind === 'numeric' ? 'numeric' : 'categorical',
      known_future: true,
    }))
  return { target, date, series_keys: seriesKeys, features }
}

/** Coacciona los valores numéricos de cadena a número (el motor agnóstico espera números). */
export function normalizarFilas(rows: AutoRow[], cols: ColumnInfo[]): AutoRow[] {
  const numericas = new Set(cols.filter((c) => c.kind === 'numeric').map((c) => c.name))
  return rows.map((r) => {
    const out: AutoRow = { ...r }
    for (const k of numericas) {
      const v = out[k]
      if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) out[k] = Number(v)
    }
    return out
  })
}
