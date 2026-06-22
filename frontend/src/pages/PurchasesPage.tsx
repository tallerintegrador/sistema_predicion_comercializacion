import { useMemo, useState } from 'react'
import { ShoppingCart } from 'lucide-react'
import { postPurchases, uploadExcel } from '../api/endpoints'
import type { PurchasesRequest, PurchasesResponse, RecommendationItem } from '../api/types'
import { usePrediction } from '../hooks/usePrediction'
import { useDomainCatalog } from '../hooks/useDomainCatalog'
import { ErrorPanel } from '../components/ErrorPanel'
import { DataSourcePanel } from '../components/DataSourcePanel'
import { CatalogTable } from '../components/CatalogTable'
import { HistoryPreview } from '../components/HistoryPreview'
import { ReuseHistoryNotice } from '../components/data/ReuseHistoryNotice'
import { JobBanner } from '../components/JobBanner'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { PurchasesChart } from '../components/charts/PurchasesChart'
import { ResultFilters } from '../components/result/ResultFilters'
import { useResultFilters } from '../hooks/useResultFilters'
import type { ResultFiltersSpec } from '../hooks/useResultFilters'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { StepSection } from '../components/ui/StepSection'
import { EmptyState } from '../components/ui/EmptyState'
import { ResultSummary } from '../components/ui/ResultSummary'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { resumenCompras } from '../utils/resumen'
import type { EditableRow } from '../utils/tableData'
import { coerceRows, objectsToRows, rowsComplete } from '../utils/tableData'

const ACCENT = SECTION_BY_ID.purchases.accent

// Explicación en lenguaje claro de cómo se obtiene «cuánto reponer». El backend envía la
// fórmula cruda en `justification` (contrato en inglés); en la app se muestra esta frase,
// que la describe fielmente, sin exponer la fórmula (ADR-0022).
export const PORQUE =
  'Demanda estimada durante el tiempo de entrega más la cobertura, y unas existencias de seguridad.'

const cols: Column<RecommendationItem>[] = [
  { header: 'Tienda', render: (r) => r.store_id },
  { header: 'Producto', render: (r) => r.product_id },
  { header: 'Demanda estimada', align: 'right', render: (r) => fmtNum(r.expected_demand_horizon) },
  { header: 'Reponer al bajar a', align: 'right', render: (r) => fmtNum(r.reorder_point) },
  { header: 'Cuánto reponer', align: 'right', render: (r) => fmtNum(r.replenishment_quantity) },
  { header: 'Por qué', render: () => <span className="text-xs text-slate-500">{PORQUE}</span> },
]

export function PurchasesPage() {
  const { domain, loading, error } = useDomainCatalog('purchases')
  const historyTable = domain?.input_tables.find((t) => t.name === 'history') ?? null
  const paramsTable = domain?.input_tables.find((t) => t.name === 'replenishment_params') ?? null

  const [histRows, setHistRows] = useState<EditableRow[]>([])
  const [paramRows, setParamRows] = useState<EditableRow[]>([])
  const [jsonError, setJsonError] = useState<string | null>(null)

  const pred = usePrediction<PurchasesResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  const completo = useMemo(
    () =>
      !!historyTable &&
      !!paramsTable &&
      rowsComplete(historyTable.columns, histRows) &&
      rowsComplete(paramsTable.columns, paramRows),
    [historyTable, paramsTable, histRows, paramRows],
  )

  const onJson = (data: unknown) => {
    const obj = (data ?? {}) as { history?: unknown; replenishment_params?: unknown }
    if (!Array.isArray(obj.history) || !Array.isArray(obj.replenishment_params)) {
      setJsonError('El JSON debe incluir el historial y los productos a reponer. Usa la plantilla como guía.')
      return
    }
    setJsonError(null)
    if (historyTable) setHistRows(objectsToRows(historyTable.columns, obj.history as Record<string, unknown>[]))
    if (paramsTable) setParamRows(objectsToRows(paramsTable.columns, obj.replenishment_params as Record<string, unknown>[]))
    pred.reset()
  }

  const predict = () => {
    if (!historyTable || !paramsTable) return
    const req = {
      history: coerceRows(historyTable.columns, histRows),
      replenishment_params: coerceRows(paramsTable.columns, paramRows),
    } as unknown as PurchasesRequest
    pred.run(() => postPurchases(req))
  }
  const onExcel = (file: File) => pred.run(() => uploadExcel<PurchasesResponse>('purchases', file))

  return (
    <div className="space-y-5">
      <ModuleHeader view="purchases" />

      {loading && <p className="text-sm text-slate-500">Cargando…</p>}
      {error && <ErrorPanel error={error} />}

      {historyTable && paramsTable && (
        <>
          {/* PASO 1 — Tus datos: historial SIEMPRE por archivo; productos a reponer a mano o por archivo. */}
          <StepSection
            step={1}
            title="Tus datos"
            accentChip={ACCENT.chip}
            description="Sube tu historial de ventas por archivo y añade los productos a reponer."
          >
            {/* Historial de ventas: solo por archivo (no se ingresa a mano). */}
            <div className="space-y-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-700">{historyTable.label}</h4>
                <p className="help mt-0">
                  Tu historial de ventas se carga siempre por archivo (Excel o JSON); no se ingresa a
                  mano. Descarga la plantilla, complétala y vuelve a subirla.
                </p>
              </div>
              <DataSourcePanel domain="purchases" onExcel={onExcel} onJson={onJson} busy={busy} accentSolid={ACCENT.solid} />
              <ReuseHistoryNotice />
              {histRows.length > 0 && (
                <div>
                  <p className="label">Resumen de tu historial</p>
                  <HistoryPreview history={histRows} />
                </div>
              )}
            </div>

            <div className="my-2 h-px bg-slate-200" aria-hidden="true" />

            {/* Productos a reponer: lista corta del estado actual; se puede ingresar a mano. */}
            <CatalogTable table={paramsTable} rows={paramRows} onChange={setParamRows} disabled={busy} />

            {jsonError && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {jsonError}
              </p>
            )}
          </StepSection>

          {/* No hay configuración de pronóstico aplicable en Compras → se omite ese paso. */}

          {/* PASO 2 — Acción: calcular la reposición con los datos cargados. */}
          <StepSection
            step={2}
            title="Calcula la reposición"
            accentChip={ACCENT.chip}
            description="Con tus datos listos, calcula cuánto y cuándo reponer cada producto."
          >
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={`btn ${ACCENT.solid}`} onClick={predict} disabled={busy || !completo}>
                {busy ? 'Calculando…' : 'Calcular reposición'}
              </button>
              {!completo && (
                <span className="text-sm text-slate-500" role="status">
                  Sube tu historial de ventas (Excel o JSON) y completa los productos a reponer
                  (campos con *).
                </span>
              )}
            </div>
          </StepSection>
        </>
      )}

      <JobBanner status={pred.status} jobId={pred.jobId} attempts={pred.attempts} />
      {pred.status === 'error' && pred.error && <ErrorPanel error={pred.error} />}

      {pred.status === 'idle' && !busy && (
        <EmptyState
          icon={ShoppingCart}
          title="Aún no hay recomendaciones"
          message="Carga tus productos y su historial, y calcula cuánto y cuándo reponer cada uno."
        />
      )}

      {pred.status === 'done' && pred.data && <PurchasesResult data={pred.data} />}
    </div>
  )
}

/** Resultado de Compras con filtros derivados de los campos reales de la respuesta. */
function PurchasesResult({ data }: { data: PurchasesResponse }) {
  const rows = data.recommendation

  const spec = useMemo<ResultFiltersSpec<RecommendationItem>>(
    () => ({
      facets: [
        { key: 'store_id', label: 'Tienda', read: (r) => r.store_id },
        { key: 'product_id', label: 'Producto', read: (r) => r.product_id },
      ],
      toggles: [
        {
          key: 'needs',
          label: 'Solo los que requieren reposición ahora',
          predicate: (r) => r.replenishment_quantity > 0,
        },
      ],
      sorts: [
        {
          key: 'store',
          label: 'Tienda y producto',
          compare: (a, b) =>
            a.store_id.localeCompare(b.store_id, 'es', { numeric: true }) ||
            a.product_id.localeCompare(b.product_id, 'es', { numeric: true }),
        },
        {
          key: 'qty',
          label: 'Cantidad a reponer (mayor primero)',
          compare: (a, b) => b.replenishment_quantity - a.replenishment_quantity,
        },
      ],
    }),
    [],
  )

  const filters = useResultFilters(rows, spec)
  const { filtered } = filters

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Recomendación de reposición</h3>
      <ResultSummary text={resumenCompras(filtered)} tone="bg-purchases-50 text-purchases-700" />
      <ResultFilters
        spec={spec}
        filters={filters}
        comingSoon={[
          {
            key: 'category',
            label: 'Categoría / familia',
            hint: 'Disponible cuando el sistema indique la categoría o familia de cada producto.',
          },
          {
            key: 'urgency',
            label: 'Ordenar por urgencia',
            hint: 'Disponible cuando el sistema entregue una medida de urgencia de reposición.',
          },
        ]}
      />
      {filtered.length > 0 ? (
        <>
          {filtered.length !== rows.length && (
            <p className="text-xs text-slate-500">
              Mostrando {filtered.length} de {rows.length} productos.
            </p>
          )}
          <PurchasesChart rows={filtered} />
          <ResultTable columns={cols} rows={filtered} />
        </>
      ) : (
        <p className="text-sm text-slate-500">No hay productos que cumplan los filtros seleccionados.</p>
      )}
    </section>
  )
}
