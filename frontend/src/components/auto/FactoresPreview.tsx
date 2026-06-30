/**
 * Vista previa de los **factores** (Paso 2): las columnas que no son target/fecha/serie pasan
 * a `features`. Cada chip muestra si la columna se conoce **a futuro** (precio, calendario…)
 * o es **solo del pasado** (rezagos ``*_prev``). El usuario puede alternarlo: marcar mal un
 * rezago como «a futuro» sería fuga de datos, así que dejarlo visible y editable importa.
 */
import type { ColumnInfo } from '../../utils/inferSchema'
import { esConocidaFutura } from '../../utils/inferSchema'

interface Props {
  cols: ColumnInfo[]
  reservadas: string[] // target, fecha y claves de serie (no son factores)
  futureOverrides: Record<string, boolean>
  busy: boolean
  onToggleFuture: (name: string) => void
}

export function FactoresPreview({ cols, reservadas, futureOverrides, busy, onToggleFuture }: Props) {
  const reserv = new Set(reservadas)
  const factores = cols.filter((c) => !reserv.has(c.name) && c.kind !== 'date')
  if (factores.length === 0) return null

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-sm font-medium text-slate-700">
        Factores ({factores.length}) — el resto de columnas que el modelo usa como pistas
      </p>
      <p className="mt-0.5 text-xs text-slate-500">
        «A futuro» = su valor se conoce de antemano (precio, promo, feriado). «Solo pasado» = solo
        se mide después (rezagos, tráfico). Pulsa un chip para cambiarlo.
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {factores.map((c) => {
          const known = futureOverrides[c.name] ?? esConocidaFutura(c.name)
          return (
            <button
              key={c.name}
              type="button"
              disabled={busy}
              onClick={() => onToggleFuture(c.name)}
              title={known ? 'Conocida a futuro — clic para marcar solo pasado' : 'Solo pasado — clic para marcar conocida a futuro'}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition disabled:opacity-50 ${
                known
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                  : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
              }`}
            >
              {c.name}
              <span className="opacity-70">{known ? 'a futuro' : 'solo pasado'}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
