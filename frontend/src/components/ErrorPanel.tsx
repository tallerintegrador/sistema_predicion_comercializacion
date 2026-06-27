import type { ApiError } from '../api/client'

/** Muestra el error uniforme del contrato: tipo, mensaje y detalles por campo. */
export function ErrorPanel({ error }: { error: ApiError }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
      <div className="flex items-center gap-2 font-semibold text-red-800">
        <span className="badge bg-red-200 text-red-900">{error.type}</span>
        {error.status > 0 && <span className="text-red-700">HTTP {error.status}</span>}
      </div>
      <p className="mt-1 text-red-800">{error.message}</p>
      {error.details.length > 0 && (
        <ul className="mt-2 list-inside list-disc space-y-1 text-red-700">
          {error.details.map((d, i) => (
            <li key={i}>
              <code className="rounded bg-red-100 px-1 py-0.5 text-xs">{d.field}</code> — {d.problem}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
