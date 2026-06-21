import { Plus, Trash2 } from 'lucide-react'
import type { CatalogColumn, InputTable } from '../api/types'
import type { EditableRow } from '../utils/tableData'
import { emptyRow } from '../utils/tableData'

/**
 * Tabla editable de carga manual (ADR-0020), **dirigida por el catálogo**: las columnas,
 * sus etiquetas en español y sus tipos salen de `GET /catalog` (no se hardcodean). Permite
 * "Agregar fila" como opción amigable para pocos productos en Compras y Almacén.
 */
export function CatalogTable({
  table,
  rows,
  onChange,
  disabled = false,
}: {
  table: InputTable
  rows: EditableRow[]
  onChange: (rows: EditableRow[]) => void
  disabled?: boolean
}) {
  const setCell = (i: number, name: string, value: string) => {
    const next = rows.map((r, idx) => (idx === i ? { ...r, [name]: value } : r))
    onChange(next)
  }
  const addRow = () => onChange([...rows, emptyRow(table)])
  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold text-slate-700">{table.label}</h4>
          {table.description && <p className="help mt-0">{table.description}</p>}
        </div>
        <button type="button" className="btn-ghost text-xs" onClick={addRow} disabled={disabled}>
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          Agregar fila
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50/60 px-3 py-4 text-center text-xs text-slate-500">
          Sin filas. Usa «Agregar fila» para cargar tus productos a mano, o sube un archivo.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr>
                {table.columns.map((c) => (
                  <th key={c.name} className="th" title={c.help ?? undefined}>
                    {c.label}
                    {c.required && <span className="text-red-500"> *</span>}
                  </th>
                ))}
                <th className="th" aria-label="Acciones" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-slate-100">
                  {table.columns.map((c) => (
                    <td key={c.name} className="px-2 py-1">
                      <Cell column={c} value={row[c.name] ?? ''} onChange={(v) => setCell(i, c.name, v)} disabled={disabled} />
                    </td>
                  ))}
                  <td className="px-2 py-1 text-right">
                    <button
                      type="button"
                      className="rounded p-1 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 disabled:opacity-50"
                      onClick={() => removeRow(i)}
                      disabled={disabled}
                      aria-label={`Eliminar fila ${i + 1}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/** Editor de una celda según el tipo declarado por la columna del contrato. */
function Cell({
  column,
  value,
  onChange,
  disabled,
}: {
  column: CatalogColumn
  value: string
  onChange: (v: string) => void
  disabled: boolean
}) {
  const common = 'input py-1 text-sm'
  if (column.type === 'bool') {
    return (
      <select className={`${common} min-w-[6rem]`} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        <option value="">—</option>
        <option value="true">Sí</option>
        <option value="false">No</option>
      </select>
    )
  }
  const type = column.type === 'date' ? 'date' : column.type === 'int' || column.type === 'float' ? 'number' : 'text'
  return (
    <input
      className={`${common} ${type === 'number' ? 'w-28' : type === 'date' ? 'w-40' : 'min-w-[8rem]'}`}
      type={type}
      step={column.type === 'int' ? '1' : column.type === 'float' ? 'any' : undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      aria-label={column.label}
    />
  )
}
