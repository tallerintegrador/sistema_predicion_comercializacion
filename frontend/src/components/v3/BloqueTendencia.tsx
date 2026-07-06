/**
 * Bloque de análisis/tendencia (A3): la ÚNICA sección con línea temporal.
 * Muestra horizonte del pronóstico, histórico vs. pronóstico (franja sombreada),
 * un resumen numérico interpretativo, un filtro por categoría y una frase "cómo leer".
 */
import { useMemo, useState } from 'react'
import { SerieChart } from '../charts/SerieChart'
import { fmtValor } from '../../utils/format'
import type { TrendAnalysis } from '../../api/types'

interface BloqueTendenciaProps {
  bloque: TrendAnalysis
  accentHex: string
}

function Tarjeta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-bold text-slate-800">{children}</div>
    </div>
  )
}

export function BloqueTendencia({ bloque, accentHex }: BloqueTendenciaProps) {
  const { title, description, unit, method, horizon, history, forecast, summary, breakdowns } = bloque
  const [cat, setCat] = useState('__all__')
  const hayFiltro = (breakdowns ?? []).length > 0

  const activo = useMemo(() => {
    if (cat === '__all__') return { history, forecast }
    const b = (breakdowns ?? []).find((x) => x.label === cat)
    return b ? { history: b.history, forecast: b.forecast } : { history, forecast }
  }, [cat, history, forecast, breakdowns])

  const hist = (activo.history ?? []).map((p) => ({ date: p.date, value: p.value }))
  const fore = (activo.forecast ?? []).map((p) => ({ date: p.date, value: p.value }))
  const hayDatos = hist.length > 0 || fore.length > 0
  const foreStart = fore[0]?.date

  const dir = summary?.direction
  const dirLabel = dir === 'creciente' ? '↗ creciente' : dir === 'decreciente' ? '↘ decreciente' : '→ estable'
  const dirColor = dir === 'creciente' ? 'text-emerald-600' : dir === 'decreciente' ? 'text-rose-600' : 'text-slate-500'
  const chg = summary?.change_pct ?? 0

  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">📈 {title || 'Análisis / Tendencia'}</h2>
          <p className="text-sm text-slate-500 mt-1">{description}</p>
        </div>
        {hayFiltro && (
          <label className="text-xs text-slate-500">
            Filtrar:{' '}
            <select
              value={cat}
              onChange={(e) => setCat(e.target.value)}
              className="rounded-md border border-slate-200 px-2 py-1 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            >
              <option value="__all__">Todo el negocio</option>
              {(breakdowns ?? []).map((b) => (
                <option key={b.label} value={b.label}>{b.label}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* Resumen numérico interpretativo (solo para el total) */}
      {summary && cat === '__all__' && (
        <div className="grid gap-2 sm:grid-cols-3">
          <Tarjeta label={`Proyección próximos ${horizon} días`}>{fmtValor(summary.projection, unit)}</Tarjeta>
          <Tarjeta label="vs. período reciente">
            <span className={chg >= 0 ? 'text-emerald-600' : 'text-rose-600'}>
              {chg >= 0 ? '+' : ''}{chg}%
            </span>
          </Tarjeta>
          <Tarjeta label="Tendencia (con estacionalidad)"><span className={dirColor}>{dirLabel}</span></Tarjeta>
        </div>
      )}

      {hayDatos ? (
        <>
          <SerieChart
            history={hist}
            forecast={fore}
            histLabel={`Histórico (${unit || 'total'})`}
            foreLabel={`Pronóstico a ${horizon} días`}
            hex={accentHex}
            forecastStart={foreStart}
          />
          <p className="text-xs text-slate-400">
            Cómo leer esto: la línea gris es lo que ya ocurrió; la <b>franja sombreada</b> a la derecha es el
            pronóstico a <b>{horizon} días</b> ({method}). Es una referencia orientativa, no una garantía.
          </p>
        </>
      ) : (
        <p className="text-sm text-slate-500 italic">
          Aún no hay suficiente historial por fecha para dibujar la tendencia.
        </p>
      )}
    </section>
  )
}
