import { TrainingPanel } from '../components/TrainingPanel'

/**
 * Sección de **Reentrenamiento** (R5). Punto de entrada visible y honesto: opt-in, local y
 * experimental, solo SALES. El experimento medido (modelo del cliente vs congelado vs
 * baseline) y la decisión de adopción viven en el `TrainingPanel` (ADR-0013). No se simulan
 * métricas: si la capacidad está deshabilitada o faltan datos, el panel muestra el estado real.
 */
export function TrainingPage() {
  return (
    <div className="space-y-5">
      <section className="card">
        <h2 className="text-lg font-semibold text-slate-800">Reentrenamiento por cliente (SALES)</h2>
        <p className="mt-1 text-sm text-slate-500">
          Entrena un modelo con <strong>tus datos</strong> y compáralo de forma medida contra el
          modelo congelado y un baseline. Es <strong>opt-in</strong>, corre en local y es
          <strong> experimental</strong>: solo se adopta si supera al congelado. «No mejora» es un
          resultado válido y se reporta como tal.
        </p>
      </section>
      <TrainingPanel />
    </div>
  )
}
