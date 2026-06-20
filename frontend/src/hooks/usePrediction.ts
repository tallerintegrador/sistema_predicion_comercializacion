/**
 * Hook genérico de predicción. Ejecuta una llamada que puede volver en línea (200)
 * o por lote (202): en el segundo caso hace polling de `/jobs/{id}/result` hasta
 * que el backend entrega el resultado o un error. Expone un estado simple para la UI.
 */
import { useCallback, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { getJobResult } from '../api/endpoints'
import type { PredictResult } from '../api/endpoints'

export type PredStatus = 'idle' | 'loading' | 'polling' | 'done' | 'error'

const POLL_INTERVAL_MS = 1500

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export interface PredictionState<T> {
  status: PredStatus
  data: T | null
  error: ApiError | null
  jobId: string | null
  attempts: number
}

const initial = <T,>(): PredictionState<T> => ({
  status: 'idle',
  data: null,
  error: null,
  jobId: null,
  attempts: 0,
})

export function usePrediction<T>() {
  const [state, setState] = useState<PredictionState<T>>(initial<T>())
  const cancelled = useRef(false)

  const run = useCallback(async (fn: () => Promise<PredictResult<T>>) => {
    cancelled.current = false
    setState({ ...initial<T>(), status: 'loading' })
    try {
      const res = await fn()
      if (res.mode === 'online') {
        setState({ status: 'done', data: res.data, error: null, jobId: null, attempts: 0 })
        return
      }
      // Modo lote: pollear el resultado.
      const jobId = res.job.job_id
      setState((s) => ({ ...s, status: 'polling', jobId, attempts: 0 }))
      let attempts = 0
      while (!cancelled.current) {
        attempts += 1
        setState((s) => ({ ...s, attempts }))
        const r = await getJobResult<T>(jobId)
        if (cancelled.current) return
        if (!r.pending) {
          setState({ status: 'done', data: r.data, error: null, jobId, attempts })
          return
        }
        await sleep(POLL_INTERVAL_MS)
      }
    } catch (e) {
      if (cancelled.current) return
      const err =
        e instanceof ApiError
          ? e
          : new ApiError(0, 'network', e instanceof Error ? e.message : 'Error de red')
      setState({ status: 'error', data: null, error: err, jobId: null, attempts: 0 })
    }
  }, [])

  const reset = useCallback(() => {
    cancelled.current = true
    setState(initial<T>())
  }, [])

  return { ...state, run, reset }
}
