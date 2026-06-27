import { useMemo, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import { ApiError } from '../api/client'
import { downloadAutoTemplate, postAutoSales, uploadAutoExcel } from '../api/endpoints'
import type { AutoRow, AutoSalesResponse, Granularity } from '../api/types'
import { useDomainCatalog } from '../hooks/useDomainCatalog'
import { ErrorPanel } from '../components/ErrorPanel'
import { ResultTable } from '../components/ResultTable'
import { SerieChart } from '../components/charts/SerieChart'
import { TrainingCard } from '../components/auto/TrainingCard'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { StepSection } from '../components/ui/StepSection'
import { EmptyState } from '../components/ui/EmptyState'
import { ResultSummary } from '../components/ui/ResultSummary'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { ComingSoon } from '../components/ui/ComingSoon'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { generarFilasDemo } from '../demo/retailDemo'
import { columnasDinamicas } from '../utils/autoColumns'
import {
  analizarColumnas,
  columnasNumericas,
  construirEsquema,
  normalizarFilas,
  sugerirFecha,
  sugerirSeries,
  sugerirTarget,
} from '../utils/inferSchema'
import type { ColumnInfo } from '../utils/inferSchema'

const ACCENT = SECTION_BY_ID.sales.accent

type Intencion = 'producto' | 'dinero' | 'otro'

const INTENCION_LABEL: Record<Intencion, string> = {
  producto: 'Unidades vendidas (producto)',
  dinero: 'Ingresos (dinero)',
  otro: 'Otra cantidad',
}

const PERIODO: Record<Granularity, [string, string]> = {
  day: ['día', 'días'],
  week: ['semana', 'semanas'],
  month: ['mes', 'meses'],
}

/** Extrae las filas de datos de un JSON (array directo, u objeto con `rows`/`history`). */
function extraerFilas(data: unknown): AutoRow[] | null {
  if (Array.isArray(data)) return data as AutoRow[]
  if (data && typeof data === 'object') {
    const o = data as { rows?: unknown; history?: unknown }
    if (Array.isArray(o.rows)) return o.rows as AutoRow[]
    if (Array.isArray(o.history)) return o.history as AutoRow[]
  }
  return null
}

/** Esquema por defecto (columnas del ejemplo): permite descargar una plantilla Excel en
 *  blanco SIN haber cargado datos antes. Si el usuario ya cargó datos, se usa el inferido. */
const DEFAULT_SCHEMA = construirEsquema({
  cols: analizarColumnas(generarFilasDemo()),
  target: 'unidades_vendidas',
  date: 'fecha',
  seriesKeys: ['tienda', 'sku'],
})

/** Resumen en lenguaje natural del pronóstico agnóstico (cualquier objetivo). */
function resumenAuto(forecast: AutoRow[], granularity: Granularity, target: string): string {
  if (forecast.length === 0) return 'No hay pronóstico para mostrar.'
  const total = forecast.reduce((a, f) => a + (Number(f.forecast_demand) || 0), 0)
  const periodos = new Set(forecast.map((f) => String(f.date))).size
  const [sing, plur] = PERIODO[granularity]
  return `Se estima un total de aproximadamente ${fmtNum(total)} de «${target}» en ${fmtNum(
    periodos,
  )} ${periodos === 1 ? sing : plur}.`
}

export function SalesPage() {
  const { domain, loading: optsLoading, error: optsError } = useDomainCatalog('sales')
  const options = domain?.query_options ?? null

  // PASO 1 — datos ricos (columnas libres) cargados por JSON o ejemplo.
  const [rows, setRows] = useState<AutoRow[]>([])
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  // PASO 2 — mapeo (override del usuario; null = sugerencia automática).
  const [intencion, setIntencion] = useState<Intencion>('producto')
  const [target, setTarget] = useState<string | null>(null)
  const [date, setDate] = useState<string | null>(null)
  const [series, setSeries] = useState<string[] | null>(null)
  const [granularity, setGranularity] = useState<Granularity | null>(null)
  const [horizon, setHorizon] = useState<number | null>(null)

  // PASO 3 — resultado.
  const [data, setData] = useState<AutoSalesResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [shownTarget, setShownTarget] = useState<string>('')

  const cols = useMemo<ColumnInfo[]>(() => analizarColumnas(rows), [rows])

  // Valores efectivos: el override del usuario o la sugerencia inferida de las columnas.
  const effDate = date ?? sugerirFecha(cols) ?? ''
  const effTarget =
    target ?? (intencion === 'otro' ? columnasNumericas(cols, [effDate])[0]?.name ?? '' : sugerirTarget(cols, intencion, [effDate]) ?? '')
  const effSeries = series ?? sugerirSeries(cols, [effDate, effTarget])
  const effGranularity: Granularity = granularity ?? options?.granularities[0]?.name ?? 'day'
  const effHorizon = horizon ?? options?.horizon.default ?? 7

  const hasRows = rows.length > 0
  const numericas = useMemo(() => columnasNumericas(cols, [effDate]), [cols, effDate])
  const puedePredecir = (hasRows || excelFile != null) && !!effTarget && !!effDate && !busy

  const resetMapeo = () => {
    setTarget(null)
    setDate(null)
    setSeries(null)
  }

  const cargarFilas = (nuevas: AutoRow[]) => {
    setRows(nuevas)
    setExcelFile(null)
    resetMapeo()
    setData(null)
    setError(null)
    setAviso(null)
  }

  const onJson = async (file: File) => {
    setAviso(null)
    try {
      const parsed = extraerFilas(JSON.parse(await file.text()))
      if (!parsed || parsed.length === 0) {
        setAviso('El JSON no contiene filas de datos. Usa un array de registros o un objeto con «rows».')
        return
      }
      cargarFilas(parsed)
    } catch {
      setAviso('El archivo no es un JSON válido. Revisa el formato.')
    }
  }

  const onExcel = (file: File) => {
    if (cols.length === 0) {
      setAviso(
        'Para Excel: primero carga un JSON o el ejemplo para configurar las columnas; el Excel debe traer esas mismas columnas.',
      )
      return
    }
    setExcelFile(file)
    setData(null)
    setError(null)
    setAviso(`Excel «${file.name}» listo: se enviará con la configuración actual al pronosticar.`)
  }

  const toggleSerie = (name: string) => {
    const base = effSeries
    const next = base.includes(name) ? base.filter((s) => s !== name) : [...base, name]
    setSeries(next)
  }

  const cambiarIntencion = (i: Intencion) => {
    setIntencion(i)
    setTarget(null) // re-sugiere el target acorde a la nueva intención
  }

  const descargarPlantilla = async () => {
    setError(null)
    // Con datos: plantilla a la medida del esquema inferido. Sin datos: plantilla por defecto
    // (columnas del ejemplo) para que el usuario la llene y la suba.
    const schema =
      hasRows && effTarget && effDate
        ? construirEsquema({ cols, target: effTarget, date: effDate, seriesKeys: effSeries })
        : DEFAULT_SCHEMA
    try {
      const { blob, filename } = await downloadAutoTemplate('sales', schema)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
    }
  }

  const predecir = async () => {
    setError(null)
    setAviso(null)
    const schema = construirEsquema({ cols, target: effTarget, date: effDate, seriesKeys: effSeries })
    setBusy(true)
    setData(null)
    setShownTarget(effTarget)
    try {
      let res: AutoSalesResponse
      if (excelFile) {
        res = await uploadAutoExcel<AutoSalesResponse>('sales', excelFile, {
          schema: JSON.stringify(schema),
          horizon: effHorizon,
          granularity: effGranularity,
        })
      } else {
        res = await postAutoSales({
          schema,
          horizon: effHorizon,
          granularity: effGranularity,
          rows: normalizarFilas(rows, cols),
        })
      }
      setData(res)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
      else setAviso(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <ModuleHeader view="sales" />

      {/* PASO 1 — Tus datos: carga columnas libres (mismas que Predicción a tu medida). */}
      <StepSection
        step={1}
        title="Tus datos"
        accentChip={ACCENT.chip}
        description="Sube tus ventas pasadas con las columnas que tengas (fecha, tienda, producto, unidades, precio, promoción, categoría, ingresos…). Acepta las mismas columnas ricas que «Predicción a tu medida»."
      >
        <div className="flex flex-wrap items-center gap-3">
          <label className={`btn cursor-pointer ${ACCENT.solid}`}>
            Subir JSON
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onJson(f)
                e.target.value = ''
              }}
            />
          </label>
          <label className="btn-ghost cursor-pointer">
            Subir Excel
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onExcel(f)
                e.target.value = ''
              }}
            />
          </label>
          <button type="button" className="btn-ghost" onClick={() => void descargarPlantilla()} disabled={busy}>
            Descargar plantilla Excel
          </button>
          <button
            type="button"
            className="badge bg-slate-100 text-slate-600 hover:bg-slate-200"
            onClick={() => cargarFilas(generarFilasDemo())}
            disabled={busy}
          >
            Cargar datos de ejemplo
          </button>
        </div>
        <p className="help">
          El JSON se lee aquí para detectar tus columnas. El Excel se procesa en el servidor con
          esas mismas columnas (configúralas antes con un JSON o el ejemplo).
        </p>

        {aviso && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800" role="alert">
            {aviso}
          </p>
        )}

        {hasRows && (
          <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-600">
            <p className="font-semibold text-slate-700">
              {fmtNum(rows.length)} filas · {cols.length} columnas detectadas
            </p>
            <p className="mt-1 flex flex-wrap gap-1">
              {cols.map((c) => (
                <span key={c.name} className={`badge ${ACCENT.badge}`}>
                  {c.name} ·{' '}
                  {c.kind === 'numeric' ? 'núm.' : c.kind === 'date' ? 'fecha' : 'categ.'}
                </span>
              ))}
            </p>
          </div>
        )}
      </StepSection>

      {/* PASO 2 — ¿Qué quieres pronosticar? + mapeo de columnas + configuración. */}
      <StepSection
        step={2}
        title="¿Qué quieres pronosticar?"
        accentChip={ACCENT.chip}
        description="Elige qué calcular (unidades, ingresos u otra cantidad) y confirma qué columnas son la fecha y las series. El resto de columnas se usan como factores."
      >
        {!hasRows && (
          <p className="text-sm text-slate-500">Carga tus datos en el Paso 1 para configurar el pronóstico.</p>
        )}

        {hasRows && (
          <div className="space-y-4">
            <div>
              <span className="label">¿Qué calcular?</span>
              <div className="flex flex-wrap gap-2">
                {(Object.keys(INTENCION_LABEL) as Intencion[]).map((i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => cambiarIntencion(i)}
                    className={`badge ${intencion === i ? ACCENT.solid : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                  >
                    {INTENCION_LABEL[i]}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-start gap-4">
              <div>
                <label className="label" htmlFor="target">
                  Columna a pronosticar
                </label>
                <select
                  id="target"
                  className="input"
                  value={effTarget}
                  disabled={busy}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  {numericas.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <p className="help">El valor numérico que quieres estimar a futuro.</p>
              </div>

              <div>
                <label className="label" htmlFor="date">
                  Columna de fecha
                </label>
                <select
                  id="date"
                  className="input"
                  value={effDate}
                  disabled={busy}
                  onChange={(e) => setDate(e.target.value)}
                >
                  {cols.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <p className="help">Cuándo ocurrió cada registro.</p>
              </div>

              <div>
                <span className="label">Series (desglose)</span>
                <div className="flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2">
                  {cols
                    .filter((c) => c.name !== effDate && c.name !== effTarget && c.kind !== 'numeric')
                    .map((c) => (
                      <label key={c.name} className="inline-flex items-center gap-1 text-sm text-slate-600">
                        <input
                          type="checkbox"
                          checked={effSeries.includes(c.name)}
                          disabled={busy}
                          onChange={() => toggleSerie(c.name)}
                        />
                        {c.name}
                      </label>
                    ))}
                </div>
                <p className="help">Tienda, producto… por qué columnas separar el pronóstico.</p>
              </div>
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
                  <p className="help">Períodos de la granularidad elegida.</p>
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
          </div>
        )}
      </StepSection>

      {/* PASO 3 — Entrena al momento y predice (motor agnóstico, ADR-0023). */}
      <StepSection
        step={3}
        title="Pronostica y revisa el resultado"
        accentChip={ACCENT.chip}
        description="El sistema entrena el mejor modelo para tus columnas con validación honesta y predice — todo en una llamada."
      >
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`btn ${ACCENT.solid}`} onClick={() => void predecir()} disabled={!puedePredecir}>
            {busy ? 'Entrenando y prediciendo…' : 'Pronosticar'}
          </button>
          {!hasRows && !excelFile && (
            <span className="text-sm text-slate-500" role="status">
              Carga tus datos (JSON, Excel o el ejemplo) para pronosticar.
            </span>
          )}
        </div>
      </StepSection>

      {error && <ErrorPanel error={error} />}

      {!data && !busy && !error && (
        <EmptyState
          icon={BarChart3}
          title="Aún no hay un pronóstico"
          message="Carga tus ventas, elige qué pronosticar y pulsa «Pronosticar». Verás un gráfico, una tabla descargable y un resumen claro."
        />
      )}

      {data && (
        <ResultSection
          data={data}
          rows={excelFile ? [] : rows}
          dateCol={effDate}
          targetCol={shownTarget || effTarget}
          granularity={effGranularity}
        />
      )}
    </div>
  )
}

function ResultSection({
  data,
  rows,
  dateCol,
  targetCol,
  granularity,
}: {
  data: AutoSalesResponse
  rows: AutoRow[]
  dateCol: string
  targetCol: string
  granularity: Granularity
}) {
  const forecast = data.forecast
  const cols = useMemo(() => columnasDinamicas(forecast), [forecast])

  // Series para el gráfico: histórico (datos subidos) vs. pronóstico (respuesta).
  const histPoints = useMemo(
    () =>
      rows
        .map((r) => ({ date: String(r[dateCol]), value: Number(r[targetCol]) || 0 }))
        .filter((p) => p.date && p.date !== 'undefined'),
    [rows, dateCol, targetCol],
  )
  const forePoints = useMemo(
    () => forecast.map((r) => ({ date: String(r.date), value: Number(r.forecast_demand) || 0 })),
    [forecast],
  )

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
      <TrainingCard training={data.training} accentSolid={ACCENT.solid} accentBadge={ACCENT.badge} />

      <ResultSummary text={resumenAuto(forecast, granularity, targetCol)} tone="bg-sales-50 text-sales-700" />

      <SerieChart
        history={histPoints}
        forecast={forePoints}
        histLabel={`Histórico (${targetCol})`}
        foreLabel="Pronóstico"
        hex={ACCENT.hex}
      />

      {forecast.length > 0 ? (
        <ResultTable columns={cols} rows={forecast} />
      ) : (
        <p className="text-sm text-slate-500">El modelo no produjo filas para esta consulta.</p>
      )}

      <TechnicalDetails>
        <p>
          Objetivo pronosticado: <span className="font-mono text-slate-700">{targetCol}</span>
        </p>
        <p>
          Firma del esquema: <span className="font-mono text-slate-700">{data.training.schema_signature}</span>
        </p>
        {Object.keys(data.training.honest_metrics).length > 0 && (
          <p>
            Métricas completas:{' '}
            {Object.entries(data.training.honest_metrics)
              .map(([k, v]) => `${k}=${fmtNum(v)}`)
              .join(' · ')}
          </p>
        )}
        <p>interval_80 (rango estimado al 80%): no disponible aún — el modelo todavía no produce intervalos.</p>
      </TechnicalDetails>
    </section>
  )
}
