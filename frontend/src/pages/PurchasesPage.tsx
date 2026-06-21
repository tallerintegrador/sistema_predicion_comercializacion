import { useMemo, useState } from 'react'
import { ShoppingCart } from 'lucide-react'
import { postPurchases, uploadExcel } from '../api/endpoints'
import type { PurchasesRequest, PurchasesResponse, RecommendationItem } from '../api/types'
import { usePrediction } from '../hooks/usePrediction'
import { useDomainCatalog } from '../hooks/useDomainCatalog'
import { ErrorPanel } from '../components/ErrorPanel'
import { DataSourcePanel } from '../components/DataSourcePanel'
import { CatalogTable } from '../components/CatalogTable'
import { JobBanner } from '../components/JobBanner'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { PurchasesChart } from '../components/charts/PurchasesChart'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { ResultSummary } from '../components/ui/ResultSummary'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { resumenCompras } from '../utils/resumen'
import type { EditableRow } from '../utils/tableData'
import { coerceRows, objectsToRows, rowsComplete } from '../utils/tableData'

const ACCENT = SECTION_BY_ID.purchases.accent

const cols: Column<RecommendationItem>[] = [
  { header: 'Tienda', render: (r) => r.store_id },
  { header: 'Producto', render: (r) => r.product_id },
  { header: 'Demanda estimada', align: 'right', render: (r) => fmtNum(r.expected_demand_horizon) },
  { header: 'Reponer al bajar a', align: 'right', render: (r) => fmtNum(r.reorder_point) },
  { header: 'Cuánto reponer', align: 'right', render: (r) => fmtNum(r.replenishment_quantity) },
  { header: 'Por qué', render: (r) => <span className="text-xs text-slate-500">{r.justification}</span> },
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
        <section className="card space-y-6">
          <h3 className="text-base font-semibold text-slate-800">Tus datos</h3>
          <CatalogTable table={paramsTable} rows={paramRows} onChange={setParamRows} disabled={busy} />
          <CatalogTable table={historyTable} rows={histRows} onChange={setHistRows} disabled={busy} />

          <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4">
            <button type="button" className={`btn ${ACCENT.solid}`} onClick={predict} disabled={busy || !completo}>
              {busy ? 'Calculando…' : 'Calcular reposición'}
            </button>
            {!completo && (
              <span className="text-sm text-slate-500" role="status">
                Completa las filas obligatorias (marcadas con *), o sube un archivo.
              </span>
            )}
          </div>
        </section>
      )}

      <DataSourcePanel domain="purchases" onExcel={onExcel} onJson={onJson} busy={busy} accentSolid={ACCENT.solid} />
      {jsonError && (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
          {jsonError}
        </p>
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

      {pred.status === 'done' && pred.data && (
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-slate-800">Recomendación de reposición</h3>
          <ResultSummary text={resumenCompras(pred.data.recommendation)} tone="bg-purchases-50 text-purchases-700" />
          <PurchasesChart rows={pred.data.recommendation} />
          <ResultTable columns={cols} rows={pred.data.recommendation} />
        </section>
      )}
    </div>
  )
}
