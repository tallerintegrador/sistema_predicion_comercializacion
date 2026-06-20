import { useState } from 'react'
import { postInventory, uploadExcel } from '../api/endpoints'
import type { AlertItem, InventoryRequest, InventoryResponse, InventoryStatusItem } from '../api/types'
import { sampleInventory } from '../data/samples'
import { usePrediction } from '../hooks/usePrediction'
import { ErrorPanel } from '../components/ErrorPanel'
import { ExcelPanel } from '../components/ExcelPanel'
import { HistoryPreview } from '../components/HistoryPreview'
import { JobBanner } from '../components/JobBanner'
import { MetadataPanel } from '../components/MetadataPanel'
import { ParamsEditor } from '../components/ParamsEditor'
import type { FieldDef } from '../components/ParamsEditor'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { InventoryRisk } from '../components/charts/InventoryRisk'
import { fmtNum, fmtPct } from '../utils/format'

const emptyReq: InventoryRequest = { history: [], inventory_status: [] }

const paramFields: FieldDef<InventoryStatusItem>[] = [
  { key: 'store_id', label: 'Tienda', type: 'text' },
  { key: 'product_id', label: 'Producto', type: 'text' },
  { key: 'current_stock', label: 'Stock actual', type: 'number' },
  { key: 'lead_time_days', label: 'Lead time (días)', type: 'number', optional: true },
]

const makeEmptyStatus = (): InventoryStatusItem => ({
  store_id: '',
  product_id: '',
  current_stock: 0,
  lead_time_days: null,
})

const cols: Column<AlertItem>[] = [
  { header: 'Tienda', render: (r) => r.store_id },
  { header: 'Producto', render: (r) => r.product_id },
  { header: 'Clase', render: (r) => r.demand_class },
  { header: 'Prob. alta', align: 'right', render: (r) => fmtPct(r.high_demand_probability) },
  { header: 'Quiebre', render: (r) => (r.stockout_risk ? 'sí' : 'no') },
  { header: 'Stock recom.', align: 'right', render: (r) => fmtNum(r.recommended_stock) },
  { header: 'Stock seguridad', align: 'right', render: (r) => fmtNum(r.safety_stock) },
  { header: 'Segmento', align: 'right', render: (r) => r.store_segment },
]

export function InventoryPage() {
  const [req, setReq] = useState<InventoryRequest>(emptyReq)
  const pred = usePrediction<InventoryResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  const loadSample = () => {
    setReq(sampleInventory)
    pred.reset()
  }
  const predict = () => pred.run(() => postInventory(req))
  const onExcel = (file: File) => pred.run(() => uploadExcel<InventoryResponse>('inventory', file))

  return (
    <div className="space-y-5">
      <section className="card">
        <h2 className="text-lg font-semibold text-slate-800">Riesgo de quiebre y stock (INVENTORY)</h2>
        <p className="mt-1 text-sm text-slate-500">
          Predice la clase de demanda y su probabilidad, marca el riesgo de quiebre y recomienda un stock objetivo con segmento de tienda.
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="btn-ghost" onClick={loadSample}>Cargar ejemplo</button>
          <button
            className="btn-primary"
            onClick={predict}
            disabled={busy || req.history.length === 0 || req.inventory_status.length === 0}
          >
            Predecir
          </button>
          <HistoryPreview history={req.history} />
        </div>

        <div className="mt-4">
          <ParamsEditor
            title="inventory_status"
            rows={req.inventory_status}
            fields={paramFields}
            makeEmpty={makeEmptyStatus}
            onChange={(rows) => setReq({ ...req, inventory_status: rows })}
          />
        </div>
      </section>

      <ExcelPanel domain="inventory" onUpload={onExcel} busy={busy} />

      <JobBanner status={pred.status} jobId={pred.jobId} attempts={pred.attempts} />
      {pred.status === 'error' && pred.error && <ErrorPanel error={pred.error} />}

      {pred.status === 'done' && pred.data && (
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-slate-800">Alertas</h3>
          <InventoryRisk alerts={pred.data.alerts} />
          <ResultTable columns={cols} rows={pred.data.alerts} />
          <MetadataPanel
            entries={[
              { label: 'threshold', value: <span className="text-xs">{pred.data.metadata.threshold}</span> },
              {
                label: 'probability_threshold',
                value: pred.data.metadata.probability_threshold == null ? '—' : fmtNum(pred.data.metadata.probability_threshold),
              },
            ]}
            notes={['Combina clasificación (demanda alta/baja) y clustering (segmento de tienda) bajo el contrato.']}
          />
        </section>
      )}
    </div>
  )
}
