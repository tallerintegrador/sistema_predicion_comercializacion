import { useState } from 'react'
import { postPurchases, uploadExcel } from '../api/endpoints'
import type { PurchasesRequest, PurchasesResponse, RecommendationItem, ReplenishmentParam } from '../api/types'
import { samplePurchases } from '../data/samples'
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
import { PurchasesChart } from '../components/charts/PurchasesChart'
import { fmtNum } from '../utils/format'

const emptyReq: PurchasesRequest = { history: [], replenishment_params: [] }

const paramFields: FieldDef<ReplenishmentParam>[] = [
  { key: 'store_id', label: 'Tienda', type: 'text' },
  { key: 'product_id', label: 'Producto', type: 'text' },
  { key: 'current_stock', label: 'Stock actual', type: 'number' },
  { key: 'lead_time_days', label: 'Lead time (días)', type: 'number' },
  { key: 'target_coverage_days', label: 'Cobertura (días)', type: 'number' },
]

const makeEmptyParam = (): ReplenishmentParam => ({
  store_id: '',
  product_id: '',
  current_stock: 0,
  lead_time_days: 7,
  target_coverage_days: 7,
})

const cols: Column<RecommendationItem>[] = [
  { header: 'Tienda', render: (r) => r.store_id },
  { header: 'Producto', render: (r) => r.product_id },
  { header: 'Demanda horizonte', align: 'right', render: (r) => fmtNum(r.expected_demand_horizon) },
  { header: 'Punto de reorden', align: 'right', render: (r) => fmtNum(r.reorder_point) },
  { header: 'Cantidad a reponer', align: 'right', render: (r) => fmtNum(r.replenishment_quantity) },
  { header: 'Justificación', render: (r) => <span className="text-xs text-slate-500">{r.justification}</span> },
]

export function PurchasesPage() {
  const [req, setReq] = useState<PurchasesRequest>(emptyReq)
  const pred = usePrediction<PurchasesResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  const loadSample = () => {
    setReq(samplePurchases)
    pred.reset()
  }
  const predict = () => pred.run(() => postPurchases(req))
  const onExcel = (file: File) => pred.run(() => uploadExcel<PurchasesResponse>('purchases', file))

  return (
    <div className="space-y-5">
      <section className="card">
        <h2 className="text-lg font-semibold text-slate-800">Reposición sugerida (PURCHASES)</h2>
        <p className="mt-1 text-sm text-slate-500">
          Deriva, por producto, la demanda esperada en la ventana de cobertura, el punto de reorden y la cantidad a reponer.
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="btn-ghost" onClick={loadSample}>Cargar ejemplo</button>
          <button
            className="btn-primary"
            onClick={predict}
            disabled={busy || req.history.length === 0 || req.replenishment_params.length === 0}
          >
            Predecir
          </button>
          <HistoryPreview history={req.history} />
        </div>

        <div className="mt-4">
          <ParamsEditor
            title="replenishment_params"
            rows={req.replenishment_params}
            fields={paramFields}
            makeEmpty={makeEmptyParam}
            onChange={(rows) => setReq({ ...req, replenishment_params: rows })}
          />
        </div>
      </section>

      <ExcelPanel domain="purchases" onUpload={onExcel} busy={busy} />

      <JobBanner status={pred.status} jobId={pred.jobId} attempts={pred.attempts} />
      {pred.status === 'error' && pred.error && <ErrorPanel error={pred.error} />}

      {pred.status === 'done' && pred.data && (
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
          <PurchasesChart rows={pred.data.recommendation} />
          <ResultTable columns={cols} rows={pred.data.recommendation} />
          <MetadataPanel
            entries={[
              { label: 'policy', value: pred.data.metadata.policy ?? '—' },
              { label: 'assumption', value: pred.data.metadata.assumption },
            ]}
            notes={['PURCHASES no tiene modelo propio: reutiliza el pronóstico de SALES + parámetros logísticos.']}
          />
        </section>
      )}
    </div>
  )
}
