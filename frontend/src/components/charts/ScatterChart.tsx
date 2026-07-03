/**
 * Gráfico de dispersión con línea de tendencia (regresión lineal simple).
 * Útil para ilustrar relaciones entre factores en reportes de regresión.
 */
import {
  ScatterChart as RechartsScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Line,
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

/** Calcula la línea de tendencia (mínimos cuadrados) para los puntos. */
function calculateTrendline(points: Point[]): { slope: number; intercept: number } {
  if (points.length < 2) return { slope: 0, intercept: 0 }

  const n = points.length
  let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0

  for (const p of points) {
    sumX += p.x
    sumY += p.y
    sumXY += p.x * p.y
    sumX2 += p.x * p.x
  }

  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX)
  const intercept = (sumY - slope * sumX) / n

  return { slope, intercept }
}

export function ScatterChart({
  data,
  xLabel,
  yLabel,
  hex = '#4f46e5',
  showTrendline = true,
}: ScatterChartProps) {
  if (data.length === 0) return null

  const trendline = showTrendline ? calculateTrendline(data) : null
  const trendlineData =
    trendline && data.length >= 2
      ? [
          {
            x: Math.min(...data.map((p) => p.x)),
            y: trendline.intercept + trendline.slope * Math.min(...data.map((p) => p.x)),
          },
          {
            x: Math.max(...data.map((p) => p.x)),
            y: trendline.intercept + trendline.slope * Math.max(...data.map((p) => p.x)),
          },
        ]
      : null

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RechartsScatterChart margin={{ top: 20, right: 20, bottom: 60, left: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="x" label={{ value: xLabel, position: 'bottom', offset: 10 }} />
        <YAxis label={{ value: yLabel, angle: -90, position: 'insideLeft' }} />
        <Tooltip cursor={{ strokeDasharray: '3 3' }} />
        {data.length > 1 && <Legend />}
        <Scatter name="Datos" data={data} fill={hex} />
        {trendlineData && (
          <Line
            type="monotone"
            dataKey="y"
            data={trendlineData}
            stroke={hex}
            strokeDasharray="5 5"
            dot={false}
            isAnimationActive={false}
            name="Tendencia"
          />
        )}
      </RechartsScatterChart>
    </ResponsiveContainer>
  )
}
