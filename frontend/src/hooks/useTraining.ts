/**
 * Hook del entrenamiento por cliente bajo demanda (ADR-0013). Sube el Excel, dispara
 * el trabajo LOCAL y pollea `/training/jobs/{id}/result` mostrando la **fase honesta**
 * (validating → training → evaluating) hasta obtener la comparación medida o un error.
 */
import { useCallback, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { getTrainingResult, startSalesTraining } from '../api/endpoints'
import type { TrainingPhase, TrainingResult, TrainingSource } from '../api/types'

export type TrainStatus = 'idle' | 'uploading' | 'training' | 'done' | 'error'

const POLL_INTERVAL_MS = 2000
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export interface TrainingState {
  status: TrainStatus
  phase: TrainingPhase | null
  result: TrainingResult | null
  error: ApiError | null
  jobId: string | null
}

const initial: TrainingState = {
  status: 'idle',
  phase: null,
  result: null,
  error: null,
  jobId: null,
}

export function useTraining() {
  const [state, setState] = useState<TrainingState>(initial)
  const cancelled = useRef(false)

  const run = useCallback(async (file: File, source: TrainingSource = 'merged') => {
    cancelled.current = false
    setState({ ...initial, status: 'uploading' })
    try {
      const acuse = await startSalesTraining(file, source)
      const jobId = acuse.job_id
      setState((s) => ({ ...s, status: 'training', jobId }))
      while (!cancelled.current) {
        const r = await getTrainingResult(jobId)
        if (cancelled.current) return
        if (!r.pending) {
          setState({ status: 'done', phase: null, result: r.data, error: null, jobId })
          return
        }
        setState((s) => ({ ...s, status: 'training', phase: r.phase }))
        await sleep(POLL_INTERVAL_MS)
      }
    } catch (e) {
      if (cancelled.current) return
      const err =
        e instanceof ApiError
          ? e
          : new ApiError(0, 'network', e instanceof Error ? e.message : 'Error de red')
      setState({ status: 'error', phase: null, result: null, error: err, jobId: null })
    }
  }, [])

  const reset = useCallback(() => {
    cancelled.current = true
    setState(initial)
  }, [])

  return { ...state, run, reset }
}
