/**
 * Lee las opciones de consulta de un dominio (tipologías R1, dimensiones R2,
 * granularidades y rango de horizonte) desde `GET /catalog`. Es la única fuente de
 * esas opciones en la UI: nada se hardcodea (ADR-0018). El motor de ML no interviene;
 * las opciones se derivan del contrato y de las agregaciones del servicio.
 */
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getCatalog } from '../api/endpoints'
import type { Domain, QueryOptions } from '../api/types'

export interface ForecastOptionsState {
  options: QueryOptions | null
  loading: boolean
  error: ApiError | null
}

export function useForecastOptions(domain: Domain): ForecastOptionsState {
  const [state, setState] = useState<ForecastOptionsState>({
    options: null,
    loading: true,
    error: null,
  })

  useEffect(() => {
    let alive = true
    getCatalog()
      .then((cat) => {
        if (!alive) return
        const dom = cat.domains.find((d) => d.domain === domain)
        setState({ options: dom?.query_options ?? null, loading: false, error: null })
      })
      .catch((e) => {
        if (!alive) return
        const err =
          e instanceof ApiError
            ? e
            : new ApiError(0, 'network', 'No se pudieron cargar las opciones del catálogo.')
        setState({ options: null, loading: false, error: err })
      })
    return () => {
      alive = false
    }
  }, [domain])

  return state
}
