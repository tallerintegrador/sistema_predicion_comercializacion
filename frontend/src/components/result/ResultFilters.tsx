import { ComingSoon } from '../ui/ComingSoon'
import type { ResultFiltersSpec, ResultFiltersState } from '../../hooks/useResultFilters'

/** Un control planificado: se muestra deshabilitado y rotulado «Próximamente» (nunca simula). */
export interface ComingSoonControl {
  key: string
  label: string
  hint?: string
}

/**
 * Barra de filtros de una tabla de resultado (Compras/Almacén). Solo expone lo que el backend
 * entrega hoy (campos presentes en la respuesta); lo que falta se muestra aparte, deshabilitado
 * y con «Próximamente», de forma honesta (ver docs/alineacion_frontend_backend.md).
 */
export function ResultFilters<T>({
  spec,
  filters,
  comingSoon = [],
}: {
  spec: ResultFiltersSpec<T>
  filters: ResultFiltersState<T>
  comingSoon?: ComingSoonControl[]
}) {
  const { options, facets, setFacet, toggles, setToggle, sort, setSort } = filters
  const facetDefs = spec.facets ?? []
  const toggleDefs = spec.toggles ?? []
  const sortDefs = spec.sorts ?? []

  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      {facetDefs.map((f) => (
        <div key={f.key}>
          <label className="label" htmlFor={`filtro-${f.key}`}>
            {f.label}
          </label>
          <select
            id={`filtro-${f.key}`}
            className="input"
            value={facets[f.key] ?? ''}
            onChange={(e) => setFacet(f.key, e.target.value)}
          >
            <option value="">Todos</option>
            {(options[f.key] ?? []).map((v) => (
              <option key={v} value={v}>
                {f.display ? f.display(v) : v}
              </option>
            ))}
          </select>
        </div>
      ))}

      {sortDefs.length > 0 && (
        <div>
          <label className="label" htmlFor="filtro-orden">
            Ordenar por
          </label>
          <select
            id="filtro-orden"
            className="input"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            {sortDefs.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {toggleDefs.map((t) => (
        <label key={t.key} className="inline-flex items-center gap-2 pb-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={!!toggles[t.key]}
            onChange={(e) => setToggle(t.key, e.target.checked)}
          />
          {t.label}
        </label>
      ))}

      {comingSoon.map((c) => (
        <div key={c.key} className="opacity-60" title={c.hint}>
          <span className="label flex items-center gap-1">
            {c.label} <ComingSoon />
          </span>
          <select className="input" disabled aria-disabled="true">
            <option>Todos</option>
          </select>
        </div>
      ))}
    </div>
  )
}
