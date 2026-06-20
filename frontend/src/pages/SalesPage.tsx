import { useState } from 'react'
import { postSales, uploadExcel } from '../api/endpoints'
import type { Granularity, SalesRequest, SalesResponse } from '../api/types'
import { sampleSales } from '../data/samples'
import { usePrediction } from '../hooks/usePrediction'
import { ErrorPanel } from '../components/ErrorPanel'
import { ExcelPanel } from '../components/ExcelPanel'
import { HistoryPreview } from '../components/HistoryPreview'
import { JobBanner } from '../components/JobBanner'
import { MetadataPanel } from '../components/MetadataPanel'
import { ResultTable } from '../components/ResultTable'
import type { Column } from '../components/ResultTable'
import { SalesChart } from '../components/charts/SalesChart'
import { fmtNum } from '../utils/format'
import type { ForecastItem } from '../api/types'

const emptyReq: SalesRequest = { granularity: 'day', horizon: 7, history: [] }

const forecastCols: Column<ForecastItem>[] = [
  { header: 'Fecha', render: (r) => r.date },
  { header: 'Tienda', render: (r) => r.store_id },
  { header: 'Producto', render: (r) => r.product_id },
  { header: 'Pronóstico', align: 'right', render: (r) => fmtNum(r.forecast_demand) },
  {
    header: 'interval_80',
    render: () => <span className="text-xs text-slate-400">diferido</span>,
  },
]

export function SalesPage() {
  const [req, setReq] = useState<SalesRequest>(emptyReq)
  const pred = usePrediction<SalesResponse>()
  const busy = pred.status === 'loading' || pred.status === 'polling'

  const loadSample = () => {
    setReq(sampleSales)
    pred.reset()
  }
  const predict = () => pred.run(() => postSales(req))
  const onExcel = (file: File) => pred.run(() => uploadExcel<SalesResponse>('sales', file))

  return (
    <div className="space-y-5">
      <section className="card">
        <h2 className="text-lg font-semibold text-slate-800">Pronóstico de demanda (SALES)</h2>
        <p className="mt-1 text-sm text-slate-500">
          Estima la demanda futura por período, tienda y producto a partir del histórico de ventas.
        </p>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="label" htmlFor="granularity">Granularidad</label>
            <select
              id="granularity"
              className="input"
              value={req.granularity}
              onChange={(e) => setReq({ ...req, granularity: e.target.value as Granularity })}
            >
              <option value="day">day</option>
              <option value="week">week</option>
              <option value="month">month</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="horizon">Horizonte (1–365)</label>
            <input
              id="horizon"
              type="number"
              min={1}
              max={365}
              className="input w-32"
              value={req.horizon}
              onChange={(e) => setReq({ ...req, horizon: Number(e.target.value) })}
            />
          </div>
          <button className="btn-ghost" onClick={loadSample}>Cargar ejemplo</button>
          <button className="btn-primary" onClick={predict} disabled={busy || req.history.length === 0}>
            Predecir
          </button>
        </div>

        <div className="mt-4">
          <HistoryPreview history={req.history} />
          {req.history.length === 0 && (
            <p className="mt-2 text-sm text-slate-400">
              Carga el ejemplo o sube un Excel para tener histórico.
            </p>
          )}
        </div>
      </section>

      <ExcelPanel domain="sales" onUpload={onExcel} busy={busy} />

      <JobBanner status={pred.status} jobId={pred.jobId} attempts={pred.attempts} />
      {pred.status === 'error' && pred.error && <ErrorPanel error={pred.error} />}

      {pred.status === 'done' && pred.data && (
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-slate-800">
            Resultado · modelo <code className="rounded bg-slate-100 px-1 text-sm">{pred.data.model}</code>
          </h3>
          <SalesChart history={req.history} forecast={pred.data.forecast} />
          <ResultTable columns={forecastCols} rows={pred.data.forecast} />
          <MetadataPanel
            entries={[
              { label: 'model', value: pred.data.model },
              { label: 'scale', value: pred.data.metadata.scale },
              { label: 'internal_transform', value: pred.data.metadata.internal_transform },
            ]}
            notes={['interval_80: no disponible (diferido) — el modelo aún no produce intervalos de predicción.']}
          />
        </section>
      )}
    </div>
  )
}
