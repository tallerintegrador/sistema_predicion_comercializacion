import { useMemo, useState } from 'react'
import { postSales, uploadExcel } from '../api/endpoints'
import type {
  ForecastItem,
  Granularity,
  HistoryItem,
  SalesRequest,
  SalesResponse,
} from '../api/types'
import { sampleSales } from '../data/samples'
import { usePrediction } from '../hooks/usePrediction'
import { useForecastOptions } from '../hooks/useForecastOptions'
import { ErrorPanel } from '../components/ErrorPanel'
import { ExcelPanel } from '../components/ExcelPanel'
import { HistoryPreview } from '../components/HistoryPreview'
import { JobBanner } from '../components/JobBanner'
import { MetadataPanel } from '../components/MetadataPanel'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { SalesChart } from '../components/charts/SalesChart'
import { TypologySelect } from '../components/forecast/TypologySelect'
import { DimensionSelect } from '../components/forecast/DimensionSelect'
import { DimensionValuesFilter } from '../components/forecast/DimensionValuesFilter'
import { fmtNum } from '../utils/format'

// Solo se desglosa/filtra por columnas identificadoras del histórico (R2).
type DimKey = 'store_id' | 'product_id'

export function SalesPage() {
  const { options, loading: optsLoading, error: optsError } = useForecastOptions('sales')

  // Configuración del pronóstico. Se guarda como "override" del usuario (null = usar el
  // valor por defecto del catálogo); el valor EFECTIVO se calcula con fallback más abajo.
  // Así no se hardcodea ninguna opción ni hace falta sincronizar estado con un efecto.
  const [typology, setTypology] = useState<string | null>(null)
  const [dimension, setDimension] = useState<string | null>(null)
  const [granularity, setGranularity] = useState<Granularity | null>(null)
  const [horizon, setHorizon] = useState<number | null>(null)
  const [selectedValues, setSelectedValues] = useState<string[]>([])

  // Histórico cargado en el cliente (vía ejemplo). El canal Excel predice en el servidor.
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [shownHistory, setShownHistory] = useState<HistoryItem[]>([])

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

  // Al cambiar la columna de desglose, la selección de valores deja de aplicar.
  const changeDimension = (name: string) => {
    setDimension(name)
    setSelectedValues([])
  }

  const dimLabel = (name: string) =>
    options?.dimensions.find((d) => d.name === name)?.label ?? name

  // Valores concretos de la dimensión, tomados del histórico REAL (no del catálogo).
  const dimensionValues = useMemo(() => {
    if (!effDimension) return []
    return Array.from(new Set(history.map((h) => String(h[dimKey])))).sort()
  }, [history, dimKey, effDimension])

  const hasHistory = history.length > 0

  const loadSample = () => {
    setHistory(sampleSales.history)
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
    const req: SalesRequest = {
      granularity: effGranularity,
      horizon: effHorizon,
      history: used,
    }
    pred.run(() => postSales(req))
  }

  const onExcel = (file: File) => {
    setShownHistory([])
    pred.run(() => uploadExcel<SalesResponse>('sales', file))
  }

  return (
    <div className="space-y-5">
      <section className="card">
        <h2 className="text-xl font-semibold text-slate-900">Ventas</h2>
        <p className="mt-1 text-sm text-slate-500">
          Pronóstico de demanda por período, tienda y producto a partir del histórico de ventas.
        </p>
      </section>

      <section className="card space-y-5" aria-labelledby="config-title">
        <h3 id="config-title" className="text-base font-semibold text-slate-800">
          Configuración del pronóstico
        </h3>

        {optsLoading && <p className="text-sm text-slate-500">Cargando opciones del catálogo…</p>}
        {optsError && <ErrorPanel error={optsError} />}

        {options && (
          <>
            {/* 1 · Tipo de pronóstico (R1) */}
            <TypologySelect
              typologies={options.typologies}
              value={effTypology}
              onChange={setTypology}
              disabled={busy}
            />

            {/* 2 · Dimensión / Filtrar por (R2) — solo si la tipología lo requiere */}
            {requiresDimension && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <DimensionSelect
                  dimensions={options.dimensions}
                  value={effDimension}
                  onChange={changeDimension}
                  disabled={busy}
                />
                <DimensionValuesFilter
                  label={`Valores de ${dimLabel(effDimension)}`}
                  values={dimensionValues}
                  selected={selectedValues}
                  onChange={setSelectedValues}
                  disabled={busy || !hasHistory}
                />
              </div>
            )}

            {/* 3 · Granularidad y Horizonte */}
            <div className="flex flex-wrap items-start gap-4">
              <div>
                <label className="label" htmlFor="granularity">
                  Granularidad
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
              </div>
              <div>
                <label className="label" htmlFor="horizon">
                  Horizonte ({options.horizon.min}–{options.horizon.max})
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
                <p className="help">Períodos de la granularidad elegida.</p>
              </div>
            </div>

            {/* 4 · Acciones */}
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="btn-ghost" onClick={loadSample} disabled={busy}>
                Cargar ejemplo
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={predict}
                disabled={busy || !hasHistory}
              >
                {busy ? 'Procesando…' : 'Predecir'}
              </button>
              {!hasHistory && (
                <span className="text-sm text-slate-500" role="status">
                  Cargue el ejemplo o suba un Excel para habilitar el pronóstico.
                </span>
              )}
            </div>

            <div className="border-t border-slate-200 pt-4">
              <HistoryPreview history={history} />
            </div>
          </>
        )}
      </section>

      <ExcelPanel domain="sales" onUpload={onExcel} busy={busy} />

      <JobBanner status={pred.status} jobId={pred.jobId} attempts={pred.attempts} />
      {pred.status === 'error' && pred.error && <ErrorPanel error={pred.error} />}

      {pred.status === 'done' && pred.data && (
        <ResultSection
          data={pred.data}
          history={shownHistory}
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
  typologyLabel,
  byDimension,
  dimKey,
  dimLabel,
}: {
  data: SalesResponse
  history: HistoryItem[]
  typologyLabel: string | null
  byDimension: boolean
  dimKey: DimKey
  dimLabel: (name: string) => string
}) {
  const forecast = data.forecast
  const otherKey: DimKey = dimKey === 'store_id' ? 'product_id' : 'store_id'

  // Serie temporal: demanda total por período (agregando todas las series).
  const periodTotals = useMemo(() => {
    const m = new Map<string, number>()
    for (const f of forecast) m.set(f.date, (m.get(f.date) ?? 0) + f.forecast_demand)
    return Array.from(m, ([date, total]) => ({ date, total })).sort((a, b) =>
      a.date.localeCompare(b.date),
    )
  }, [forecast])

  // Por dimensión: ordenado por la columna elegida y luego por fecha.
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
    { header: 'Pronóstico total', align: 'right', render: (r) => fmtNum(r.total) },
  ]
  const dimensionCols: Column<ForecastItem>[] = [
    { header: 'Fecha', render: (r) => r.date },
    { header: dimLabel(dimKey), render: (r) => String(r[dimKey]) },
    { header: dimLabel(otherKey), render: (r) => String(r[otherKey]) },
    { header: 'Pronóstico', align: 'right', render: (r) => fmtNum(r.forecast_demand) },
  ]

  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
        {typologyLabel && <span className="badge bg-brand-50 text-brand-700">{typologyLabel}</span>}
        <span className="badge bg-slate-100 text-slate-600">
          modelo <code className="ml-1">{data.model}</code>
        </span>
      </div>

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

      <MetadataPanel
        entries={[
          { label: 'model', value: data.model },
          { label: 'scale', value: data.metadata.scale },
          { label: 'internal_transform', value: data.metadata.internal_transform },
        ]}
        notes={[
          'interval_80: no disponible (diferido) — el modelo aún no produce intervalos de predicción.',
        ]}
      />
    </section>
  )
}
