import { useMemo, useState } from 'react'
import { ShoppingCart } from 'lucide-react'
import { ApiError } from '../api/client'
import { downloadAutoTemplate, postAutoPurchases, uploadAutoExcel } from '../api/endpoints'
import type { AutoPurchasesResponse, AutoRow } from '../api/types'
import { ErrorPanel } from '../components/ErrorPanel'
import { ResultTable } from '../components/ResultTable'
import { TrainingCard } from '../components/auto/TrainingCard'
import { ItemsEditor } from '../components/auto/ItemsEditor'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { StepSection } from '../components/ui/StepSection'
import { EmptyState } from '../components/ui/EmptyState'
import { ResultSummary } from '../components/ui/ResultSummary'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { generarFilasDemo, generarItemsDemo } from '../demo/retailDemo'
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

const ACCENT = SECTION_BY_ID.purchases.accent

// Explicación en lenguaje claro de cómo se obtiene «cuánto reponer». El backend envía la
// fórmula cruda en `justification` (contrato en inglés); en la app se muestra esta frase,
// que la describe fielmente, sin exponer la fórmula (ADR-0022).
export const PORQUE =
  'Demanda estimada durante el tiempo de entrega más la cobertura, y unas existencias de seguridad.'

type Intencion = 'producto' | 'dinero' | 'otro'

const INTENCION_LABEL: Record<Intencion, string> = {
  producto: 'Demanda en unidades (producto)',
  dinero: 'Demanda en dinero',
  otro: 'Otra cantidad',
}

/** Esquema por defecto (columnas del ejemplo) para descargar la plantilla Excel sin datos. */
const DEFAULT_SCHEMA = construirEsquema({
  cols: analizarColumnas(generarFilasDemo()),
  target: 'unidades_vendidas',
  date: 'fecha',
  seriesKeys: ['tienda', 'sku'],
})

/** Extrae historial + productos a reponer de un JSON (array de filas, u objeto con `rows`/
 *  `history` e `items`/`replenishment_params`). */
function extraerCompras(data: unknown): { rows: AutoRow[]; items: AutoRow[] } | null {
  if (Array.isArray(data)) return { rows: data as AutoRow[], items: [] }
  if (data && typeof data === 'object') {
    const o = data as { rows?: unknown; history?: unknown; items?: unknown; replenishment_params?: unknown }
    const rows = Array.isArray(o.rows) ? o.rows : Array.isArray(o.history) ? o.history : null
    if (rows) {
      const items = Array.isArray(o.items)
        ? o.items
        : Array.isArray(o.replenishment_params)
          ? o.replenishment_params
          : []
      return { rows: rows as AutoRow[], items: items as AutoRow[] }
    }
  }
  return null
}

/** Resumen en lenguaje natural de la recomendación de reposición. */
function resumenComprasAuto(recs: AutoRow[]): string {
  if (recs.length === 0) return 'No hay recomendaciones para mostrar.'
  const aReponer = recs.filter((r) => Number(r.replenishment_quantity) > 0)
  const total = aReponer.reduce((a, r) => a + (Number(r.replenishment_quantity) || 0), 0)
  if (aReponer.length === 0) {
    return 'Por ahora no necesitas reponer ninguno de estos productos: tus existencias cubren la demanda estimada.'
  }
  return `Conviene reponer alrededor de ${fmtNum(total)} unidades repartidas en ${fmtNum(
    aReponer.length,
  )} ${aReponer.length === 1 ? 'producto' : 'productos'}.`
}

export function PurchasesPage() {
  // PASO 1 — datos ricos + productos a reponer.
  const [rows, setRows] = useState<AutoRow[]>([])
  const [items, setItems] = useState<AutoRow[]>([])
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  // PASO 2 — mapeo (override del usuario; null = sugerencia automática).
  const [intencion, setIntencion] = useState<Intencion>('producto')
  const [target, setTarget] = useState<string | null>(null)
  const [date, setDate] = useState<string | null>(null)
  const [series, setSeries] = useState<string[] | null>(null)

  // PASO 3 — resultado.
  const [data, setData] = useState<AutoPurchasesResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)

  const cols = useMemo<ColumnInfo[]>(() => analizarColumnas(rows), [rows])

  const effDate = date ?? sugerirFecha(cols) ?? ''
  const effTarget =
    target ?? (intencion === 'otro' ? columnasNumericas(cols, [effDate])[0]?.name ?? '' : sugerirTarget(cols, intencion, [effDate]) ?? '')
  const effSeries = series ?? sugerirSeries(cols, [effDate, effTarget])

  const hasRows = rows.length > 0
  const numericas = useMemo(() => columnasNumericas(cols, [effDate]), [cols, effDate])

  const itemsValidos =
    items.length > 0 &&
    items.every(
      (it) =>
        effSeries.every((k) => String(it[k] ?? '') !== '') &&
        Number(it.lead_time_days) > 0 &&
        Number(it.target_coverage_days) > 0,
    )
  const puedeCalcular = (hasRows || excelFile != null) && !!effTarget && !!effDate && itemsValidos && !busy

  const resetMapeo = () => {
    setTarget(null)
    setDate(null)
    setSeries(null)
  }

  const cargarDatos = (nRows: AutoRow[], nItems: AutoRow[]) => {
    setRows(nRows)
    setItems(nItems)
    setExcelFile(null)
    resetMapeo()
    setData(null)
    setError(null)
    setAviso(null)
  }

  const onJson = async (file: File) => {
    setAviso(null)
    try {
      const parsed = extraerCompras(JSON.parse(await file.text()))
      if (!parsed || parsed.rows.length === 0) {
        setAviso('El JSON no contiene filas de historial. Usa un array de registros o un objeto con «rows».')
        return
      }
      cargarDatos(parsed.rows, parsed.items)
      if (parsed.items.length === 0) {
        setAviso('Historial cargado. Genera o agrega los productos a reponer abajo.')
      }
    } catch {
      setAviso('El archivo no es un JSON válido. Revisa el formato.')
    }
  }

  const onExcel = (file: File) => {
    if (cols.length === 0) {
      setAviso('Para Excel: primero carga un JSON o el ejemplo para configurar las columnas; el Excel debe traer esas mismas columnas.')
      return
    }
    setExcelFile(file)
    setData(null)
    setError(null)
    setAviso(`Excel «${file.name}» listo: completa los productos a reponer y calcula.`)
  }

  /** Crea un producto a reponer por cada serie distinta del historial cargado. */
  const generarItems = () => {
    const vistos = new Set<string>()
    const out: AutoRow[] = []
    for (const r of rows) {
      const clave = effSeries.map((k) => String(r[k])).join('|')
      if (vistos.has(clave)) continue
      vistos.add(clave)
      const it: AutoRow = {}
      for (const k of effSeries) it[k] = String(r[k])
      it.current_stock = 0
      it.lead_time_days = 5
      it.target_coverage_days = 14
      out.push(it)
    }
    setItems(out)
  }

  const cambiarIntencion = (i: Intencion) => {
    setIntencion(i)
    setTarget(null)
  }

  const descargarPlantilla = async () => {
    setError(null)
    const schema =
      hasRows && effTarget && effDate
        ? construirEsquema({ cols, target: effTarget, date: effDate, seriesKeys: effSeries })
        : DEFAULT_SCHEMA
    try {
      const { blob, filename } = await downloadAutoTemplate('purchases', schema)
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

  const calcular = async () => {
    setError(null)
    setAviso(null)
    const schema = construirEsquema({ cols, target: effTarget, date: effDate, seriesKeys: effSeries })
    // Coacciona los campos numéricos de los productos a reponer.
    const itemsLimpios = items.map((it) => ({
      ...it,
      current_stock: Number(it.current_stock) || 0,
      lead_time_days: Number(it.lead_time_days) || 0,
      target_coverage_days: Number(it.target_coverage_days) || 0,
    }))
    setBusy(true)
    setData(null)
    try {
      let res: AutoPurchasesResponse
      if (excelFile) {
        res = await uploadAutoExcel<AutoPurchasesResponse>('purchases', excelFile, {
          schema: JSON.stringify(schema),
          items: JSON.stringify(itemsLimpios),
        })
      } else {
        res = await postAutoPurchases({ schema, rows: normalizarFilas(rows, cols), items: itemsLimpios })
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
      <ModuleHeader view="purchases" />

      {/* PASO 1 — Tus datos: historial rico + productos a reponer. */}
      <StepSection
        step={1}
        title="Tus datos"
        accentChip={ACCENT.chip}
        description="Sube tu historial de ventas con las columnas que tengas (las mismas columnas ricas que «Predicción a tu medida») y define los productos a reponer."
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
            onClick={() => cargarDatos(generarFilasDemo(), generarItemsDemo())}
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
                  {c.name} · {c.kind === 'numeric' ? 'núm.' : c.kind === 'date' ? 'fecha' : 'categ.'}
                </span>
              ))}
            </p>
          </div>
        )}

        <div className="my-1 h-px bg-slate-200" aria-hidden="true" />

        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-700">Productos a reponer</h4>
              <p className="help mt-0">Stock actual, días de entrega y cobertura objetivo por producto.</p>
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
            seriesKeys={effSeries.length > 0 ? effSeries : ['tienda', 'sku']}
            items={items}
            onChange={setItems}
            disabled={busy}
            accentBadge={ACCENT.badge}
          />
        </div>
      </StepSection>

      {/* PASO 2 — ¿Qué demanda pronosticar? + mapeo de columnas. */}
      <StepSection
        step={2}
        title="¿Qué demanda pronosticar?"
        accentChip={ACCENT.chip}
        description="Elige qué demanda estimar (unidades, dinero u otra cantidad) y confirma qué columnas son la fecha y las series. El resto de columnas se usan como factores."
      >
        {!hasRows && (
          <p className="text-sm text-slate-500">Carga tus datos en el Paso 1 para configurar el pronóstico.</p>
        )}

        {hasRows && (
          <div className="space-y-4">
            <div>
              <span className="label">¿Qué estimar?</span>
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
                <label className="label" htmlFor="target">Columna de demanda</label>
                <select id="target" className="input" value={effTarget} disabled={busy} onChange={(e) => setTarget(e.target.value)}>
                  {numericas.map((c) => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
                <p className="help">El valor numérico cuya demanda futura quieres estimar.</p>
              </div>

              <div>
                <label className="label" htmlFor="date">Columna de fecha</label>
                <select id="date" className="input" value={effDate} disabled={busy} onChange={(e) => setDate(e.target.value)}>
                  {cols.map((c) => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
                <p className="help">Cuándo ocurrió cada registro.</p>
              </div>

              <div>
                <span className="label">Series (producto a reponer)</span>
                <div className="flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2">
                  {cols
                    .filter((c) => c.name !== effDate && c.name !== effTarget && c.kind !== 'numeric')
                    .map((c) => (
                      <label key={c.name} className="inline-flex items-center gap-1 text-sm text-slate-600">
                        <input
                          type="checkbox"
                          checked={effSeries.includes(c.name)}
                          disabled={busy}
                          onChange={() =>
                            setSeries(
                              effSeries.includes(c.name)
                                ? effSeries.filter((s) => s !== c.name)
                                : [...effSeries, c.name],
                            )
                          }
                        />
                        {c.name}
                      </label>
                    ))}
                </div>
                <p className="help">Tienda, producto… deben coincidir con los productos a reponer.</p>
              </div>
            </div>
          </div>
        )}
      </StepSection>

      {/* PASO 3 — Calcular la reposición (motor agnóstico, ADR-0023). */}
      <StepSection
        step={3}
        title="Calcula la reposición"
        accentChip={ACCENT.chip}
        description="El sistema entrena el mejor modelo para tu demanda con validación honesta y calcula cuánto y cuándo reponer cada producto."
      >
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`btn ${ACCENT.solid}`} onClick={() => void calcular()} disabled={!puedeCalcular}>
            {busy ? 'Calculando…' : 'Calcular reposición'}
          </button>
          {!puedeCalcular && !busy && (
            <span className="text-sm text-slate-500" role="status">
              Carga tu historial, elige qué pronosticar y completa los productos a reponer (entrega y cobertura &gt; 0).
            </span>
          )}
        </div>
      </StepSection>

      {error && <ErrorPanel error={error} />}

      {!data && !busy && !error && (
        <EmptyState
          icon={ShoppingCart}
          title="Aún no hay recomendaciones"
          message="Carga tus productos y su historial, y calcula cuánto y cuándo reponer cada uno."
        />
      )}

      {data && <PurchasesResult data={data} />}
    </div>
  )
}

function PurchasesResult({ data }: { data: AutoPurchasesResponse }) {
  const recs = data.recommendation
  // Tabla dinámica sin la columna `justification` cruda: la explicación va una sola vez como nota.
  const cols = useMemo(() => columnasDinamicas(recs).filter((c) => c.header !== 'Cálculo'), [recs])

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Recomendación de reposición</h3>
      <TrainingCard training={data.training} accentSolid={ACCENT.solid} accentBadge={ACCENT.badge} />
      <ResultSummary text={resumenComprasAuto(recs)} tone="bg-purchases-50 text-purchases-700" />

      {recs.length > 0 ? (
        <>
          <ResultTable columns={cols} rows={recs} />
          <p className="text-xs text-slate-500">
            <span className="font-medium">Cómo se calcula:</span> {PORQUE}
          </p>
        </>
      ) : (
        <p className="text-sm text-slate-500">El modelo no produjo recomendaciones para esta consulta.</p>
      )}

      <TechnicalDetails>
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
      </TechnicalDetails>
    </section>
  )
}
