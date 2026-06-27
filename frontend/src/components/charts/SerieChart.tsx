import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fmtDate } from '../../utils/format'

interface Punto {
  date: string
  historico?: number
  pronostico?: number
}

/**
 * Línea de tiempo genérica: valor observado (histórico) vs. pronóstico, agregando por fecha.
 * A diferencia de `SalesChart`, las etiquetas de la leyenda llegan por prop, porque el motor
 * agnóstico de Ventas pronostica cualquier objetivo (unidades, ingresos…) y el texto debe
 * reflejarlo.
 */
export function SerieChart({
  history,
  forecast,
  histLabel,
  foreLabel,
  hex = '#4f46e5',
}: {
  history: { date: string; value: number }[]
  forecast: { date: string; value: number }[]
  histLabel: string
  foreLabel: string
  hex?: string
}) {
  const data = useMemo<Punto[]>(() => {
    const byDate = new Map<string, Punto>()
    for (const h of history) {
      const d = fmtDate(h.date)
      const p = byDate.get(d) ?? { date: d }
      p.historico = (p.historico ?? 0) + h.value
      byDate.set(d, p)
    }
    for (const f of forecast) {
      const d = fmtDate(f.date)
      const p = byDate.get(d) ?? { date: d }
      p.pronostico = (p.pronostico ?? 0) + f.value
      byDate.set(d, p)
    }
    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date))
  }, [history, forecast])

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} width={56} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="historico" name={histLabel} stroke="#64748b" dot={false} strokeWidth={2} connectNulls />
          <Line type="monotone" dataKey="pronostico" name={foreLabel} stroke={hex} dot={false} strokeWidth={2} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
