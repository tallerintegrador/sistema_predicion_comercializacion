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
import type { ForecastItem, HistoryItem } from '../../api/types'
import { fmtDate } from '../../utils/format'

interface Point {
  date: string
  historico?: number
  pronostico?: number
}

/**
 * Línea de tiempo: demanda observada (history) vs. pronóstico (forecast).
 * Cuando hay varias series (tienda×producto), agrega por fecha sumando.
 */
export function SalesChart({
  history,
  forecast,
}: {
  history: HistoryItem[]
  forecast: ForecastItem[]
}) {
  const data = useMemo<Point[]>(() => {
    const byDate = new Map<string, Point>()
    for (const h of history) {
      const d = fmtDate(h.date)
      const p = byDate.get(d) ?? { date: d }
      p.historico = (p.historico ?? 0) + h.units_sold
      byDate.set(d, p)
    }
    for (const f of forecast) {
      const d = fmtDate(f.date)
      const p = byDate.get(d) ?? { date: d }
      p.pronostico = (p.pronostico ?? 0) + f.forecast_demand
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
          <Line
            type="monotone"
            dataKey="historico"
            name="Histórico (units_sold)"
            stroke="#64748b"
            dot={false}
            strokeWidth={2}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="pronostico"
            name="Pronóstico (forecast_demand)"
            stroke="#4f46e5"
            dot={false}
            strokeWidth={2}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
