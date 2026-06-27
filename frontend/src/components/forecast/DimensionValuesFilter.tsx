/**
 * Multiselección de VALORES concretos de la dimensión (p. ej. categorías concretas).
 *
 * Honestidad: los valores NO salen del catálogo, sino del histórico real cargado; por
 * eso el control se **deshabilita** hasta que hay datos y muestra una explicación. Una
 * selección vacía significa "todas". Reutilizable por Compras/Almacén.
 */

export function DimensionValuesFilter({
  label,
  values,
  selected,
  onChange,
  disabled = false,
  disabledHint = 'Cargue un histórico para filtrar por valores concretos.',
}: {
  label: string
  values: string[]
  selected: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
  disabledHint?: string
}) {
  const inactive = disabled || values.length === 0
  const allSelected = selected.length === 0

  const toggle = (v: string) => {
    if (selected.includes(v)) onChange(selected.filter((x) => x !== v))
    else onChange([...selected, v])
  }

  return (
    <fieldset className="min-w-0" disabled={inactive}>
      <legend className="label">{label}</legend>
      {inactive ? (
        <p className="help">{disabledHint}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              aria-pressed={allSelected}
              onClick={() => onChange([])}
              className={`badge border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 ${
                allSelected
                  ? 'border-brand-200 bg-brand-50 text-brand-700'
                  : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              Todas
            </button>
            {values.map((v) => {
              const on = selected.includes(v)
              return (
                <button
                  key={v}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(v)}
                  className={`badge border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 ${
                    on
                      ? 'border-brand-200 bg-brand-50 text-brand-700'
                      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {v}
                </button>
              )
            })}
          </div>
          <p className="help">
            {allSelected
              ? `Todas las series (${values.length}).`
              : `${selected.length} de ${values.length} seleccionadas.`}
          </p>
        </>
      )}
    </fieldset>
  )
}
