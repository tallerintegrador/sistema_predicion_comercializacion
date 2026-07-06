/**
 * Tabla con buscador y "mostrar más".
 * Reutilizable en cualquier vista que necesite mostrar datos en tabla.
 */
import { useMemo, useState } from 'react'
import type { AutoRow } from '../../api/types'

const NUM = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 })

interface TablaInteractivaProps {
  rows: AutoRow[]
  columns: string[]
  buscarPlaceholder?: string
  inicial?: number
}

export function TablaInteractiva({
  rows,
  columns,
  buscarPlaceholder = 'Buscar…',
  inicial = 8,
}: TablaInteractivaProps) {
  const [q, setQ] = useState('')
  const [limite, setLimite] = useState(inicial)

  const filtradas = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return rows
    return rows.filter((r) =>
      columns.some((c) => String(r[c] ?? '').toLowerCase().includes(t)),
    )
  }, [rows, columns, q])

  const visibles = filtradas.slice(0, limite)
  // A10: el buscador solo aporta cuando hay muchas filas; con pocas (p. ej. categorías) estorba.
  const buscable = rows.length > 6

  return (
    <div className="space-y-2">
      {buscable && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setLimite(inicial)
            }}
            placeholder={buscarPlaceholder}
            className="w-full max-w-xs rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:border-slate-400 focus:outline-none"
          />
          <span className="text-xs text-slate-400">
            {filtradas.length === rows.length
              ? `${rows.length} filas`
              : `${filtradas.length} de ${rows.length}`}
          </span>
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
              {columns.map((c) => (
                <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibles.map((r, i) => (
              <tr key={i} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                {columns.map((c) => (
                  <td key={c} className="whitespace-nowrap px-3 py-2 text-slate-700">
                    {typeof r[c] === 'number'
                      ? NUM.format(r[c] as number)
                      : String(r[c] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
            {visibles.length === 0 && (
              <tr>
                <td
                  className="px-3 py-3 text-sm text-slate-400"
                  colSpan={columns.length}
                >
                  Sin resultados para «{q}».
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {filtradas.length > limite && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => setLimite((l) => l + 20)}
          >
            Mostrar más
          </button>
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => setLimite(filtradas.length)}
          >
            Mostrar todo ({filtradas.length})
          </button>
        </div>
      )}
    </div>
  )
}
