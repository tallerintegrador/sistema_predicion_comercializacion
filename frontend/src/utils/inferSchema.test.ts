import { describe, it, expect } from 'vitest'
import {
  analizarColumnas,
  columnasNumericas,
  construirEsquema,
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
