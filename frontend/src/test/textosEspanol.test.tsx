import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { InventoryRisk } from '../components/charts/InventoryRisk'
import { LEGEND_HISTORICO, LEGEND_PRONOSTICO } from '../components/charts/SalesChart'
import { PORQUE } from '../components/prediccion/resumen'
import type { AlertItem } from '../api/types'

// Términos internos/ingleses que no deben filtrarse a la interfaz (ADR-0019/0022).
const alerta = (demandClass: 'high' | 'low'): AlertItem => ({
  store_id: '1',
  product_id: 'BEVERAGES',
  demand_class: demandClass,
  high_demand_probability: 0.8,
  stockout_risk: true,
  recommended_stock: 120,
  safety_stock: 30,
  store_segment: 2,
})

describe('Leyenda de Ventas (sin nombres del contrato)', () => {
  it('usa español y no expone units_sold / forecast_demand', () => {
    expect(LEGEND_HISTORICO).toBe('Histórico (unidades vendidas)')
    expect(LEGEND_PRONOSTICO).toBe('Pronóstico (demanda estimada)')
    for (const txt of [LEGEND_HISTORICO, LEGEND_PRONOSTICO]) {
      expect(txt).not.toContain('units_sold')
      expect(txt).not.toContain('forecast_demand')
    }
  })
})

describe('InventoryRisk (clase de demanda y existencias en español)', () => {
  it('traduce la clase de demanda alta y no muestra "high"', () => {
    const { container } = render(<InventoryRisk alerts={[alerta('high')]} />)
    expect(screen.getByText('demanda alta')).toBeInTheDocument()
    expect(container.textContent).not.toContain('demanda high')
  })

  it('traduce la clase de demanda baja', () => {
    render(<InventoryRisk alerts={[alerta('low')]} />)
    expect(screen.getByText('demanda baja')).toBeInTheDocument()
  })

  it('usa "Existencias" en vez de "Stock"', () => {
    const { container } = render(<InventoryRisk alerts={[alerta('high')]} />)
    expect(screen.getByText('Existencias recomendadas')).toBeInTheDocument()
    expect(screen.getByText('Existencias de seguridad')).toBeInTheDocument()
    expect(container.textContent).not.toContain('Stock')
  })
})

describe('Compras «Por qué» (frase clara, no la fórmula cruda)', () => {
  it('explica el cálculo en lenguaje claro sin la fórmula del backend', () => {
    expect(PORQUE).toContain('tiempo de entrega')
    expect(PORQUE).toContain('existencias de seguridad')
    for (const t of ['forecast_demand', 'safety_stock', 'current_stock', 'lead_time']) {
      expect(PORQUE).not.toContain(t)
    }
  })
})
