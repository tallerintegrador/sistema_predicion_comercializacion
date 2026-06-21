import type { PredStatus } from '../hooks/usePrediction'

/**
 * Banner de estado de la predicción. En modo lote (status="polling") muestra el
 * job_id y los reintentos del polling a `/jobs/{id}/result`.
 */
export function JobBanner({
  status,
  jobId,
  attempts,
}: {
  status: PredStatus
  jobId: string | null
  attempts: number
}) {
  if (status === 'loading') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-800">
        <Spinner /> Enviando petición…
      </div>
    )
  }
  if (status === 'polling') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        <Spinner />
        <div>
          <div className="font-medium">Modo lote (asíncrono) — procesando en segundo plano</div>
          <div className="text-amber-700">
            job <code className="rounded bg-amber-100 px-1 py-0.5 text-xs">{jobId}</code> · consulta #{attempts}
          </div>
        </div>
      </div>
    )
  }
  if (status === 'timeout') {
    return (
      <div className="rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
        <div className="font-medium">El trabajo sigue en proceso en el servidor</div>
        <div className="text-slate-500">
          Dejamos de consultar tras {attempts} intentos para no sondear sin fin. El job{' '}
          <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">{jobId}</code> no se canceló:
          vuelve a predecir en unos minutos para recuperar el resultado.
        </div>
      </div>
    )
  }
  return null
}

function Spinner() {
  return (
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
  )
}
