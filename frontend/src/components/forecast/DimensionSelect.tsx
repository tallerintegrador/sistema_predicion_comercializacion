/**
 * Selector de DIMENSIÓN / FILTRAR POR (recomendación R2). Desplegable de la columna
 * por la que se desglosa/filtra el pronóstico. Las opciones llegan de `/catalog`
 * (query_options.dimensions, derivadas del bloque `history` del contrato); el
 * componente es agnóstico para que Compras y Almacén lo reutilicen.
 */
import type { ForecastDimension } from '../../api/types'

export function DimensionSelect({
  dimensions,
  value,
  onChange,
  disabled = false,
  label = 'Dimensión / Filtrar por',
  id = 'dimension',
}: {
  dimensions: ForecastDimension[]
  value: string
  onChange: (name: string) => void
  disabled?: boolean
  label?: string
  id?: string
}) {
  const current = dimensions.find((d) => d.name === value)
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="input"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {dimensions.map((d) => (
          <option key={d.name} value={d.name}>
            {d.label}
          </option>
        ))}
      </select>
      {current?.description && <p className="help">{current.description}</p>}
    </div>
  )
}
