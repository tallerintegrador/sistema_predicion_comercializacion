/**
 * Lee del `GET /catalog` todo lo que la UI necesita de un dominio **sin hardcodear**:
 * las opciones de consulta (tipologías R1, dimensiones R2, granularidad y horizonte) y
 * las **tablas de entrada** con sus columnas y etiquetas en español (ADR-0018/0020). El
 * motor de ML no interviene: todo se deriva del contrato y de las agregaciones del servicio.
 */
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getCatalog } from '../api/endpoints'
import type { Domain, DomainCatalog } from '../api/types'

export interface DomainCatalogState {
  domain: DomainCatalog | null
  loading: boolean
  error: ApiError | null
}

export function useDomainCatalog(domain: Domain): DomainCatalogState {
  const [state, setState] = useState<DomainCatalogState>({
    domain: null,
    loading: true,
    error: null,
  })

  useEffect(() => {
    let alive = true
    getCatalog()
      .then((cat) => {
        if (!alive) return
        const dom = cat.domains.find((d) => d.domain === domain) ?? null
        setState({ domain: dom, loading: false, error: null })
      })
      .catch((e) => {
        if (!alive) return
        const err =
          e instanceof ApiError
            ? e
            : new ApiError(0, 'network', 'No se pudo cargar la información del módulo.')
        setState({ domain: null, loading: false, error: err })
      })
    return () => {
      alive = false
    }
  }, [domain])

  return state
}
