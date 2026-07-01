/**
 * Motor de **predicción guiada** (ADR-0023): el flujo común de los cuatro modos de
 * predicción a tu medida (Ventas, Compras, Almacén y «Otro rubro»). Todos comparten el
 * mismo motor agnóstico que entrena varios modelos con los datos del cliente y se queda
 * con el mejor; solo cambian las etiquetas, los productos a reponer y cómo se muestra el
 * resultado. Esa variación vive en {@link DomainConfig}; aquí está la mecánica compartida
 * (cargar datos → mapear columnas → entrenar y predecir), antes duplicada en cada página.
 */
import { useMemo, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ApiError } from '../../api/client'
import { downloadAutoTemplate } from '../../api/endpoints'
import type { AutoRow, AutoSchemaSpec, AutoTrainingInfo, Domain, QueryOptions } from '../../api/types'
import { ErrorPanel } from '../ErrorPanel'
import { MapeoColumnas, type MapeoLabels } from '../auto/MapeoColumnas'
import { FactoresPreview } from '../auto/FactoresPreview'
import { ItemsEditor } from '../auto/ItemsEditor'
import type { NumCol } from '../auto/itemCols'
import { ModuleHeader } from '../ui/ModuleHeader'
import { StepSection } from '../ui/StepSection'
import { EmptyState } from '../ui/EmptyState'
import type { Accent, View } from '../../theme/modules'
import { fmtNum } from '../../utils/format'
import { generarFilasDemo } from '../../demo/retailDemo'
import {
  analizarColumnas,
  candidatasTarget,
  construirEsquema,
  esConocidaFutura,
  normalizarFilas,
  sugerirFecha,
  sugerirSeries,
  sugerirTarget,
} from '../../utils/inferSchema'
import type { ColumnInfo } from '../../utils/inferSchema'

/** Qué cantidad se quiere estimar (afina la sugerencia automática del target). */
export type Intencion = 'producto' | 'dinero' | 'otro'

export interface PredecirArgs {
  schema: AutoSchemaSpec
  rows: AutoRow[]
  items: AutoRow[]
  extra: Record<string, unknown>
  options: QueryOptions | null
}

export interface PredecirExcelArgs {
  schema: AutoSchemaSpec
  file: File
  items: AutoRow[]
  extra: Record<string, unknown>
  options: QueryOptions | null
}

export interface ResultadoArgs<Res> {
  data: Res
  /** Filas originales cargadas (para el gráfico); vacío si se usó Excel. */
  rows: AutoRow[]
  effDate: string
  effTarget: string
  extra: Record<string, unknown>
  options: QueryOptions | null
}

/** Sección de «productos» (Compras = reponer; Almacén = estado). Ausente en Ventas. */
export interface ItemsConfig {
  titulo: string
  ayuda: string
  numCols?: NumCol[]
  avisoSinItems: string
  generarDemo: () => AutoRow[]
  /** Fila nueva en blanco para una serie (al «Generar desde mis datos» o «Agregar»). */
  nuevoItem: (seriesKeys: string[]) => AutoRow
  /** ¿La fila tiene lo mínimo para calcular? (claves de serie + campos numéricos > 0). */
  valido: (it: AutoRow, seriesKeys: string[]) => boolean
}

export interface DomainConfig<Res extends { training: AutoTrainingInfo }> {
  domain: Domain
  accent: Accent
  // --- Paso 1: datos ---
  datosDescripcion: string
  /** Lee filas (+items) de un JSON ya parseado; null si no hay filas válidas. */
  extraerDatos: (data: unknown) => { rows: AutoRow[]; items: AutoRow[] } | null
  excelAviso: (filename: string) => string
  items?: ItemsConfig
  // --- Paso 2: ¿qué predecir? + mapeo ---
  intencionLabel: Record<Intencion, string>
  paso2Titulo: string
  paso2Desc: string
  mapeoLabels: MapeoLabels
  /** Controles extra del Paso 2 (granularidad/horizonte en Ventas, percentil en Almacén). */
  extraInicial?: Record<string, unknown>
  renderExtra?: (a: {
    extra: Record<string, unknown>
    set: (k: string, v: unknown) => void
    busy: boolean
    options: QueryOptions | null
  }) => ReactNode
  // --- Paso 3: acción ---
  paso3Titulo: string
  paso3Desc: string
  botonAccion: string
  botonBusy: string
  /** Mensaje cuando aún no se puede ejecutar (faltan datos/items). */
  faltaParaPredecir: string
  predecir: (a: PredecirArgs) => Promise<Res>
  predecirExcel: (a: PredecirExcelArgs) => Promise<Res>
  // --- Resultado / vacío ---
  empty: { icon: LucideIcon; titulo: string; mensaje: string }
  renderResultado: (a: ResultadoArgs<Res>) => ReactNode
}

/** Esquema por defecto (columnas del ejemplo): permite descargar la plantilla Excel sin
 *  haber cargado datos. Idéntico para los cuatro modos. */
const DEFAULT_SCHEMA = construirEsquema({
  cols: analizarColumnas(generarFilasDemo()),
  target: 'unidades_vendidas',
  date: 'fecha',
  seriesKeys: ['tienda', 'sku'],
})

/** Opciones de consulta del flujo guiado (estáticas): granularidad y rango de horizonte.
 *  Antes venían del `GET /catalog`; ahora el frontend las declara, y el backend queda
 *  solo-predicción (motores entrenados en el momento). */
const OPCIONES_GUIADAS: QueryOptions = {
  typologies: [],
  dimensions: [],
  granularities: [
    { name: 'day', label: 'Día' },
    { name: 'week', label: 'Semana' },
    { name: 'month', label: 'Mes' },
  ],
  horizon: { min: 1, max: 365, default: 14, unit: 'periods' },
}

function guardarBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function PrediccionGuiada<Res extends { training: AutoTrainingInfo }>({
  view,
  config,
  intro,
}: {
  view: View
  config: DomainConfig<Res>
  /** Contenido opcional bajo el encabezado (p. ej. el selector de objetivo de «Otro rubro»). */
  intro?: ReactNode
}) {
  const ACCENT = config.accent
  const options = OPCIONES_GUIADAS

  // Paso 1 — datos ricos (columnas libres) + productos (si el modo los usa).
  const [rows, setRows] = useState<AutoRow[]>([])
  const [items, setItems] = useState<AutoRow[]>([])
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  // Paso 2 — mapeo (override del usuario; null = sugerencia automática) + extras.
  const [intencion, setIntencion] = useState<Intencion>('producto')
  const [target, setTarget] = useState<string | null>(null)
  const [date, setDate] = useState<string | null>(null)
  const [series, setSeries] = useState<string[] | null>(null)
  const [futureOverrides, setFutureOverrides] = useState<Record<string, boolean>>({})
  const [extra, setExtra] = useState<Record<string, unknown>>(config.extraInicial ?? {})

  // Paso 3 — resultado.
  const [data, setData] = useState<Res | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [shownTarget, setShownTarget] = useState<string>('')

  const cols = useMemo<ColumnInfo[]>(() => analizarColumnas(rows), [rows])

  // Valores efectivos: el override del usuario o la sugerencia inferida de las columnas.
  const effDate = date ?? sugerirFecha(cols) ?? ''
  const effTarget =
    target ??
    (intencion === 'otro'
      ? candidatasTarget(cols, [effDate])[0]?.name ?? ''
      : sugerirTarget(cols, intencion, [effDate]) ?? '')
  const effSeries = series ?? sugerirSeries(cols, [effDate, effTarget])

  const hasRows = rows.length > 0
  const itemsValidos = config.items
    ? items.length > 0 && items.every((it) => config.items!.valido(it, effSeries))
    : true
  const puedePredecir = (hasRows || excelFile != null) && !!effTarget && !!effDate && itemsValidos && !busy

  const setExtraKey = (k: string, v: unknown) => setExtra((prev) => ({ ...prev, [k]: v }))

  const resetMapeo = () => {
    setTarget(null)
    setDate(null)
    setSeries(null)
    setFutureOverrides({})
  }

  const toggleSerie = (name: string) =>
    setSeries(effSeries.includes(name) ? effSeries.filter((s) => s !== name) : [...effSeries, name])

  const toggleFuture = (name: string) =>
    setFutureOverrides((prev) => ({ ...prev, [name]: !(prev[name] ?? esConocidaFutura(name)) }))

  const cargarDatos = (nRows: AutoRow[], nItems: AutoRow[]) => {
    setRows(nRows)
    setItems(nItems)
    setExcelFile(null)
    resetMapeo()
    setData(null)
    setError(null)
    if (config.items && nItems.length === 0) setAviso(config.items.avisoSinItems)
    else setAviso(null)
  }

  const onJson = async (file: File) => {
    setAviso(null)
    try {
      const parsed = config.extraerDatos(JSON.parse(await file.text()))
      if (!parsed || parsed.rows.length === 0) {
        setAviso('El JSON no contiene filas de datos. Usa un array de registros o un objeto con «rows».')
        return
      }
      cargarDatos(parsed.rows, parsed.items)
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
    setAviso(config.excelAviso(file.name))
  }

  /** Crea un producto por cada serie distinta del historial cargado (Compras/Almacén). */
  const generarItems = () => {
    if (!config.items) return
    const vistos = new Set<string>()
    const out: AutoRow[] = []
    for (const r of rows) {
      const clave = effSeries.map((k) => String(r[k])).join('|')
      if (vistos.has(clave)) continue
      vistos.add(clave)
      const it = config.items.nuevoItem(effSeries)
      for (const k of effSeries) it[k] = String(r[k])
      out.push(it)
    }
    setItems(out)
  }

  const cambiarIntencion = (i: Intencion) => {
    setIntencion(i)
    setTarget(null) // re-sugiere el target acorde a la nueva intención
  }

  const descargarPlantilla = async () => {
    setError(null)
    const schema =
      hasRows && effTarget && effDate
        ? construirEsquema({ cols, target: effTarget, date: effDate, seriesKeys: effSeries, futureOverrides })
        : DEFAULT_SCHEMA
    try {
      const { blob, filename } = await downloadAutoTemplate(config.domain, schema)
      guardarBlob(blob, filename)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
    }
  }

  const predecir = async () => {
    setError(null)
    setAviso(null)
    const schema = construirEsquema({ cols, target: effTarget, date: effDate, seriesKeys: effSeries, futureOverrides })
    setBusy(true)
    setData(null)
    setShownTarget(effTarget)
    try {
      const res = excelFile
        ? await config.predecirExcel({ schema, file: excelFile, items, extra, options })
        : await config.predecir({ schema, rows: normalizarFilas(rows, cols), items, extra, options })
      setData(res)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
      else setAviso(String(e))
    } finally {
      setBusy(false)
    }
  }

  const Empty = config.empty.icon
  const seriesKeysItems = effSeries.length > 0 ? effSeries : ['tienda', 'sku']

  return (
    <div className="space-y-5">
      <ModuleHeader view={view} />
      {intro}

      {/* PASO 1 — Tus datos: columnas libres (+ productos si el modo los usa). */}
      <StepSection step={1} title="Tus datos" accentChip={ACCENT.chip} description={config.datosDescripcion}>
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
            onClick={() => cargarDatos(generarFilasDemo(), config.items?.generarDemo() ?? [])}
            disabled={busy}
          >
            Cargar datos de ejemplo
          </button>
        </div>
        <p className="help">
          El JSON se lee aquí para detectar tus columnas. El Excel se procesa en el servidor con esas
          mismas columnas (configúralas antes con un JSON o el ejemplo).
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
                  {c.name} · {c.kind === 'numeric' ? 'núm.' : c.kind === 'date' ? 'fecha' : 'categ.'}
                </span>
              ))}
            </p>
          </div>
        )}

        {config.items && (
          <>
            <div className="my-1 h-px bg-slate-200" aria-hidden="true" />
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-sm font-semibold text-slate-700">{config.items.titulo}</h4>
                  <p className="help mt-0">{config.items.ayuda}</p>
                </div>
                <button
                  type="button"
                  className={`badge ${ACCENT.badge}`}
                  onClick={generarItems}
                  disabled={busy || !hasRows}
                >
                  Generar desde mis datos
                </button>
              </div>
              <ItemsEditor
                seriesKeys={seriesKeysItems}
                items={items}
                onChange={setItems}
                numCols={config.items.numCols}
                disabled={busy}
                accentBadge={ACCENT.badge}
              />
            </div>
          </>
        )}
      </StepSection>

      {/* PASO 2 — ¿Qué predecir? + mapeo de columnas + controles extra. */}
      <StepSection step={2} title={config.paso2Titulo} accentChip={ACCENT.chip} description={config.paso2Desc}>
        {!hasRows && (
          <p className="text-sm text-slate-500">Carga tus datos en el Paso 1 para configurar la predicción.</p>
        )}

        {hasRows && (
          <div className="space-y-4">
            <div>
              <span className="label">¿Qué estimar?</span>
              <div className="flex flex-wrap gap-2">
                {(Object.keys(config.intencionLabel) as Intencion[]).map((i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => cambiarIntencion(i)}
                    className={`badge ${intencion === i ? ACCENT.solid : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                  >
                    {config.intencionLabel[i]}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-start gap-4">
              <MapeoColumnas
                cols={cols}
                target={effTarget}
                date={effDate}
                series={effSeries}
                busy={busy}
                labels={config.mapeoLabels}
                onTarget={setTarget}
                onDate={setDate}
                onToggleSerie={toggleSerie}
              />
            </div>

            <FactoresPreview
              cols={cols}
              reservadas={[effTarget, effDate, ...effSeries]}
              futureOverrides={futureOverrides}
              busy={busy}
              onToggleFuture={toggleFuture}
            />

            {config.renderExtra?.({ extra, set: setExtraKey, busy, options })}
          </div>
        )}
      </StepSection>

      {/* PASO 3 — Entrena el mejor modelo con tus datos y predice (ADR-0023). */}
      <StepSection step={3} title={config.paso3Titulo} accentChip={ACCENT.chip} description={config.paso3Desc}>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`btn ${ACCENT.solid}`} onClick={() => void predecir()} disabled={!puedePredecir}>
            {busy ? config.botonBusy : config.botonAccion}
          </button>
          {!puedePredecir && !busy && (
            <span className="text-sm text-slate-500" role="status">
              {config.faltaParaPredecir}
            </span>
          )}
        </div>
      </StepSection>

      {error && <ErrorPanel error={error} />}

      {!data && !busy && !error && (
        <EmptyState icon={Empty} title={config.empty.titulo} message={config.empty.mensaje} />
      )}

      {data &&
        config.renderResultado({
          data,
          rows: excelFile ? [] : rows,
          effDate,
          effTarget: shownTarget || effTarget,
          extra,
          options,
        })}
    </div>
  )
}
