import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResultFilters } from './ResultFilters'
import type { ResultFiltersSpec, ResultFiltersState } from '../../hooks/useResultFilters'

interface Row {
  store_id: string
}

const spec: ResultFiltersSpec<Row> = {
  facets: [{ key: 'store_id', label: 'Tienda', read: (r) => r.store_id }],
  toggles: [{ key: 'needs', label: 'Solo reposición', predicate: () => true }],
  sorts: [{ key: 'qty', label: 'Cantidad', compare: () => 0 }],
}

const state: ResultFiltersState<Row> = {
  filtered: [],
  options: { store_id: ['1', '2'] },
  facets: {},
  setFacet: () => {},
  toggles: {},
  setToggle: () => {},
  sort: 'qty',
  setSort: () => {},
}

describe('ResultFilters', () => {
  it('muestra facetas, orden e interruptores disponibles', () => {
    render(<ResultFilters spec={spec} filters={state} />)
    expect(screen.getByLabelText('Tienda')).toBeInTheDocument()
    expect(screen.getByLabelText('Ordenar por')).toBeInTheDocument()
    expect(screen.getByText('Solo reposición')).toBeInTheDocument()
  })

  it('rotula lo no disponible como «Próximamente» y lo deja deshabilitado', () => {
    render(
      <ResultFilters
        spec={spec}
        filters={state}
        comingSoon={[{ key: 'category', label: 'Categoría / familia' }]}
      />,
    )
    expect(screen.getByText('Próximamente')).toBeInTheDocument()
    // El control planificado se muestra, pero deshabilitado (no se simula).
    const combos = screen.getAllByRole('combobox') as HTMLSelectElement[]
    expect(combos.some((c) => c.disabled)).toBe(true)
  })
})
