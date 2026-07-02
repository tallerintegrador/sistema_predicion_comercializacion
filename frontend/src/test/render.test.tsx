import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { ComingSoon } from '../components/ui/ComingSoon'

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

describe('ComingSoon', () => {
  it('rotula honestamente lo no disponible', () => {
    render(<ComingSoon />)
    expect(screen.getByText('Próximamente')).toBeInTheDocument()
  })
})
