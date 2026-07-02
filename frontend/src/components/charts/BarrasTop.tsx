import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

/**
 * Barras horizontales para un "Top N": las entidades (productos) con mayor valor
 * previsto en el horizonte. Muy visual para la demo (qué se venderá/pedirá más).
 */
export function BarrasTop({
  data,
  hex = '#4f46e5',
  valorLabel = 'Total previsto',
}: {
  data: { nombre: string; valor: number }[]
  hex?: string
  valorLabel?: string
}) {
  if (data.length === 0) return null
  return (
    <div className="w-full" style={{ height: Math.max(160, data.length * 30 + 40) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="nombre" tick={{ fontSize: 11 }} width={120} />
          <Tooltip />
          <Bar dataKey="valor" name={valorLabel} fill={hex} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
