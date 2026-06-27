import { describe, it, expect } from 'vitest'
import { applyFilters, facetOptions } from './useResultFilters'
import type { ResultFiltersSpec } from './useResultFilters'

interface Rec {
  store_id: string
  product_id: string
  qty: number
  risk: boolean
}

const rows: Rec[] = [
  { store_id: '2', product_id: 'A', qty: 0, risk: false },
  { store_id: '10', product_id: 'B', qty: 5, risk: true },
  { store_id: '1', product_id: 'A', qty: 3, risk: true },
]

const spec: ResultFiltersSpec<Rec> = {
  facets: [
    { key: 'store_id', label: 'Tienda', read: (r) => r.store_id },
    { key: 'product_id', label: 'Producto', read: (r) => r.product_id },
  ],
  toggles: [{ key: 'needs', label: 'Solo reposición', predicate: (r) => r.qty > 0 }],
  sorts: [
    { key: 'qty', label: 'Cantidad', compare: (a, b) => b.qty - a.qty },
    {
      key: 'store',
      label: 'Tienda',
      compare: (a, b) => a.store_id.localeCompare(b.store_id, 'es', { numeric: true }),
    },
  ],
}

describe('facetOptions', () => {
  it('devuelve valores distintos en orden natural y omite vacíos', () => {
    expect(facetOptions(rows, spec.facets![0])).toEqual(['1', '2', '10']) // numérico, no "1,10,2"
    expect(facetOptions(rows, spec.facets![1])).toEqual(['A', 'B'])
  })
})

describe('applyFilters', () => {
  it('filtra por faceta de igualdad usando valores reales', () => {
    const out = applyFilters(rows, spec, { facets: { product_id: 'A' }, toggles: {}, sort: '' })
    expect(out.map((r) => r.store_id).sort()).toEqual(['1', '2'])
  })

  it('aplica el interruptor solo cuando está activo', () => {
    const sinToggle = applyFilters(rows, spec, { facets: {}, toggles: { needs: false }, sort: '' })
    expect(sinToggle).toHaveLength(3)
    const conToggle = applyFilters(rows, spec, { facets: {}, toggles: { needs: true }, sort: '' })
    expect(conToggle.every((r) => r.qty > 0)).toBe(true)
    expect(conToggle).toHaveLength(2)
  })

  it('ordena según la opción elegida sin mutar la entrada', () => {
    const out = applyFilters(rows, spec, { facets: {}, toggles: {}, sort: 'qty' })
    expect(out.map((r) => r.qty)).toEqual([5, 3, 0])
    expect(rows.map((r) => r.qty)).toEqual([0, 5, 3]) // original intacto
  })

  it('combina faceta + interruptor + orden', () => {
    const out = applyFilters(rows, spec, {
      facets: { product_id: 'A' },
      toggles: { needs: true },
      sort: 'store',
    })
    expect(out).toHaveLength(1)
    expect(out[0]).toMatchObject({ store_id: '1', product_id: 'A' })
  })
})
