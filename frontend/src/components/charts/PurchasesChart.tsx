import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { RecommendationItem } from '../../api/types'

/** Barras por producto: punto de reorden vs. cantidad a reponer. */
export function PurchasesChart({ rows }: { rows: RecommendationItem[] }) {
  const data = useMemo(
    () =>
      rows.map((r) => ({
        label: `${r.store_id}·${r.product_id}`,
        reorder_point: r.reorder_point,
        replenishment_quantity: r.replenishment_quantity,
      })),
    [rows],
  )

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={56} />
          <Tooltip />
          <Legend />
          <Bar dataKey="reorder_point" name="Punto de reorden" fill="#94a3b8" />
          <Bar dataKey="replenishment_quantity" name="Cantidad a reponer" fill="#4f46e5" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
