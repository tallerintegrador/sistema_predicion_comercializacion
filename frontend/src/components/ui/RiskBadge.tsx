import type { AlertItem } from '../../api/types'

/**
 * Semáforo de riesgo de agotamiento (ADR-0019/0020). Traduce los campos técnicos
 * (`stockout_risk`, `demand_class`) a una etiqueta clara con color, sin tecnicismos.
 */
export function RiskBadge({ alert }: { alert: AlertItem }) {
  const { label, cls, dot } = clasificar(alert)
  return (
    <span className={`badge gap-1.5 ${cls}`}>
      <span aria-hidden="true">{dot}</span>
      {label}
    </span>
  )
}

function clasificar(a: AlertItem): { label: string; cls: string; dot: string } {
  if (a.stockout_risk) {
    return { label: 'Riesgo de agotarse', cls: 'bg-red-100 text-red-800', dot: '🔴' }
  }
  if (a.demand_class === 'high') {
    return { label: 'Vigilar (demanda alta)', cls: 'bg-amber-100 text-amber-800', dot: '🟡' }
  }
  return { label: 'Existencias estables', cls: 'bg-emerald-100 text-emerald-800', dot: '🟢' }
}
