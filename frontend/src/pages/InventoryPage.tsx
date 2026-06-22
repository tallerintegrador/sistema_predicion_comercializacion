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
import { ReuseHistoryNotice } from '../components/data/ReuseHistoryNotice'
import { JobBanner } from '../components/JobBanner'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { InventoryRisk } from '../components/charts/InventoryRisk'
import { ResultFilters } from '../components/result/ResultFilters'
import { useResultFilters } from '../hooks/useResultFilters'
import type { ResultFiltersSpec } from '../hooks/useResultFilters'
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
          {/* PASO 1 — Tus datos: historial SIEMPRE por archivo; estado del inventario a mano o por archivo. */}
          <StepSection
            step={1}
            title="Tus datos"
            accentChip={ACCENT.chip}
            description="Sube tu historial de ventas por archivo y añade el estado de tus existencias."
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
              <DataSourcePanel domain="inventory" onExcel={onExcel} onJson={onJson} busy={busy} accentSolid={ACCENT.solid} />
              <ReuseHistoryNotice />
              {histRows.length > 0 && (
                <div>
                  <p className="label">Resumen de tu historial</p>
                  <HistoryPreview history={histRows} />
                </div>
              )}
            </div>

            <div className="my-2 h-px bg-slate-200" aria-hidden="true" />

            {/* Estado del inventario: lista corta del estado actual; se puede ingresar a mano. */}
            <CatalogTable table={statusTable} rows={statusRows} onChange={setStatusRows} disabled={busy} />

            {jsonError && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {jsonError}
              </p>
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
                  Sube tu historial de ventas (Excel o JSON) y completa el estado del inventario
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
          icon={Package}
          title="Aún no hay un análisis"
          message="Carga tus productos y su historial para ver cuáles tienen riesgo de agotarse y cuántas existencias conviene tener."
        />
      )}

      {pred.status === 'done' && pred.data && <InventoryResult data={pred.data} />}
    </div>
  )
}

/** Resultado de Almacén con filtros derivados de los campos reales de la respuesta. */
function InventoryResult({ data }: { data: InventoryResponse }) {
  const rows = data.alerts

  const spec = useMemo<ResultFiltersSpec<AlertItem>>(
    () => ({
      facets: [
        { key: 'store_id', label: 'Tienda', read: (r) => r.store_id },
        { key: 'product_id', label: 'Producto', read: (r) => r.product_id },
        {
          key: 'store_segment',
          label: 'Segmento de tienda',
          read: (r) => String(r.store_segment),
          display: (v) => `Segmento ${v}`,
        },
      ],
      toggles: [
        {
          key: 'risk',
          label: 'Solo los que están en riesgo de agotarse',
          predicate: (r) => r.stockout_risk,
        },
      ],
      sorts: [
        {
          key: 'risk',
          label: 'Riesgo (mayor primero)',
          compare: (a, b) =>
            Number(b.stockout_risk) - Number(a.stockout_risk) ||
            b.high_demand_probability - a.high_demand_probability,
        },
        {
          key: 'store',
          label: 'Tienda y producto',
          compare: (a, b) =>
            a.store_id.localeCompare(b.store_id, 'es', { numeric: true }) ||
            a.product_id.localeCompare(b.product_id, 'es', { numeric: true }),
        },
      ],
    }),
    [],
  )

  const filters = useResultFilters(rows, spec)
  const { filtered } = filters

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Estado del inventario</h3>
      <ResultSummary text={resumenAlmacen(filtered)} tone="bg-inventory-50 text-inventory-700" />
      <ResultFilters
        spec={spec}
        filters={filters}
        comingSoon={[
          {
            key: 'level',
            label: 'Nivel de riesgo (alto/medio/bajo)',
            hint: 'Disponible cuando el sistema entregue el nivel de riesgo en niveles.',
          },
          {
            key: 'category',
            label: 'Categoría / familia',
            hint: 'Disponible cuando el sistema indique la categoría o familia de cada producto.',
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
          <InventoryRisk alerts={filtered} />
          <ResultTable columns={cols} rows={filtered} />
        </>
      ) : (
        <p className="text-sm text-slate-500">No hay productos que cumplan los filtros seleccionados.</p>
      )}
      <TechnicalDetails>
        <p>Definición de demanda alta: {data.metadata.threshold}</p>
        <p>
          Umbral de probabilidad:{' '}
          {data.metadata.probability_threshold == null
            ? '—'
            : fmtNum(data.metadata.probability_threshold)}
        </p>
        <p>«Segmento» (store_segment) y «clase de demanda» provienen de los artefactos del sistema.</p>
      </TechnicalDetails>
    </section>
  )
}
