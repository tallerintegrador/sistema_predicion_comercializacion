import { describe, it, expect } from 'vitest'
import {
  analizarColumnas,
  candidatasSerie,
  candidatasTarget,
  columnasFecha,
  columnasNumericas,
  construirEsquema,
  esConocidaFutura,
  normalizarFilas,
  sugerirFecha,
  sugerirSeries,
  sugerirTarget,
} from './inferSchema'
import type { AutoRow } from '../api/types'

// Datos ricos: fecha + identificadores + numéricas (unidades, ingresos) + categórica.
const ROWS: AutoRow[] = [
  { fecha: '2024-01-01', tienda: 'lima', sku: 'A', unidades_vendidas: 10, ingresos: 100.5, clima: 'soleado' },
  { fecha: '2024-01-02', tienda: 'lima', sku: 'A', unidades_vendidas: 12, ingresos: 120, clima: 'lluvia' },
  { fecha: '2024-01-01', tienda: 'cusco', sku: 'B', unidades_vendidas: 7, ingresos: 70, clima: 'nublado' },
]

describe('analizarColumnas', () => {
  it('clasifica fecha, numéricas y categóricas', () => {
    const cols = analizarColumnas(ROWS)
    const tipo = (n: string) => cols.find((c) => c.name === n)?.kind
    expect(tipo('fecha')).toBe('date')
    expect(tipo('unidades_vendidas')).toBe('numeric')
    expect(tipo('ingresos')).toBe('numeric')
    expect(tipo('tienda')).toBe('categorical')
    expect(tipo('clima')).toBe('categorical')
  })

  it('calcula la cardinalidad', () => {
    const cols = analizarColumnas(ROWS)
    expect(cols.find((c) => c.name === 'tienda')?.cardinality).toBe(2)
    expect(cols.find((c) => c.name === 'sku')?.cardinality).toBe(2)
  })
})

describe('sugerencias de mapeo', () => {
  const cols = analizarColumnas(ROWS)

  it('sugiere la columna de fecha por nombre/tipo', () => {
    expect(sugerirFecha(cols)).toBe('fecha')
  })

  it('sugiere el target según la intención', () => {
    expect(sugerirTarget(cols, 'producto', ['fecha'])).toBe('unidades_vendidas')
    expect(sugerirTarget(cols, 'dinero', ['fecha'])).toBe('ingresos')
  })

  it('sugiere claves de serie identificadoras (tienda/sku)', () => {
    const series = sugerirSeries(cols, ['fecha', 'unidades_vendidas'])
    expect(series).toContain('tienda')
    expect(series).toContain('sku')
  })

  it('columnasNumericas excluye la fecha y las no numéricas', () => {
    const nums = columnasNumericas(cols, ['fecha']).map((c) => c.name)
    expect(nums).toEqual(expect.arrayContaining(['unidades_vendidas', 'ingresos']))
    expect(nums).not.toContain('clima')
    expect(nums).not.toContain('fecha')
  })

  it('columnasFecha solo ofrece columnas tipo fecha (y todas como respaldo)', () => {
    expect(columnasFecha(cols).map((c) => c.name)).toEqual(['fecha'])
    const sinFecha = analizarColumnas([{ tienda: 'lima', unidades_vendidas: 10 }])
    // Sin columnas fecha, devuelve todas para no dejar el menú vacío.
    expect(columnasFecha(sinFecha).length).toBe(sinFecha.length)
  })

  it('candidatasSerie excluye numéricas, fecha y alta cardinalidad', () => {
    const ser = candidatasSerie(cols, { excluir: ['fecha', 'unidades_vendidas'] }).map((c) => c.name)
    expect(ser).toEqual(expect.arrayContaining(['tienda', 'sku', 'clima']))
    expect(ser).not.toContain('ingresos') // numérica
    expect(candidatasSerie(cols, { excluir: [], maxCardinalidad: 1 }).length).toBe(0)
  })
})

describe('known_future y orden de target', () => {
  it('esConocidaFutura marca los rezagos como solo-pasado', () => {
    expect(esConocidaFutura('precio')).toBe(true)
    expect(esConocidaFutura('es_feriado')).toBe(true)
    expect(esConocidaFutura('ausentismo_prev')).toBe(false)
    expect(esConocidaFutura('trafico_web_prev')).toBe(false)
    expect(esConocidaFutura('ventas_ult')).toBe(false)
  })

  it('candidatasTarget pone medidas continuas antes que flags y rezagos', () => {
    const rows: AutoRow[] = [
      { fecha: '2024-01-01', pacientes: 30, es_feriado: 0, ausentismo_prev: 2 },
      { fecha: '2024-01-02', pacientes: 41, es_feriado: 1, ausentismo_prev: 3 },
      { fecha: '2024-01-03', pacientes: 25, es_feriado: 0, ausentismo_prev: 1 },
    ]
    const cols = analizarColumnas(rows)
    const orden = candidatasTarget(cols, ['fecha']).map((c) => c.name)
    expect(orden[0]).toBe('pacientes')
    expect(orden.indexOf('ausentismo_prev')).toBeLessThan(orden.indexOf('es_feriado'))
  })

  it('construirEsquema infiere known_future y respeta el override', () => {
    const rows: AutoRow[] = [
      { fecha: '2024-01-01', tienda: 'lima', demanda: 10, precio: 5, trafico_prev: 100 },
      { fecha: '2024-01-02', tienda: 'lima', demanda: 12, precio: 5, trafico_prev: 120 },
    ]
    const cols = analizarColumnas(rows)
    const schema = construirEsquema({ cols, target: 'demanda', date: 'fecha', seriesKeys: ['tienda'] })
    const kf = (n: string) => schema.features.find((f) => f.name === n)?.known_future
    expect(kf('precio')).toBe(true)
    expect(kf('trafico_prev')).toBe(false) // rezago → solo pasado
    const conOverride = construirEsquema({
      cols,
      target: 'demanda',
      date: 'fecha',
      seriesKeys: ['tienda'],
      futureOverrides: { trafico_prev: true },
    })
    expect(conOverride.features.find((f) => f.name === 'trafico_prev')?.known_future).toBe(true)
  })
})

describe('construirEsquema', () => {
  it('reserva target/fecha/series y deja el resto como features', () => {
    const cols = analizarColumnas(ROWS)
    const schema = construirEsquema({
      cols,
      target: 'unidades_vendidas',
      date: 'fecha',
      seriesKeys: ['tienda', 'sku'],
    })
    expect(schema.target).toBe('unidades_vendidas')
    expect(schema.date).toBe('fecha')
    expect(schema.series_keys).toEqual(['tienda', 'sku'])
    const featNames = schema.features.map((f) => f.name)
    expect(featNames).toContain('ingresos')
    expect(featNames).toContain('clima')
    expect(featNames).not.toContain('unidades_vendidas')
    expect(featNames).not.toContain('fecha')
    // tipos inferidos
    expect(schema.features.find((f) => f.name === 'ingresos')?.type).toBe('numeric')
    expect(schema.features.find((f) => f.name === 'clima')?.type).toBe('categorical')
  })
})

describe('normalizarFilas', () => {
  it('coacciona cadenas numéricas a número', () => {
    const rows: AutoRow[] = [{ fecha: '2024-01-01', tienda: 'lima', unidades_vendidas: '15', precio: '4.5' }]
    const cols = analizarColumnas(rows)
    const out = normalizarFilas(rows, cols)
    expect(out[0].unidades_vendidas).toBe(15)
    expect(out[0].precio).toBe(4.5)
    expect(out[0].tienda).toBe('lima')
  })
})
