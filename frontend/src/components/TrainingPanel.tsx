/**
 * Panel de **entrenamiento por cliente bajo demanda** (ADR-0013), en Ventas.
 *
 * El cliente sube su plantilla Excel y pulsa "Entrenar con mis datos". El panel muestra el
 * progreso (fase honesta), un veredicto en lenguaje claro (mejora / no mejora) y deja un
 * interruptor para usar o no su modelo. El camino por defecto (modelo base) queda intacto
 * para quien no entrena. Los detalles numéricos (métricas) viven en «Detalles técnicos».
 */
import { useEffect, useRef, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { getServingStatus, setServing } from '../api/endpoints'
import type { MetricTriple, ServingStatus, TrainingResult } from '../api/types'
import { useTraining } from '../hooks/useTraining'
import { ErrorPanel } from './ErrorPanel'
import { TechnicalDetails } from './ui/TechnicalDetails'
import { fmtNum } from '../utils/format'

const FASE_LABEL: Record<string, string> = {
  validating: 'Revisando tus datos…',
  training: 'Aprendiendo de tu historia…',
  evaluating: 'Comparando con el modelo base…',
}

const OUTCOME: Record<string, { txt: string; cls: string }> = {
  adopted: { txt: 'Tu modelo mejora: ahora se usa el tuyo', cls: 'bg-emerald-100 text-emerald-800' },
  not_adopted: { txt: 'Se mantiene el modelo base (no mejoró)', cls: 'bg-amber-100 text-amber-800' },
  insufficient_data: { txt: 'Datos insuficientes para entrenar', cls: 'bg-slate-200 text-slate-700' },
  inconclusive: { txt: 'Resultado no concluyente', cls: 'bg-slate-200 text-slate-700' },
}

function MetricRow({ label, m, highlight }: { label: string; m?: MetricTriple; highlight?: boolean }) {
  return (
    <tr className={highlight ? 'font-semibold text-slate-700' : 'text-slate-500'}>
      <td className="py-1 pr-4">{label}</td>
      <td className="py-1 pr-4 text-right">{m ? `${fmtNum(m.WAPE)}%` : '—'}</td>
      <td className="py-1 pr-4 text-right">{m ? fmtNum(m.MAE) : '—'}</td>
      <td className="py-1 text-right">{m ? fmtNum(m.RMSE) : '—'}</td>
    </tr>
  )
}

function Veredicto({ r }: { r: TrainingResult }) {
  const badge = OUTCOME[r.outcome] ?? OUTCOME.inconclusive

  if (r.outcome === 'insufficient_data') {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
        <span className={`badge ${badge.cls}`}>{badge.txt}</span>
        <p className="mt-2 text-sm text-slate-600">{r.message}</p>
        {r.missing && r.missing.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-slate-500">
            {r.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-3">
      <span className={`badge ${badge.cls}`}>{badge.txt}</span>
      <p className="text-sm text-slate-600">{r.message}</p>

      {/* Métricas (técnicas): ocultas por defecto, fuera del camino del usuario. */}
      <TechnicalDetails title="Ver la comparación en detalle">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase text-slate-400">
              <th className="py-1 pr-4 text-left">Modelo</th>
              <th className="py-1 pr-4 text-right">WAPE</th>
              <th className="py-1 pr-4 text-right">MAE</th>
              <th className="py-1 text-right">RMSE</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow label="Tu modelo" m={r.candidate} highlight={r.outcome === 'adopted'} />
            <MetricRow label="Modelo base" m={r.frozen} highlight={r.outcome !== 'adopted'} />
            {r.baseline && <MetricRow label={`Referencia simple (${r.baseline.name})`} m={r.baseline} />}
          </tbody>
        </table>
        {typeof r.improvement_wape_points === 'number' && (
          <p className="mt-2">
            Diferencia frente al modelo base: <strong>{fmtNum(r.improvement_wape_points)}</strong> puntos de
            margen de error{r.improvement_wape_points > 0 ? ' a favor de tu modelo.' : ' (no mejora).'}
            {r.window_days ? ` · Ventana de validación: ${r.window_days} días.` : ''}
          </p>
        )}
        <p className="mt-1">WAPE es el «margen de error»: cuanto más bajo, mejor.</p>
      </TechnicalDetails>
    </div>
  )
}

function EstadoActual({ s }: { s: ServingStatus }) {
  const usandoPropio = s.serving_client_model
  return (
    <span className={`badge ${usandoPropio ? 'bg-training-100 text-training-700' : 'bg-slate-200 text-slate-700'}`}>
      Ahora se usa: {usandoPropio ? 'tu modelo' : 'el modelo base'}
    </span>
  )
}

export function TrainingPanel() {
  const train = useTraining()
  const inputRef = useRef<HTMLInputElement>(null)
  const [serving, setServingState] = useState<ServingStatus | null>(null)
  const [switching, setSwitching] = useState(false)
  const busy = train.status === 'uploading' || train.status === 'training'

  const refrescarEstado = async () => {
    try {
      setServingState(await getServingStatus())
    } catch {
      setServingState(null) // capacidad deshabilitada o sin red: el panel degrada en silencio
    }
  }

  useEffect(() => {
    void refrescarEstado()
  }, [])

  useEffect(() => {
    if (train.status === 'done') void refrescarEstado()
  }, [train.status])

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void train.run(file)
    e.target.value = ''
  }

  const toggleServing = async () => {
    if (!serving) return
    setSwitching(true)
    try {
      setServingState(await setServing(!serving.serving_client_model))
    } catch {
      await refrescarEstado()
    } finally {
      setSwitching(false)
    }
  }

  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Entrenar con mis datos</h3>
          <p className="text-xs text-slate-500">
            Sube tu historial (la misma plantilla Excel de Ventas). El sistema aprende de tus datos, los
            compara con el modelo base y solo usa el tuyo si mejora.
          </p>
        </div>
        {serving && <EstadoActual s={serving} />}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn bg-training-600 text-white hover:bg-training-700" onClick={() => inputRef.current?.click()} disabled={busy}>
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {busy ? 'Entrenando…' : 'Entrenar con mis datos'}
        </button>
        <input ref={inputRef} type="file" accept=".xlsx" className="hidden" onChange={onFile} />

        {serving?.has_client_model && (
          <button type="button" className="btn-ghost" onClick={toggleServing} disabled={switching || busy}>
            {serving.serving_client_model ? 'Volver al modelo base' : 'Usar mi modelo'}
          </button>
        )}
      </div>

      {busy && (
        <p className="text-sm text-slate-500">
          {train.phase ? FASE_LABEL[train.phase] : 'Preparando el trabajo…'} (puede tardar; se ejecuta
          aparte del pronóstico).
        </p>
      )}

      {train.status === 'error' && train.error && <ErrorPanel error={train.error} />}
      {train.status === 'done' && train.result && <Veredicto r={train.result} />}
    </section>
  )
}
