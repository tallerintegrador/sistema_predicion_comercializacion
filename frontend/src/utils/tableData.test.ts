import { describe, it, expect } from 'vitest'
import { coerceRows, emptyRow, objectsToRows, rowsComplete } from './tableData'
import type { CatalogColumn, InputTable } from '../api/types'

const cols: CatalogColumn[] = [
  { name: 'store_id', label: 'Tienda', type: 'str', required: true },
  { name: 'current_stock', label: 'Existencias', type: 'float', required: true },
  { name: 'lead_time_days', label: 'Entrega', type: 'int', required: false },
  { name: 'event_active', label: '¿Especial?', type: 'bool', required: false },
]

describe('coerceRows', () => {
  it('respeta los tipos del contrato y omite opcionales vacíos', () => {
    const [row] = coerceRows(cols, [
      { store_id: '1', current_stock: '10.5', lead_time_days: '', event_active: 'true' },
    ])
    expect(row.store_id).toBe('1')
    expect(row.current_stock).toBe(10.5)
    expect(typeof row.current_stock).toBe('number')
    expect('lead_time_days' in row).toBe(false) // opcional vacío → omitido
    expect(row.event_active).toBe(true)
  })
})

describe('rowsComplete', () => {
  it('exige los campos obligatorios', () => {
    expect(rowsComplete(cols, [{ store_id: '', current_stock: '10' }])).toBe(false)
    expect(rowsComplete(cols, [{ store_id: '1', current_stock: '10' }])).toBe(true)
    expect(rowsComplete(cols, [])).toBe(false)
  })
})

describe('objectsToRows', () => {
  it('convierte objetos del contrato en filas de texto', () => {
    const [row] = objectsToRows(cols, [{ store_id: 1, current_stock: 10, event_active: true }])
    expect(row.store_id).toBe('1')
    expect(row.current_stock).toBe('10')
    expect(row.event_active).toBe('true')
    expect(row.lead_time_days).toBe('') // ausente → texto vacío
  })
})

describe('emptyRow', () => {
  it('prellena con los valores por defecto editables del catálogo y deja vacío lo demás', () => {
    const table: InputTable = {
      name: 'replenishment_params',
      label: 'Productos a reponer',
      columns: [
        { name: 'store_id', label: 'Tienda', type: 'str', required: true },
        { name: 'lead_time_days', label: 'Entrega', type: 'int', required: true, default: 7 },
        { name: 'target_coverage_days', label: 'Cobertura', type: 'int', required: true, default: 14 },
      ],
    }
    const row = emptyRow(table)
    expect(row.store_id).toBe('') // sin default → vacío
    expect(row.lead_time_days).toBe('7') // default del catálogo (política), como texto editable
    expect(row.target_coverage_days).toBe('14')
  })
})
