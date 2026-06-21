import { describe, it, expect } from 'vitest'
import { resumenVentas, resumenCompras, resumenAlmacen } from './resumen'
import type { AlertItem, ForecastItem, RecommendationItem } from '../api/types'

const fc = (date: string, demand: number): ForecastItem => ({
  date,
  store_id: '1',
  product_id: 'A',
  forecast_demand: demand,
})

describe('resumenVentas', () => {
  it('suma la demanda y cuenta los períodos', () => {
    const s = resumenVentas([fc('2024-01-01', 10), fc('2024-01-02', 5)], 'day')
    expect(s).toContain('15')
    expect(s).toContain('días')
  })
  it('degrada con elegancia si no hay datos', () => {
    expect(resumenVentas([], 'day')).toMatch(/No hay/i)
  })
})

const rec = (q: number, id = 'A'): RecommendationItem => ({
  store_id: '1',
  product_id: id,
  expected_demand_horizon: 0,
  reorder_point: 0,
  replenishment_quantity: q,
  justification: '',
})

describe('resumenCompras', () => {
  it('cuenta solo los productos a reponer', () => {
    const s = resumenCompras([rec(20, 'A'), rec(0, 'B')])
    expect(s).toContain('20')
    expect(s).toContain('producto')
  })
  it('avisa cuando no hace falta reponer', () => {
    expect(resumenCompras([rec(0)])).toMatch(/no necesitas reponer/i)
  })
})

const alert = (risk: boolean): AlertItem => ({
  store_id: '1',
  product_id: 'A',
  demand_class: 'low',
  high_demand_probability: 0.1,
  stockout_risk: risk,
  recommended_stock: 0,
  safety_stock: 0,
  store_segment: 0,
})

describe('resumenAlmacen', () => {
  it('cuenta los productos en riesgo', () => {
    expect(resumenAlmacen([alert(true), alert(false)])).toMatch(/riesgo de agotarse/i)
  })
  it('tranquiliza cuando no hay riesgo', () => {
    expect(resumenAlmacen([alert(false)])).toMatch(/ninguno/i)
  })
})
