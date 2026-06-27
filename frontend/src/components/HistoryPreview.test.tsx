import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { HistoryPreview } from './HistoryPreview'

/** Normaliza el espacio duro (&nbsp;) para poder comparar el texto renderizado. */
const texto = (el: HTMLElement) => (el.textContent ?? '').replace(/\u00a0/g, ' ')

describe('HistoryPreview (resumen sin filas vacías)', () => {
  it('no cuenta filas en blanco en «Filas»', () => {
    const { container } = render(
      <HistoryPreview
        history={[
          { date: '2017-01-01', store_id: '1', product_id: 'A' },
          { date: '2017-01-02', store_id: '1', product_id: 'A' },
          {}, // fila en blanco recién agregada → NO debe sumar
        ]}
      />,
    )
    const t = texto(container as unknown as HTMLElement)
    expect(t).toMatch(/Filas:\s*2/)
    expect(t).not.toMatch(/Filas:\s*3/)
  })

  it('con solo filas en blanco muestra cero', () => {
    const { container } = render(<HistoryPreview history={[{}, {}]} />)
    expect(texto(container as unknown as HTMLElement)).toMatch(/Filas:\s*0/)
  })
})
