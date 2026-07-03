/**
 * Bloque de análisis/tendencia: la ÚNICA sección con línea temporal.
 * Dibuja histórico + pronóstico referencial del total diario de la magnitud principal.
 */
import { SerieChart } from '../charts/SerieChart'
import type { BloqueAnalisisTendencia } from '../../api/types'

interface BloqueTendenciaProps {
  bloque: BloqueAnalisisTendencia
  accentHex: string
}

export function BloqueTendencia({ bloque, accentHex }: BloqueTendenciaProps) {
  const { titulo, descripcion, unidad, metodo, historico, pronostico } = bloque

  const hist = (historico ?? []).map((p) => ({ date: p.fecha, value: p.valor }))
  const fore = (pronostico ?? []).map((p) => ({ date: p.fecha, value: p.valor }))
  const hayDatos = hist.length > 0 || fore.length > 0

  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-bold text-slate-800">📈 {titulo || 'Análisis / Tendencia'}</h2>
        <p className="text-sm text-slate-500 mt-1">{descripcion}</p>
      </div>

      {hayDatos ? (
        <>
          <SerieChart
            history={hist}
            forecast={fore}
            histLabel={`Histórico (${unidad || 'total'})`}
            foreLabel="Pronóstico (referencial)"
            hex={accentHex}
          />
          {metodo && (
            <p className="text-xs text-slate-400">
              Método: {metodo}. El pronóstico es una referencia orientativa, no una garantía.
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-500 italic">
          Aún no hay suficiente historial por fecha para dibujar la tendencia.
        </p>
      )}
    </section>
  )
}
