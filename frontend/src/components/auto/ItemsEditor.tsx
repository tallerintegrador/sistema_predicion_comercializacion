/**
 * Editor de **productos a reponer** para «Compras» (motor agnóstico, ADR-0023). Una fila por
 * serie (tienda × producto) con: claves de serie (texto) + stock actual, días de entrega y
 * días de cobertura (números). El motor usa estos campos para calcular punto de reorden y
 * cantidad a reponer sobre el pronóstico de demanda.
 */
import type { AutoRow } from '../../api/types'
import { ITEM_COLS_COMPRAS } from './itemCols'
import type { NumCol } from './itemCols'

export function ItemsEditor({
  seriesKeys,
  items,
  onChange,
  numCols = ITEM_COLS_COMPRAS,
  disabled = false,
  accentBadge = 'bg-slate-100 text-slate-600',
}: {
  seriesKeys: string[]
  items: AutoRow[]
  onChange: (items: AutoRow[]) => void
  numCols?: NumCol[]
  disabled?: boolean
  accentBadge?: string
}) {
  const setCell = (i: number, key: string, value: string, numeric: boolean) => {
    const next = items.map((row, idx) =>
      idx === i ? { ...row, [key]: numeric ? (value === '' ? '' : Number(value)) : value } : row,
    )
    onChange(next)
  }

  const addRow = () => {
    const blank: AutoRow = {}
    for (const k of seriesKeys) blank[k] = ''
    for (const c of numCols) blank[c.key] = c.default
    onChange([...items, blank])
  }

  const removeRow = (i: number) => onChange(items.filter((_, idx) => idx !== i))

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase text-slate-400">
              {seriesKeys.map((k) => (
                <th key={k} className="py-1 pr-3 text-left font-medium">{k}</th>
              ))}
              {numCols.map((c) => (
                <th key={c.key} className="py-1 pr-3 text-right font-medium" title={c.help}>{c.label}</th>
              ))}
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {items.map((row, i) => (
              <tr key={i} className="border-t border-slate-100">
                {seriesKeys.map((k) => (
                  <td key={k} className="py-1 pr-3">
                    <input
                      className="input h-8 py-1"
                      value={String(row[k] ?? '')}
                      disabled={disabled}
                      onChange={(e) => setCell(i, k, e.target.value, false)}
                    />
                  </td>
                ))}
                {numCols.map((c) => (
                  <td key={c.key} className="py-1 pr-3 text-right">
                    <input
                      type="number"
                      className="input h-8 w-28 py-1 text-right"
                      value={row[c.key] == null ? '' : String(row[c.key])}
                      disabled={disabled}
                      onChange={(e) => setCell(i, c.key, e.target.value, true)}
                    />
                  </td>
                ))}
                <td className="py-1 text-right">
                  <button
                    type="button"
                    className="text-xs text-slate-400 hover:text-rose-600"
                    onClick={() => removeRow(i)}
                    disabled={disabled}
                  >
                    Quitar
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={seriesKeys.length + numCols.length + 1} className="py-3 text-center text-sm text-slate-400">
                  Sin productos. Usa «Generar desde mis datos» o «Agregar fila».
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <button type="button" className={`badge ${accentBadge}`} onClick={addRow} disabled={disabled}>
        + Agregar fila
      </button>
    </div>
  )
}
