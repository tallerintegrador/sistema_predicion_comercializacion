import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { TablaInteractiva } from './TablaInteractiva'
import type { AutoRow } from '../../api/types'

const filas = (n: number): AutoRow[] =>
  Array.from({ length: n }, (_, i) => ({ Categoría: `Cat ${i}`, Total: i * 10 }))

describe('TablaInteractiva — buscador según cantidad de filas (A10)', () => {
  it('OCULTA el buscador con 6 filas o menos', () => {
    const { queryByPlaceholderText } = render(
      <TablaInteractiva rows={filas(6)} columns={['Categoría', 'Total']} />,
    )
    expect(queryByPlaceholderText('Buscar…')).toBeNull()
  })

  it('MUESTRA el buscador con más de 6 filas', () => {
    const { queryByPlaceholderText } = render(
      <TablaInteractiva rows={filas(10)} columns={['Categoría', 'Total']} />,
    )
    expect(queryByPlaceholderText('Buscar…')).not.toBeNull()
  })
})
