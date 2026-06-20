import type { ReactNode } from 'react'

export interface MetaEntry {
  label: string
  value: ReactNode
}

/**
 * Panel de metadata de la respuesta + notas honestas (p. ej. campos diferidos).
 * Las notas se pintan tal cual las entrega el backend; no se inventan valores.
 */
export function MetadataPanel({ entries, notes }: { entries: MetaEntry[]; notes?: string[] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">Metadata</h3>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {entries.map((e, i) => (
          <div key={i} className="flex justify-between gap-2 border-b border-slate-200 pb-1 text-sm">
            <dt className="text-slate-500">{e.label}</dt>
            <dd className="text-right font-medium text-slate-800">{e.value}</dd>
          </div>
        ))}
      </dl>
      {notes && notes.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-slate-500">
          {notes.map((n, i) => (
            <li key={i} className="flex gap-1.5">
              <span aria-hidden>ℹ️</span>
              <span>{n}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
