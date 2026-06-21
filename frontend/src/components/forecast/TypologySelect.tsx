/**
 * Selector de TIPO DE PRONÓSTICO (recomendación R1). Control segmentado accesible
 * (radiogroup con navegación por teclado). Las opciones llegan de `/catalog`
 * (query_options.typologies); este componente no conoce su contenido, así Compras y
 * Almacén pueden reutilizarlo tal cual.
 */
import type { ForecastTypology } from '../../api/types'

export function TypologySelect({
  typologies,
  value,
  onChange,
  disabled = false,
  label = 'Tipo de pronóstico',
  id = 'typology',
}: {
  typologies: ForecastTypology[]
  value: string
  onChange: (name: string) => void
  disabled?: boolean
  label?: string
  id?: string
}) {
  const current = typologies.find((t) => t.name === value)
  const index = typologies.findIndex((t) => t.name === value)

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled || typologies.length === 0) return
    const dir =
      e.key === 'ArrowRight' || e.key === 'ArrowDown'
        ? 1
        : e.key === 'ArrowLeft' || e.key === 'ArrowUp'
          ? -1
          : 0
    if (dir === 0) return
    e.preventDefault()
    const next = (index + dir + typologies.length) % typologies.length
    onChange(typologies[next].name)
  }

  return (
    <div>
      <span className="label" id={`${id}-label`}>
        {label}
      </span>
      <div className="segmented" role="radiogroup" aria-labelledby={`${id}-label`} onKeyDown={onKeyDown}>
        {typologies.map((t) => (
          <button
            key={t.name}
            type="button"
            role="radio"
            aria-checked={t.name === value}
            tabIndex={t.name === value ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(t.name)}
            className="segmented-option"
            title={t.description}
          >
            {t.label}
          </button>
        ))}
      </div>
      {current && <p className="help">{current.description}</p>}
    </div>
  )
}
