import type { AlertItem } from '../../api/types'
import { fmtNum, fmtPct } from '../../utils/format'

/** Tarjetas de riesgo por alerta de inventario (clase, probabilidad, quiebre). */
export function InventoryRisk({ alerts }: { alerts: AlertItem[] }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {alerts.map((a, i) => (
        <div key={i} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium text-slate-800">
              {a.store_id} · {a.product_id}
            </span>
            <span className={`badge ${a.demand_class === 'high' ? 'bg-indigo-100 text-indigo-800' : 'bg-slate-100 text-slate-600'}`}>
              demanda {a.demand_class}
            </span>
          </div>

          <div className="mt-3">
            <div className="mb-1 flex justify-between text-xs text-slate-500">
              <span>Prob. demanda alta</span>
              <span className="font-medium text-slate-700">{fmtPct(a.high_demand_probability)}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full bg-indigo-500"
                style={{ width: `${Math.round(a.high_demand_probability * 100)}%` }}
              />
            </div>
          </div>

          <div className="mt-3 flex items-center gap-2">
            <span className={`badge ${a.stockout_risk ? 'bg-red-100 text-red-800' : 'bg-emerald-100 text-emerald-800'}`}>
              {a.stockout_risk ? '⚠ Riesgo de quiebre' : '✓ Sin riesgo'}
            </span>
            <span className="badge bg-slate-100 text-slate-600">segmento {a.store_segment}</span>
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <Stat label="Stock recomendado" value={fmtNum(a.recommended_stock)} />
            <Stat label="Stock de seguridad" value={fmtNum(a.safety_stock)} />
          </dl>
        </div>
      ))}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-slate-100 pb-0.5">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  )
}
