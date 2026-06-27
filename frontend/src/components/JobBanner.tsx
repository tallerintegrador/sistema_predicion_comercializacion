import type { PredStatus } from '../hooks/usePrediction'

/**
 * Banner de estado de la predicción. Cuando un archivo grande se procesa en segundo
 * plano, muestra un estado **honesto y sin tecnicismos**: el resultado aparece solo al
 * terminar. No se exponen los términos internos «en línea» ni «por lote» (ADR-0022); el
 * sondeo del trabajo ocurre por debajo (ver usePrediction).
 */
export function JobBanner({
  status,
  jobId,
  attempts,
}: {
  status: PredStatus
  // Se conservan en la firma para diagnóstico, pero no se muestran al usuario.
  jobId: string | null
  attempts: number
}) {
  void jobId
  void attempts

  if (status === 'loading') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-800">
        <Spinner /> Enviando tus datos…
      </div>
    )
  }
  if (status === 'polling') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        <Spinner />
        <div>
          <div className="font-medium">Estamos procesando tu pronóstico</div>
          <div className="text-amber-700">
            Esto puede tomar un momento. El resultado aparecerá aquí en cuanto esté listo.
          </div>
        </div>
      </div>
    )
  }
  if (status === 'timeout') {
    return (
      <div className="rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
        <div className="font-medium">Tu pronóstico sigue procesándose</div>
        <div className="text-slate-500">
          Está tomando más de lo habitual. Tu trabajo no se perdió: vuelve a pronosticar en
          unos minutos para recuperar el resultado.
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
