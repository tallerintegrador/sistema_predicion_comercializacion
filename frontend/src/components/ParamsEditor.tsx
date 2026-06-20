/**
 * Editor genérico de filas de parámetros (replenishment_params / inventory_status).
 * Cada fila es un objeto plano; los campos se declaran en `fields`. Mantiene el
 * tipado del contrato y permite agregar/quitar filas.
 */
export interface FieldDef<T> {
  key: keyof T & string
  label: string
  type: 'text' | 'number'
  optional?: boolean
}

export function ParamsEditor<T extends object>({
  title,
  rows,
  fields,
  makeEmpty,
  onChange,
}: {
  title: string
  rows: T[]
  fields: FieldDef<T>[]
  makeEmpty: () => T
  onChange: (rows: T[]) => void
}) {
  const update = (index: number, key: keyof T & string, raw: string, type: 'text' | 'number', optional?: boolean) => {
    const next = rows.slice()
    let value: unknown = raw
    if (type === 'number') {
      value = raw === '' ? (optional ? null : 0) : Number(raw)
    }
    next[index] = { ...next[index], [key]: value } as T
    onChange(next)
  }

  const addRow = () => onChange([...rows, makeEmpty()])
  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
        <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={addRow}>
          + Agregar fila
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {fields.map((f) => (
                <th key={f.key} className="th">
                  {f.label}
                  {f.optional && <span className="ml-1 font-normal normal-case text-slate-400">(opc.)</span>}
                </th>
              ))}
              <th className="th" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, ri) => (
              <tr key={ri}>
                {fields.map((f) => {
                  const v = row[f.key]
                  return (
                    <td key={f.key} className="px-2 py-1">
                      <input
                        className="input py-1"
                        type={f.type}
                        value={v == null ? '' : String(v)}
                        onChange={(e) => update(ri, f.key, e.target.value, f.type, f.optional)}
                      />
                    </td>
                  )
                })}
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    className="text-xs text-red-600 hover:underline"
                    onClick={() => removeRow(ri)}
                    aria-label="Quitar fila"
                  >
                    Quitar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
