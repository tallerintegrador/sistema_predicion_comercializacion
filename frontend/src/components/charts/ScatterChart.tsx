/**
 * Gráfico de dispersión "valor real vs. predicho" (A1).
 * - Eje X = valor REAL como escala numérica continua; eje Y = valor PREDICHO.
 * - Recta y = x (predicción perfecta): cuanto más cerca de ella, mejor la predicción.
 * - Ambos ejes comparten dominio para que la recta sea a 45° y la lectura sea literal.
 * - Leyenda arriba, separada del rótulo del eje X (sin solaparse).
 */
import {
  ScatterChart as RechartsScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'

interface Point {
  x: number
  y: number
  name?: string
}

interface ScatterChartProps {
  data: Point[]
  xLabel: string
  yLabel: string
  hex?: string
  showTrendline?: boolean
}

const fmtEje = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0, notation: 'compact' })

export function ScatterChart({ data, xLabel, yLabel, hex = '#4f46e5' }: ScatterChartProps) {
  if (data.length === 0) return null

  // Dominio compartido (real y predicho en la misma escala) con un pequeño margen.
  const vals = data.flatMap((p) => [p.x, p.y])
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const pad = (hi - lo) * 0.05 || 1
  const dominio: [number, number] = [lo - pad, hi + pad]

  return (
    <ResponsiveContainer width="100%" height={320}>
      <RechartsScatterChart margin={{ top: 28, right: 24, bottom: 44, left: 56 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          type="number"
          dataKey="x"
          domain={dominio}
          tickFormatter={(v) => fmtEje.format(Number(v))}
          tick={{ fontSize: 11 }}
          label={{ value: xLabel, position: 'insideBottom', offset: -12, fontSize: 12 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          domain={dominio}
          tickFormatter={(v) => fmtEje.format(Number(v))}
          tick={{ fontSize: 11 }}
          label={{ value: yLabel, angle: -90, position: 'insideLeft', offset: 4, fontSize: 12 }}
        />
        <Tooltip
          cursor={{ strokeDasharray: '3 3' }}
          formatter={(v: number, name) => [Number(v).toLocaleString('es-PE'), name === 'y' ? 'Predicho' : 'Real']}
        />
        <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
        {/* Recta y = x: predicción perfecta */}
        <ReferenceLine
          segment={[{ x: dominio[0], y: dominio[0] }, { x: dominio[1], y: dominio[1] }]}
          stroke="#94a3b8"
          strokeDasharray="5 5"
          ifOverflow="hidden"
          label={{ value: 'y = x (perfecto)', position: 'insideTopRight', fontSize: 11, fill: '#64748b' }}
        />
        <Scatter name="Casos (real vs. predicho)" data={data} fill={hex} fillOpacity={0.6} />
      </RechartsScatterChart>
    </ResponsiveContainer>
  )
}
