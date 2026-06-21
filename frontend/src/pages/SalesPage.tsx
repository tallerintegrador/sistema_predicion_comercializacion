import { useMemo, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import { postSales, uploadExcel } from '../api/endpoints'
import type {
  ForecastItem,
  Granularity,
  HistoryItem,
  SalesRequest,
  SalesResponse,
} from '../api/types'
import { usePrediction } from '../hooks/usePrediction'
import { useDomainCatalog } from '../hooks/useDomainCatalog'
import { ErrorPanel } from '../components/ErrorPanel'
import { DataSourcePanel } from '../components/DataSourcePanel'
import { HistoryPreview } from '../components/HistoryPreview'
import { JobBanner } from '../components/JobBanner'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { SalesChart } from '../components/charts/SalesChart'
import { TypologySelect } from '../components/forecast/TypologySelect'
import { DimensionSelect } from '../components/forecast/DimensionSelect'
import { DimensionValuesFilter } from '../components/forecast/DimensionValuesFilter'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { ComingSoon } from '../components/ui/ComingSoon'
import { ResultSummary } from '../components/ui/ResultSummary'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { resumenVentas } from '../utils/resumen'

// Solo se desglosa/filtra por columnas identificadoras del histórico (R2).
type DimKey = 'store_id' | 'product_id'

const ACCENT = SECTION_BY_ID.sales.accent

/** Extrae el bloque de ventas pasadas de un JSON (array directo u objeto con `history`). */
function extraerHistorial(data: unknown): HistoryItem[] | null {
  if (Array.isArray(data)) return data as HistoryItem[]
  if (data && typeof data === 'object' && Array.isArray((data as { history?: unknown }).history)) {
    return (data as { history: HistoryItem[] }).history
  }
  return null
}

export function SalesPage() {
  const { domain, loading: optsLoading, error: optsError } = useDomainCatalog('sales')
  const options = domain?.query_options ?? null

  // Configuración del pronóstico (override del usuario; null = valor por defecto del catálogo).
  const [typology, setTypology] = useState<string | null>(null)
  const [dimension, setDimension] = useState<string | null>(null)
  const [granularity, setGranularity] = useState<Granularity | null>(null)
  const [horizon, setHorizon] = useState<number | null>(null)
  const [selectedValues, setSelectedValues] = useState<string[]>([])

  const [history, setHistory] = useState<HistoryItem[]>([])
  const [shownHistory, setShownHistory] = useState<HistoryItem[]>([])
  const [jsonError, setJsonError] = useState<string | null>(null)

  const pred = usePrediction<SalesResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  // Valores efectivos: el override del usuario o el valor por defecto del catálogo.
  const effTypology = typology ?? options?.typologies[0]?.name ?? ''
  const effDimension = dimension ?? options?.dimensions[0]?.name ?? ''
  const effGranularity: Granularity = granularity ?? options?.granularities[0]?.name ?? 'day'
  const effHorizon = horizon ?? options?.horizon.default ?? 1

  const currentTypology = options?.typologies.find((t) => t.name === effTypology) ?? null
  const requiresDimension = currentTypology?.requires_dimension ?? false
  const dimKey = (effDimension || 'product_id') as DimKey

  const changeDimension = (name: string) => {
    setDimension(name)
    setSelectedValues([])
  }
  const dimLabel = (name: string) => options?.dimensions.find((d) => d.name === name)?.label ?? name

  const dimensionValues = useMemo(() => {
    if (!effDimension) return []
    return Array.from(new Set(history.map((h) => String(h[dimKey])))).sort()
  }, [history, dimKey, effDimension])

  const hasHistory = history.length > 0

  const onJson = (data: unknown) => {
    const hist = extraerHistorial(data)
    if (!hist) {
      setJsonError('El JSON no contiene un historial de ventas válido. Usa la plantilla como guía.')
      return
    }
    setJsonError(null)
    setHistory(hist)
    setSelectedValues([])
    pred.reset()
  }

  const buildHistory = (): HistoryItem[] => {
    if (!requiresDimension || selectedValues.length === 0) return history
    return history.filter((h) => selectedValues.includes(String(h[dimKey])))
  }

  const predict = () => {
    const used = buildHistory()
    setShownHistory(used)
    const req: SalesRequest = { granularity: effGranularity, horizon: effHorizon, history: used }
    pred.run(() => postSales(req))
  }

  const onExcel = (file: File) => {
    setShownHistory([])
    pred.run(() => uploadExcel<SalesResponse>('sales', file))
  }

  return (
    <div className="space-y-5">
      <ModuleHeader view="sales" />

      <section className="card space-y-5" aria-labelledby="config-title">
        <h3 id="config-title" className="text-base font-semibold text-slate-800">
          Configuración del pronóstico
        </h3>

        {optsLoading && <p className="text-sm text-slate-500">Cargando opciones…</p>}
        {optsError && <ErrorPanel error={optsError} />}

        {options && (
          <>
            <TypologySelect
              typologies={options.typologies}
              value={effTypology}
              onChange={setTypology}
              disabled={busy}
            />

            {requiresDimension && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <DimensionSelect
                  dimensions={options.dimensions}
                  value={effDimension}
                  onChange={changeDimension}
                  disabled={busy}
                  label="Agrupar / filtrar por"
                />
                <DimensionValuesFilter
                  label={`Valores de ${dimLabel(effDimension)}`}
                  values={dimensionValues}
                  selected={selectedValues}
                  onChange={setSelectedValues}
                  disabled={busy || !hasHistory}
                  disabledHint="Sube tus ventas en JSON para elegir valores concretos. (Con Excel, esta opción llegará pronto)."
                />
              </div>
            )}

            <div className="flex flex-wrap items-start gap-4">
              <div>
                <label className="label" htmlFor="granularity">
                  ¿Cada cuánto?
                </label>
                <select
                  id="granularity"
                  className="input"
                  value={effGranularity}
                  disabled={busy}
                  onChange={(e) => setGranularity(e.target.value as Granularity)}
                >
                  {options.granularities.map((g) => (
                    <option key={g.name} value={g.name}>
                      {g.label}
                    </option>
                  ))}
                </select>
                <p className="help">Día, semana o mes.</p>
              </div>
              <div>
                <label className="label" htmlFor="horizon">
                  ¿Hasta cuándo? ({options.horizon.min}–{options.horizon.max})
                </label>
                <input
                  id="horizon"
                  type="number"
                  min={options.horizon.min}
                  max={options.horizon.max}
                  className="input w-32"
                  value={effHorizon}
                  disabled={busy}
                  onChange={(e) => {
                    const n = Number(e.target.value)
                    const { min, max } = options.horizon
                    setHorizon(Number.isNaN(n) ? min : Math.min(Math.max(n, min), max))
                  }}
                />
                <p className="help">Cuántos períodos quieres estimar.</p>
              </div>
              <div className="opacity-60">
                <span className="label flex items-center gap-2">
                  Rango estimado (80%) <ComingSoon />
                </span>
                <label className="mt-1 inline-flex items-center gap-2 text-sm text-slate-400">
                  <input type="checkbox" disabled />
                  Mostrar el margen alto/bajo
                </label>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4">
              <button type="button" className={`btn ${ACCENT.solid}`} onClick={predict} disabled={busy || !hasHistory}>
                {busy ? 'Calculando…' : 'Pronosticar'}
              </button>
              {!hasHistory && (
                <span className="text-sm text-slate-500" role="status">
                  Sube tus ventas (Excel o JSON) para pronosticar con esta configuración.
                </span>
              )}
              <HistoryPreview history={history} />
            </div>
          </>
        )}
      </section>

      <DataSourcePanel domain="sales" onExcel={onExcel} onJson={onJson} busy={busy} accentSolid={ACCENT.solid} />
      {jsonError && (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
          {jsonError}
        </p>
      )}
      <p className="text-xs text-slate-400">
        Al subir un Excel, el pronóstico usa la configuración incluida en el propio archivo.
      </p>

      <JobBanner status={pred.status} jobId={pred.jobId} attempts={pred.attempts} />
      {pred.status === 'error' && pred.error && <ErrorPanel error={pred.error} />}

      {pred.status === 'idle' && !busy && (
        <EmptyState
          icon={BarChart3}
          title="Aún no hay un pronóstico"
          message="Sube tus ventas pasadas y pulsa «Pronosticar». Verás un gráfico, una tabla descargable y un resumen claro."
        />
      )}

      {pred.status === 'done' && pred.data && (
        <ResultSection
          data={pred.data}
          history={shownHistory}
          granularity={effGranularity}
          typologyLabel={currentTypology?.label ?? null}
          byDimension={requiresDimension}
          dimKey={dimKey}
          dimLabel={dimLabel}
        />
      )}
    </div>
  )
}

/** Resultado del pronóstico, presentado según la tipología elegida (R1). */
function ResultSection({
  data,
  history,
  granularity,
  typologyLabel,
  byDimension,
  dimKey,
  dimLabel,
}: {
  data: SalesResponse
  history: HistoryItem[]
  granularity: Granularity
  typologyLabel: string | null
  byDimension: boolean
  dimKey: DimKey
  dimLabel: (name: string) => string
}) {
  const forecast = data.forecast
  const otherKey: DimKey = dimKey === 'store_id' ? 'product_id' : 'store_id'

  const periodTotals = useMemo(() => {
    const m = new Map<string, number>()
    for (const f of forecast) m.set(f.date, (m.get(f.date) ?? 0) + f.forecast_demand)
    return Array.from(m, ([date, total]) => ({ date, total })).sort((a, b) => a.date.localeCompare(b.date))
  }, [forecast])

  const dimensionRows = useMemo(
    () =>
      [...forecast].sort((a, b) => {
        const k = String(a[dimKey]).localeCompare(String(b[dimKey]))
        return k !== 0 ? k : a.date.localeCompare(b.date)
      }),
    [forecast, dimKey],
  )

  const periodCols: Column<{ date: string; total: number }>[] = [
    { header: 'Período', render: (r) => r.date },
    { header: 'Demanda estimada', align: 'right', render: (r) => fmtNum(r.total) },
  ]
  const dimensionCols: Column<ForecastItem>[] = [
    { header: 'Fecha', render: (r) => r.date },
    { header: dimLabel(dimKey), render: (r) => String(r[dimKey]) },
    { header: dimLabel(otherKey), render: (r) => String(r[otherKey]) },
    { header: 'Demanda estimada', align: 'right', render: (r) => fmtNum(r.forecast_demand) },
  ]

  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
        {typologyLabel && <span className={`badge ${ACCENT.badge}`}>{typologyLabel}</span>}
      </div>

      <ResultSummary text={resumenVentas(forecast, granularity)} tone="bg-sales-50 text-sales-700" />

      <SalesChart history={history} forecast={forecast} />

      {byDimension ? (
        <>
          <p className="text-sm text-slate-500">Desglose por {dimLabel(dimKey)}.</p>
          <ResultTable columns={dimensionCols} rows={dimensionRows} />
        </>
      ) : (
        <>
          <p className="text-sm text-slate-500">Demanda total por período.</p>
          <ResultTable columns={periodCols} rows={periodTotals} />
        </>
      )}

      <TechnicalDetails>
        <p>Modelo: <span className="font-mono text-slate-700">{data.model}</span></p>
        <p>Escala: {data.metadata.scale} · Transformación interna: {data.metadata.internal_transform}</p>
        <p>interval_80 (rango estimado al 80%): no disponible aún — el modelo todavía no produce intervalos de predicción.</p>
      </TechnicalDetails>
    </section>
  )
}
