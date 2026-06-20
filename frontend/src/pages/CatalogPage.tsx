import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getCatalog } from '../api/endpoints'
import type { Availability, CatalogResponse, DomainCatalog } from '../api/types'
import { ErrorPanel } from '../components/ErrorPanel'

export function CatalogPage() {
  const [data, setData] = useState<CatalogResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    getCatalog()
      .then((c) => alive && setData(c))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e : new ApiError(0, 'network', 'No se pudo cargar el catálogo.')),
      )
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <p className="text-sm text-slate-500">Cargando catálogo…</p>
  if (error) return <ErrorPanel error={error} />
  if (!data) return null

  return (
    <div className="space-y-5">
      <section className="card">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Catálogo de predicciones</h2>
          <span className="badge bg-indigo-100 text-indigo-800">contrato v{data.contract_version}</span>
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Menú derivado de los esquemas reales de la API: lo disponible hoy vs. lo planificado.
        </p>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <AvailabilityList title="Canales" items={data.channels} />
          <AvailabilityList title="Modos" items={data.modes} />
        </div>
      </section>

      {data.domains.map((d) => (
        <DomainCard key={d.domain} domain={d} />
      ))}
    </div>
  )
}

function statusBadge(status: Availability['status']) {
  return status === 'available'
    ? 'bg-emerald-100 text-emerald-800'
    : 'bg-amber-100 text-amber-800'
}

function AvailabilityList({ title, items }: { title: string; items: Availability[] }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-700">{title}</h3>
      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.name} className="rounded-lg border border-slate-200 p-2">
            <div className="flex items-center gap-2">
              <code className="text-sm font-medium text-slate-800">{it.name}</code>
              <span className={`badge ${statusBadge(it.status)}`}>{it.status}</span>
            </div>
            <p className="mt-1 text-xs text-slate-500">{it.description}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DomainCard({ domain }: { domain: DomainCatalog }) {
  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-800 capitalize">{domain.domain}</h3>
        <code className="badge bg-slate-100 text-slate-600">{domain.endpoint}</code>
        {!domain.has_model && <span className="badge bg-slate-100 text-slate-500">sin modelo propio</span>}
      </div>
      <p className="mt-1 text-sm text-slate-600">{domain.summary}</p>
      <p className="mt-1 text-xs text-slate-500">{domain.description}</p>

      <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Entradas</h4>
          <ul className="space-y-1 text-sm">
            {domain.inputs.map((i) => (
              <li key={i.name} className="flex items-baseline gap-2">
                <code className="text-slate-800">{i.name}</code>
                <span className="text-xs text-slate-400">{i.type}</span>
                {i.required && <span className="badge bg-red-50 text-red-600">requerido</span>}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Salidas</h4>
          {domain.outputs.map((g) => (
            <div key={g.group} className="mb-2">
              <div className="text-xs font-medium text-slate-600">
                {g.group}
                {g.container && <span className="text-slate-400"> · {g.container}</span>}
              </div>
              <div className="flex flex-wrap gap-1">
                {g.fields.map((f) => (
                  <code key={f.name} className="badge bg-slate-100 text-slate-600" title={f.description ?? ''}>
                    {f.name}
                  </code>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {domain.notes.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-slate-500">
          {domain.notes.map((n, i) => (
            <li key={i}>• {n}</li>
          ))}
        </ul>
      )}
      {domain.pending_policy.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-amber-700">
          {domain.pending_policy.map((n, i) => (
            <li key={i}>⚠ {n}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
