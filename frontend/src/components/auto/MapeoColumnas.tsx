/**
 * Mapeo de columnas del motor agnóstico (Paso 2): elige target, fecha y claves de serie.
 * Compartido por Ventas, Almacén y Compras: solo cambian las etiquetas. Los menús se nutren
 * de helpers puros ({@link candidatasTarget}, {@link columnasFecha}, {@link candidatasSerie})
 * para no ofrecer opciones absurdas (fecha que no es fecha, flags como target…).
 */
import type { ColumnInfo } from '../../utils/inferSchema'
import { candidatasSerie, candidatasTarget, columnasFecha } from '../../utils/inferSchema'

export interface MapeoLabels {
  target: string
  targetHelp: string
  series: string
  seriesHelp: string
}

interface Props {
  cols: ColumnInfo[]
  target: string
  date: string
  series: string[]
  busy: boolean
  labels: MapeoLabels
  onTarget: (v: string) => void
  onDate: (v: string) => void
  onToggleSerie: (name: string) => void
}

export function MapeoColumnas({
  cols,
  target,
  date,
  series,
  busy,
  labels,
  onTarget,
  onDate,
  onToggleSerie,
}: Props) {
  const targets = candidatasTarget(cols, [date])
  const fechas = columnasFecha(cols)
  const series_ = candidatasSerie(cols, { excluir: [date, target] })

  return (
    <>
      <div>
        <label className="label" htmlFor="target" title="La cantidad numérica que el modelo aprende a predecir a futuro.">
          {labels.target}
        </label>
        <select id="target" className="input" value={target} disabled={busy} onChange={(e) => onTarget(e.target.value)}>
          {targets.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
        <p className="help">{labels.targetHelp}</p>
      </div>

      <div>
        <label className="label" htmlFor="date" title="La columna con la fecha de cada registro; ordena la serie en el tiempo.">
          Columna de fecha
        </label>
        <select id="date" className="input" value={date} disabled={busy} onChange={(e) => onDate(e.target.value)}>
          {fechas.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
        <p className="help">Cuándo ocurrió cada registro.</p>
      </div>

      <div>
        <span className="label" title="Columnas que identifican cada serie independiente (p. ej. tienda × producto). Se pronostica una por una.">
          {labels.series}
        </span>
        <div className="flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2">
          {series_.length === 0 && <span className="text-sm text-slate-400">Sin columnas de agrupación.</span>}
          {series_.map((c) => (
            <label key={c.name} className="inline-flex items-center gap-1 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={series.includes(c.name)}
                disabled={busy}
                onChange={() => onToggleSerie(c.name)}
              />
              {c.name}
              <span className="text-xs text-slate-400">({c.cardinality})</span>
            </label>
          ))}
        </div>
        <p className="help">{labels.seriesHelp}</p>
      </div>
    </>
  )
}
