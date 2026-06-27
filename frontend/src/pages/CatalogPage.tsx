import { useEffect, useState } from 'react'
import { CheckCircle2, FileSpreadsheet } from 'lucide-react'
import { ApiError } from '../api/client'
import { getCatalog } from '../api/endpoints'
import type { CatalogResponse, DomainCatalog } from '../api/types'
import { ErrorPanel } from '../components/ErrorPanel'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { SECTION_BY_ID, type View } from '../theme/modules'

/** Qué entrega cada módulo, en lenguaje claro (copy de producto, no datos del backend). */
const RECIBES: Record<string, string> = {
  sales: 'Cuánto venderás en cada período, por tienda y producto, con un gráfico y un resumen.',
  purchases: 'Cuánto y cuándo reponer cada producto, y el punto en que conviene volver a pedir.',
  inventory: 'Qué productos tienen riesgo de agotarse y el nivel de existencias sugerido.',
}

/**
 * "¿Qué hace el sistema?" (ADR-0020): reemplaza el volcado de esquemas por una vista
 * amigable. Explica cada módulo en lenguaje natural (qué datos pide, qué entrega). Lo
 * técnico (endpoints, campos, versión de contrato) queda en «Detalles técnicos».
 */
export function CatalogPage() {
  const [data, setData] = useState<CatalogResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    getCatalog()
      .then((c) => alive && setData(c))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e : new ApiError(0, 'network', 'No se pudo cargar la información.')),
      )
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <p className="text-sm text-slate-500">Cargando…</p>
  if (error) return <ErrorPanel error={error} />
  if (!data) return null

  return (
    <div className="space-y-5">
      <ModuleHeader view="catalog" />

      <section className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <FileSpreadsheet className="h-5 w-5 shrink-0 text-slate-400" aria-hidden="true" />
        <p className="text-sm text-slate-600">
          En todos los módulos puedes cargar tus datos en <strong>Excel</strong> o <strong>JSON</strong>, o
          descargar una <strong>plantilla</strong> para completarla. El sistema decide solo cómo procesarlos.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {data.domains.map((d) => (
          <FriendlyDomainCard key={d.domain} domain={d} />
        ))}
      </div>

      <TechnicalDetails title="Detalles técnicos (para desarrolladores)">
        <p>Versión del contrato de datos: <span className="font-mono text-slate-700">{data.contract_version}</span>.</p>
        {data.domains.map((d) => (
          <div key={d.domain} className="mt-2">
            <p className="font-mono text-slate-700">{d.endpoint}</p>
            <p>
              Entradas: {d.input_tables.map((t) => `${t.name} (${t.columns.map((c) => c.name).join(', ')})`).join(' · ')}
            </p>
            <p>
              Salidas: {d.outputs.map((g) => `${g.container ?? g.group}: ${g.fields.map((f) => f.name).join(', ')}`).join(' · ')}
            </p>
          </div>
        ))}
      </TechnicalDetails>
    </div>
  )
}

function FriendlyDomainCard({ domain }: { domain: DomainCatalog }) {
  const section = SECTION_BY_ID[domain.domain as View]
  const Icon = section?.icon
  const accent = section?.accent
  return (
    <section className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        {Icon && accent && (
          <span aria-hidden="true" className={`flex h-10 w-10 items-center justify-center rounded-xl ${accent.chip}`}>
            <Icon className="h-5 w-5" />
          </span>
        )}
        <h3 className="text-base font-semibold text-slate-800">{section?.label ?? domain.domain}</h3>
      </div>

      <p className="mt-3 text-sm leading-relaxed text-slate-600">{section?.blurb}</p>

      <div className="mt-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Qué datos necesita</p>
        <ul className="mt-1 space-y-1">
          {domain.input_tables.map((t) => (
            <li key={t.name} className="text-sm text-slate-600">
              • {t.label}
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4 flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" aria-hidden="true" />
        <p className="text-sm text-slate-600">{RECIBES[domain.domain] ?? domain.summary}</p>
      </div>
    </section>
  )
}
