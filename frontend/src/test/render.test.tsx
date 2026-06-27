import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { RiskBadge } from '../components/ui/RiskBadge'
import { ComingSoon } from '../components/ui/ComingSoon'
import type { AlertItem } from '../api/types'

// Términos que NUNCA deben aparecer en la interfaz del usuario (ADR-0019).
const PROHIBIDOS = ['SALES', 'PURCHASES', 'INVENTORY', 'stock', 'lead time', 'forecast', 'WAPE', 'opt-in']

describe('ModuleHeader (lenguaje sin tecnicismos)', () => {
  it('muestra el nombre del módulo en español', () => {
    render(<ModuleHeader view="sales" />)
    expect(screen.getByRole('heading', { name: 'Ventas' })).toBeInTheDocument()
  })

  it('no expone términos en inglés ni tecnicismos', () => {
    const { container } = render(<ModuleHeader view="inventory" />)
    const texto = container.textContent ?? ''
    for (const t of PROHIBIDOS) expect(texto).not.toContain(t)
  })
})

describe('RiskBadge (semáforo en español)', () => {
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

  it('marca el riesgo de agotarse de forma clara', () => {
    render(<RiskBadge alert={alert(true)} />)
    expect(screen.getByText(/riesgo de agotarse/i)).toBeInTheDocument()
  })
})

describe('ComingSoon', () => {
  it('rotula honestamente lo no disponible', () => {
    render(<ComingSoon />)
    expect(screen.getByText('Próximamente')).toBeInTheDocument()
  })
})
