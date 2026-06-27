import { useMemo, useState } from 'react'

/**
 * Filtros y orden de las tablas de resultado (Compras/Almacén).
 *
 * Principio: TODO sale de los datos reales que devuelve la API. Los valores de cada filtro
 * (qué tiendas, qué productos, qué segmentos) se derivan de las filas del resultado, no de
 * listas fijas; nunca se inventan. Lo que el backend no entrega hoy (categoría/familia,
 * nivel de riesgo en niveles, medida de urgencia) NO se simula aquí: se muestra aparte como
 * «Próximamente» (ver ResultFilters) y queda registrado en docs/alineacion_frontend_backend.md.
 */

/** Faceta de igualdad: filtra por un valor concreto de un campo presente en la respuesta. */
export interface Facet<T> {
  key: string
  label: string
  /** Lee el valor de la faceta como texto (p. ej. r.store_id o String(r.store_segment)). */
  read: (row: T) => string
  /** Etiqueta visible de un valor (p. ej. "Segmento 1"); por defecto, el valor crudo. */
  display?: (value: string) => string
}

/** Interruptor booleano: cuando está activo, conserva solo las filas que cumplen el predicado. */
export interface Toggle<T> {
  key: string
  label: string
  predicate: (row: T) => boolean
}

/** Opción de orden: nombre visible + comparador (sobre campos reales de la respuesta). */
export interface SortOption<T> {
  key: string
  label: string
  compare: (a: T, b: T) => number
}

export interface ResultFiltersSpec<T> {
  facets?: Facet<T>[]
  toggles?: Toggle<T>[]
  sorts?: SortOption<T>[]
}

export interface ResultFiltersState<T> {
  filtered: T[]
  options: Record<string, string[]>
  facets: Record<string, string>
  setFacet: (key: string, value: string) => void
  toggles: Record<string, boolean>
  setToggle: (key: string, value: boolean) => void
  sort: string
  setSort: (value: string) => void
}

/** Valores distintos de una faceta, en orden natural (numérico/es). Función pura. */
export function facetOptions<T>(rows: T[], facet: Facet<T>): string[] {
  const vals = new Set<string>()
  for (const r of rows) {
    const v = facet.read(r)
    if (v !== '') vals.add(v)
  }
  return Array.from(vals).sort((a, b) => a.localeCompare(b, 'es', { numeric: true }))
}

/** Aplica facetas (igualdad), interruptores activos y orden. Función pura y testeable. */
export function applyFilters<T>(
  rows: T[],
  spec: ResultFiltersSpec<T>,
  state: { facets: Record<string, string>; toggles: Record<string, boolean>; sort: string },
): T[] {
  let out = rows
  for (const f of spec.facets ?? []) {
    const sel = state.facets[f.key]
    if (sel) out = out.filter((r) => f.read(r) === sel)
  }
  for (const t of spec.toggles ?? []) {
    if (state.toggles[t.key]) out = out.filter(t.predicate)
  }
  const sort = (spec.sorts ?? []).find((s) => s.key === state.sort)
  if (sort) out = [...out].sort(sort.compare)
  return out
}

/** Estado + opciones derivadas + resultado filtrado/ordenado para una tabla de resultado. */
export function useResultFilters<T>(rows: T[], spec: ResultFiltersSpec<T>): ResultFiltersState<T> {
  const [facets, setFacets] = useState<Record<string, string>>({})
  const [toggles, setToggles] = useState<Record<string, boolean>>({})
  const [sort, setSort] = useState<string>(spec.sorts?.[0]?.key ?? '')

  const options = useMemo(() => {
    const o: Record<string, string[]> = {}
    for (const f of spec.facets ?? []) o[f.key] = facetOptions(rows, f)
    return o
  }, [rows, spec])

  const filtered = useMemo(
    () => applyFilters(rows, spec, { facets, toggles, sort }),
    [rows, spec, facets, toggles, sort],
  )

  return {
    filtered,
    options,
    facets,
    setFacet: (key, value) => setFacets((s) => ({ ...s, [key]: value })),
    toggles,
    setToggle: (key, value) => setToggles((s) => ({ ...s, [key]: value })),
    sort,
    setSort,
  }
}
