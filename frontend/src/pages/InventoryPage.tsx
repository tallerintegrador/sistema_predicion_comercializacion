import { useMemo, useState } from 'react'
import { Package } from 'lucide-react'
import { postInventory, uploadExcel } from '../api/endpoints'
import type { AlertItem, InventoryRequest, InventoryResponse } from '../api/types'
import { usePrediction } from '../hooks/usePrediction'
import { useDomainCatalog } from '../hooks/useDomainCatalog'
import { ErrorPanel } from '../components/ErrorPanel'
import { DataSourcePanel } from '../components/DataSourcePanel'
import { CatalogTable } from '../components/CatalogTable'
import { HistoryPreview } from '../components/HistoryPreview'
import { JobBanner } from '../components/JobBanner'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { InventoryRisk } from '../components/charts/InventoryRisk'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { StepSection } from '../components/ui/StepSection'
import { EmptyState } from '../components/ui/EmptyState'
import { ResultSummary } from '../components/ui/ResultSummary'
import { RiskBadge } from '../components/ui/RiskBadge'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum, fmtPct } from '../utils/format'
import { resumenAlmacen } from '../utils/resumen'
import type { EditableRow } from '../utils/tableData'
import { coerceRows, objectsToRows, rowsComplete } from '../utils/tableData'

const ACCENT = SECTION_BY_ID.inventory.accent

const cols: Column<AlertItem>[] = [
  { header: 'Tienda', render: (r) => r.store_id },
  { header: 'Producto', render: (r) => r.product_id },
  { header: 'Estado', render: (r) => <RiskBadge alert={r} /> },
  { header: 'Prob. demanda alta', align: 'right', render: (r) => fmtPct(r.high_demand_probability) },
  { header: 'Existencias sugeridas', align: 'right', render: (r) => fmtNum(r.recommended_stock) },
  { header: 'Colchón de seguridad', align: 'right', render: (r) => fmtNum(r.safety_stock) },
]

export function InventoryPage() {
  const { domain, loading, error } = useDomainCatalog('inventory')
  const historyTable = domain?.input_tables.find((t) => t.name === 'history') ?? null
  const statusTable = domain?.input_tables.find((t) => t.name === 'inventory_status') ?? null

  const [histRows, setHistRows] = useState<EditableRow[]>([])
  const [statusRows, setStatusRows] = useState<EditableRow[]>([])
  const [jsonError, setJsonError] = useState<string | null>(null)

  const pred = usePrediction<InventoryResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  const completo = useMemo(
    () =>
      !!historyTable &&
      !!statusTable &&
      rowsComplete(historyTable.columns, histRows) &&
      rowsComplete(statusTable.columns, statusRows),
    [historyTable, statusTable, histRows, statusRows],
  )

  const onJson = (data: unknown) => {
    const obj = (data ?? {}) as { history?: unknown; inventory_status?: unknown }
    if (!Array.isArray(obj.history) || !Array.isArray(obj.inventory_status)) {
      setJsonError('El JSON debe incluir el historial y el estado del inventario. Usa la plantilla como guía.')
      return
    }
    setJsonError(null)
    if (historyTable) setHistRows(objectsToRows(historyTable.columns, obj.history as Record<string, unknown>[]))
    if (statusTable) setStatusRows(objectsToRows(statusTable.columns, obj.inventory_status as Record<string, unknown>[]))
    pred.reset()
  }

  const predict = () => {
    if (!historyTable || !statusTable) return
    const req = {
      history: coerceRows(historyTable.columns, histRows),
      inventory_status: coerceRows(statusTable.columns, statusRows),
    } as unknown as InventoryRequest
    pred.run(() => postInventory(req))
  }
  const onExcel = (file: File) => pred.run(() => uploadExcel<InventoryResponse>('inventory', file))

  return (
    <div className="space-y-5">
      <ModuleHeader view="inventory" />

      {loading && <p className="text-sm text-slate-500">Cargando…</p>}
      {error && <ErrorPanel error={error} />}

      {historyTable && statusTable && (
        <>
          {/* PASO 1 — Tus datos: súbelos en archivo o ingrésalos a mano, juntos. */}
          <StepSection
            step={1}
            title="Tus datos"
            accentChip={ACCENT.chip}
            description="Aporta el historial y el estado de tus existencias: sube un archivo o ingrésalos a mano."
          >
            <DataSourcePanel domain="inventory" onExcel={onExcel} onJson={onJson} busy={busy} accentSolid={ACCENT.solid} />

            <div className="flex items-center gap-3" aria-hidden="true">
              <span className="h-px flex-1 bg-slate-200" />
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">o ingrésalos a mano</span>
              <span className="h-px flex-1 bg-slate-200" />
            </div>

            <CatalogTable table={statusTable} rows={statusRows} onChange={setStatusRows} disabled={busy} />
            <CatalogTable table={historyTable} rows={histRows} onChange={setHistRows} disabled={busy} />

            {jsonError && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {jsonError}
              </p>
            )}
            {histRows.length > 0 && (
              <div>
                <p className="label">Resumen de tu historial</p>
                <HistoryPreview history={histRows} />
              </div>
            )}
          </StepSection>

          {/* No hay configuración de pronóstico aplicable en Almacén → se omite ese paso. */}

          {/* PASO 2 — Acción: revisar el riesgo de agotamiento con los datos cargados. */}
          <StepSection
            step={2}
            title="Revisa el riesgo de agotamiento"
            accentChip={ACCENT.chip}
            description="Con tus datos listos, identifica qué productos pueden agotarse y cuántas existencias conviene tener."
          >
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={`btn ${ACCENT.solid}`} onClick={predict} disabled={busy || !completo}>
                {busy ? 'Calculando…' : 'Revisar riesgo de agotamiento'}
              </button>
              {!completo && (
                <span className="text-sm text-slate-500" role="status">
                  Completa las filas obligatorias (marcadas con *), o sube un archivo.
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
          icon={Package}
          title="Aún no hay un análisis"
          message="Carga tus productos y su historial para ver cuáles tienen riesgo de agotarse y cuántas existencias conviene tener."
        />
      )}

      {pred.status === 'done' && pred.data && (
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-slate-800">Estado del inventario</h3>
          <ResultSummary text={resumenAlmacen(pred.data.alerts)} tone="bg-inventory-50 text-inventory-700" />
          <InventoryRisk alerts={pred.data.alerts} />
          <ResultTable columns={cols} rows={pred.data.alerts} />
          <TechnicalDetails>
            <p>Definición de demanda alta: {pred.data.metadata.threshold}</p>
            <p>
              Umbral de probabilidad:{' '}
              {pred.data.metadata.probability_threshold == null
                ? '—'
                : fmtNum(pred.data.metadata.probability_threshold)}
            </p>
            <p>«Segmento» (store_segment) y «clase de demanda» provienen de los artefactos del sistema.</p>
          </TechnicalDetails>
        </section>
      )}
    </div>
  )
}
