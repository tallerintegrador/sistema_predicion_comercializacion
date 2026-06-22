import { useMemo, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import { postSales, uploadExcel } from '../api/endpoints'
import type {
  ForecastItem,
  Granularity,
  HistoryItem,
  QueryOptions,
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
import { StepSection } from '../components/ui/StepSection'
import { EmptyState } from '../components/ui/EmptyState'
import { ComingSoon } from '../components/ui/ComingSoon'
import { ResultSummary } from '../components/ui/ResultSummary'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { resumenVentas } from '../utils/resumen'
import {
  contarSeries,
  filasPorDimension,
  filtrarPorValores,
  totalesPorPeriodo,
  valoresDimension,
} from '../utils/ventasResult'
import type { DimKey } from '../utils/ventasResult'

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

  // Configuración del pronóstico: lo único que el modelo necesita para calcular.
  // (override del usuario; null = valor por defecto del catálogo).
  const [granularity, setGranularity] = useState<Granularity | null>(null)
  const [horizon, setHorizon] = useState<number | null>(null)

  const [history, setHistory] = useState<HistoryItem[]>([])
  const [shownHistory, setShownHistory] = useState<HistoryItem[]>([])
  const [jsonError, setJsonError] = useState<string | null>(null)

  const pred = usePrediction<SalesResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  // Valores efectivos: el override del usuario o el valor por defecto del catálogo.
  const effGranularity: Granularity = granularity ?? options?.granularities[0]?.name ?? 'day'
  const effHorizon = horizon ?? options?.horizon.default ?? 1

  const hasHistory = history.length > 0

  const onJson = (data: unknown) => {
    const hist = extraerHistorial(data)
    if (!hist) {
      setJsonError('El JSON no contiene un historial de ventas válido. Usa la plantilla como guía.')
      return
    }
    setJsonError(null)
    setHistory(hist)
    pred.reset()
  }

  const predict = () => {
    setShownHistory(history)
    const req: SalesRequest = { granularity: effGranularity, horizon: effHorizon, history }
    pred.run(() => postSales(req))
  }

  const onExcel = (file: File) => {
    // El archivo es solo datos: la configuración de pantalla viaja como campos de
    // formulario (única fuente del pronóstico, ADR-0022).
    setShownHistory([])
    pred.run(() =>
      uploadExcel<SalesResponse>('sales', file, { granularity: effGranularity, horizon: effHorizon }),
    )
  }

  return (
    <div className="space-y-5">
      <ModuleHeader view="sales" />

      {/* PASO 1 — Tus datos: cómo aportarlos y un resumen de lo cargado. */}
      <StepSection
        step={1}
        title="Tus datos"
        accentChip={ACCENT.chip}
        description="Empieza por aquí: sube tus ventas pasadas en Excel o JSON, o descarga la plantilla Excel para completarla."
      >
        <DataSourcePanel domain="sales" onExcel={onExcel} onJson={onJson} busy={busy} accentSolid={ACCENT.solid} />
        {jsonError && (
          <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
            {jsonError}
          </p>
        )}
        {hasHistory && (
          <div>
            <p className="label">Resumen de tus datos</p>
            <HistoryPreview history={history} />
          </div>
        )}
      </StepSection>

      {/* PASO 2 — Configuración: SOLO lo que el modelo necesita para calcular. */}
      <StepSection
        step={2}
        title="Configuración del pronóstico"
        accentChip={ACCENT.chip}
        description="Define cada cuánto y hasta cuándo estimar. Se aplica sobre los datos del Paso 1."
      >
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Qué estimar, cada cuánto y hasta cuándo lo eliges aquí en pantalla: esta configuración es
          la única que se aplica, también cuando subes un Excel. Después de pronosticar podrás
          explorar el resultado por tienda, producto o valores concretos sin recalcular.
        </div>

        {optsLoading && <p className="text-sm text-slate-500">Cargando opciones…</p>}
        {optsError && <ErrorPanel error={optsError} />}

        {options && (
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
              <p className="help">
                Se cuenta en períodos de la granularidad elegida (p. ej. 7 días, 7 semanas o 7 meses).
              </p>
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
        )}
      </StepSection>

      {/* PASO 3 — Acción: pronosticar con la configuración, habilitado solo si hay datos. */}
      <StepSection
        step={3}
        title="Pronostica y revisa el resultado"
        accentChip={ACCENT.chip}
        description="Cuando tengas tus datos y la configuración lista, calcula el pronóstico."
      >
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`btn ${ACCENT.solid}`} onClick={predict} disabled={busy || !hasHistory}>
            {busy ? 'Calculando…' : 'Pronosticar'}
          </button>
          {!hasHistory && (
            <span className="text-sm text-slate-500" role="status">
              Sube tus ventas (Excel o JSON) para pronosticar con esta configuración.
            </span>
          )}
        </div>
      </StepSection>

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
        <ResultSection data={pred.data} history={shownHistory} granularity={effGranularity} options={options} />
      )}
    </div>
  )
}

/**
 * Resultado del pronóstico con FILTROS SOBRE EL RESULTADO (mismo principio que Compras y
 * Almacén): el usuario pronostica una vez y explora el mismo resultado de varias formas
 * sin recalcular. «Ver total / por dimensión», «Agrupar / filtrar por» y «Valores concretos»
 * cambian la vista, no el cálculo; sus valores salen de las filas reales de la respuesta
 * (sirven para cualquier canal, también Excel).
 */
function ResultSection({
  data,
  history,
  granularity,
  options,
}: {
  data: SalesResponse
  history: HistoryItem[]
  granularity: Granularity
  options: QueryOptions | null
}) {
  // Estado de los filtros del resultado (se reinicia con cada pronóstico).
  const [typology, setTypology] = useState<string | null>(null)
  const [dimension, setDimension] = useState<string | null>(null)
  const [selectedValues, setSelectedValues] = useState<string[]>([])

  const effTypology = typology ?? options?.typologies[0]?.name ?? 'time_series'
  const effDimension = dimension ?? options?.dimensions[0]?.name ?? 'product_id'
  const currentTypology = options?.typologies.find((t) => t.name === effTypology) ?? null
  const byDimension = currentTypology?.requires_dimension ?? false
  const dimKey = (effDimension || 'product_id') as DimKey
  const otherKey: DimKey = dimKey === 'store_id' ? 'product_id' : 'store_id'

  const dimLabel = (name: string) => options?.dimensions.find((d) => d.name === name)?.label ?? name
  const changeDimension = (name: string) => {
    setDimension(name)
    setSelectedValues([])
  }

  const forecast = data.forecast

  // Valores concretos: derivados de las filas del RESULTADO (no del histórico), así el
  // filtro funciona también cuando los datos se subieron por Excel.
  const dimensionValues = useMemo(() => valoresDimension(forecast, dimKey), [forecast, dimKey])

  // El filtro por valores concretos solo aplica en la vista «por dimensión». Una selección
  // vacía significa «todas». `activeKey` mantiene estable la dependencia de los useMemo.
  const activeValues = byDimension ? selectedValues : []
  const activeKey = activeValues.join('|')

  const filteredForecast = useMemo(
    () => filtrarPorValores(forecast, dimKey, activeValues),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [forecast, dimKey, activeKey],
  )
  const filteredHistory = useMemo(
    () => filtrarPorValores(history, dimKey, activeValues),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [history, dimKey, activeKey],
  )

  const periodTotals = useMemo(() => totalesPorPeriodo(filteredForecast), [filteredForecast])
  const dimensionRows = useMemo(() => filasPorDimension(filteredForecast, dimKey), [filteredForecast, dimKey])

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

  const filteredSeries = contarSeries(filteredForecast)
  const totalSeries = contarSeries(forecast)

  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
        {currentTypology && <span className={`badge ${ACCENT.badge}`}>{currentTypology.label}</span>}
      </div>

      {/* Filtros sobre el resultado: cambian la vista, no el cálculo. */}
      {options && (
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
          <TypologySelect
            typologies={options.typologies}
            value={effTypology}
            onChange={setTypology}
            label="Ver"
          />
          {byDimension && (
            <>
              <DimensionSelect
                dimensions={options.dimensions}
                value={effDimension}
                onChange={changeDimension}
                label="Agrupar / filtrar por"
              />
              <DimensionValuesFilter
                label={`Valores de ${dimLabel(effDimension)}`}
                values={dimensionValues}
                selected={selectedValues}
                onChange={setSelectedValues}
              />
            </>
          )}
          <div className="opacity-60" title="Disponible cuando el sistema indique la categoría o familia de cada producto.">
            <span className="label flex items-center gap-1">
              Categoría / familia <ComingSoon />
            </span>
            <select className="input" disabled aria-disabled="true">
              <option>Todas</option>
            </select>
          </div>
        </div>
      )}

      <ResultSummary text={resumenVentas(filteredForecast, granularity)} tone="bg-sales-50 text-sales-700" />

      {byDimension && filteredSeries !== totalSeries && (
        <p className="text-xs text-slate-500">
          Mostrando {filteredSeries} de {totalSeries} series.
        </p>
      )}

      <SalesChart history={filteredHistory} forecast={filteredForecast} />

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
