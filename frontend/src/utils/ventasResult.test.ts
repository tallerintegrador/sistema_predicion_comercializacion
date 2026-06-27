import { describe, it, expect } from 'vitest'
import {
  contarSeries,
  filasPorDimension,
  filtrarPorValores,
  totalesPorPeriodo,
  valoresDimension,
} from './ventasResult'
import type { ForecastItem } from '../api/types'

const fc = (date: string, store: string, product: string, demand: number): ForecastItem => ({
  date,
  store_id: store,
  product_id: product,
  forecast_demand: demand,
})

// Pronóstico de ejemplo: 2 tiendas × 1 producto × 2 fechas.
const FORECAST: ForecastItem[] = [
  fc('2017-08-03', '1', 'BEVERAGES', 10),
  fc('2017-08-04', '1', 'BEVERAGES', 20),
  fc('2017-08-03', '2', 'BEVERAGES', 5),
  fc('2017-08-04', '2', 'BEVERAGES', 7),
]

describe('valoresDimension (valores concretos desde el resultado)', () => {
  it('lista los valores distintos en orden natural', () => {
    expect(valoresDimension(FORECAST, 'store_id')).toEqual(['1', '2'])
    expect(valoresDimension(FORECAST, 'product_id')).toEqual(['BEVERAGES'])
  })

  it('ordena numéricamente como texto (10 después de 2)', () => {
    const rows = [fc('2017-08-03', '10', 'A', 1), fc('2017-08-03', '2', 'A', 1)]
    expect(valoresDimension(rows, 'store_id')).toEqual(['2', '10'])
  })
})

describe('filtrarPorValores (no recalcula: filtra la vista)', () => {
  it('selección vacía = todas las filas', () => {
    expect(filtrarPorValores(FORECAST, 'store_id', [])).toHaveLength(4)
  })

  it('conserva solo las filas de los valores elegidos', () => {
    const soloTienda1 = filtrarPorValores(FORECAST, 'store_id', ['1'])
    expect(soloTienda1).toHaveLength(2)
    expect(soloTienda1.every((f) => f.store_id === '1')).toBe(true)
  })
})

describe('totalesPorPeriodo (vista total)', () => {
  it('suma todas las series por fecha, ordenado por fecha', () => {
    expect(totalesPorPeriodo(FORECAST)).toEqual([
      { date: '2017-08-03', total: 15 },
      { date: '2017-08-04', total: 27 },
    ])
  })
})

describe('filasPorDimension y contarSeries', () => {
  it('ordena por dimensión y luego por fecha', () => {
    const filas = filasPorDimension(FORECAST, 'store_id')
    expect(filas.map((f) => `${f.store_id}@${f.date}`)).toEqual([
      '1@2017-08-03',
      '1@2017-08-04',
      '2@2017-08-03',
      '2@2017-08-04',
    ])
  })

  it('cuenta las series distintas (tienda×producto)', () => {
    expect(contarSeries(FORECAST)).toBe(2)
    expect(contarSeries(filtrarPorValores(FORECAST, 'store_id', ['1']))).toBe(1)
  })
})
