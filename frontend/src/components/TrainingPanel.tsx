/**
 * Panel de **entrenamiento por cliente bajo demanda** (ADR-0013), en SALES.
 *
 * Opt-in: el cliente sube su plantilla Excel y pulsa "Entrenar con mis datos". El panel
 * muestra el progreso (fase honesta), presenta la **comparación medida** (su modelo vs el
 * congelado vs un baseline) y el veredicto de adopción, y deja un **switch** para servir o
 * no su modelo. El camino por defecto (congelado) queda intacto para quien no entrena.
 */
import { useEffect, useRef, useState } from 'react'
import { getServingStatus, setServing } from '../api/endpoints'
import type { MetricTriple, ServingStatus, TrainingResult } from '../api/types'
import { useTraining } from '../hooks/useTraining'
import { ErrorPanel } from './ErrorPanel'
import { fmtNum } from '../utils/format'

const FASE_LABEL: Record<string, string> = {
  validating: 'Validando datos…',
  training: 'Entrenando tu modelo…',
  evaluating: 'Midiendo contra el congelado…',
}

const OUTCOME_BADGE: Record<string, { txt: string; cls: string }> = {
  adopted: { txt: 'Adoptado', cls: 'bg-green-100 text-green-800' },
  not_adopted: { txt: 'No adoptado', cls: 'bg-amber-100 text-amber-800' },
  insufficient_data: { txt: 'Datos insuficientes', cls: 'bg-slate-200 text-slate-700' },
  inconclusive: { txt: 'No concluyente', cls: 'bg-slate-200 text-slate-700' },
}

function MetricRow({ label, m, highlight }: { label: string; m?: MetricTriple; highlight?: boolean }) {
  return (
    <tr className={highlight ? 'font-semibold text-slate-800' : 'text-slate-600'}>
      <td className="py-1 pr-4">{label}</td>
      <td className="py-1 pr-4 text-right">{m ? `${fmtNum(m.WAPE)}%` : '—'}</td>
      <td className="py-1 pr-4 text-right">{m ? fmtNum(m.MAE) : '—'}</td>
      <td className="py-1 text-right">{m ? fmtNum(m.RMSE) : '—'}</td>
    </tr>
  )
}

function Comparacion({ r }: { r: TrainingResult }) {
  const badge = OUTCOME_BADGE[r.outcome] ?? OUTCOME_BADGE.inconclusive

  if (r.outcome === 'insufficient_data') {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${badge.cls}`}>{badge.txt}</span>
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
    <div className="rounded-md border border-slate-200 p-3">
      <span className={`rounded px-2 py-0.5 text-xs font-semibold ${badge.cls}`}>{badge.txt}</span>
      <p className="mt-2 text-sm text-slate-600">{r.message}</p>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-xs uppercase text-slate-400">
            <th className="py-1 pr-4 text-left">Modelo ({r.metric ?? 'WAPE'})</th>
            <th className="py-1 pr-4 text-right">WAPE</th>
            <th className="py-1 pr-4 text-right">MAE</th>
            <th className="py-1 text-right">RMSE</th>
          </tr>
        </thead>
        <tbody>
          <MetricRow label="Tu modelo (por cliente)" m={r.candidate} highlight={r.outcome === 'adopted'} />
          <MetricRow label="Modelo congelado (base)" m={r.frozen} highlight={r.outcome !== 'adopted'} />
          {r.baseline && <MetricRow label={`Baseline (${r.baseline.name})`} m={r.baseline} />}
        </tbody>
      </table>
      {typeof r.improvement_wape_points === 'number' && (
        <p className="mt-2 text-xs text-slate-500">
          Diferencia vs congelado: <strong>{fmtNum(r.improvement_wape_points)}</strong> puntos de WAPE
          {r.improvement_wape_points > 0 ? ' a favor de tu modelo.' : ' (no mejora).'}
          {r.window_days ? ` · Ventana de validación: ${r.window_days} días.` : ''}
        </p>
      )}
    </div>
  )
}

function ServingBadge({ s }: { s: ServingStatus }) {
  if (s.serving_client_model) {
    return (
      <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800">
        Sirviendo TU modelo {s.model_version ? `(${s.model_version})` : ''}
      </span>
    )
  }
  return (
    <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">
      Sirviendo modelo congelado (base)
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
      setServingState(null) // feature deshabilitada o sin red: el panel degrada en silencio
    }
  }

  useEffect(() => {
    void refrescarEstado()
  }, [])

  // Tras terminar un entrenamiento, refresca el estado de serving (puede haber adoptado).
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
          <h3 className="text-sm font-semibold text-slate-700">Entrenar con mis datos (opt-in)</h3>
          <p className="text-xs text-slate-500">
            Entrena un modelo con TU historial (misma plantilla Excel). Corre local, mide contra el
            congelado y solo se adopta si mejora. "No mejora" también se reporta.
          </p>
        </div>
        {serving && <ServingBadge s={serving} />}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
        >
          {busy ? 'Entrenando…' : '🧠 Entrenar con mis datos'}
        </button>
        <input ref={inputRef} type="file" accept=".xlsx" className="hidden" onChange={onFile} />

        {serving?.has_client_model && (
          <button type="button" className="btn-ghost" onClick={toggleServing} disabled={switching || busy}>
            {serving.serving_client_model ? 'Volver al congelado' : 'Servir mi modelo'}
          </button>
        )}
      </div>

      {busy && (
        <p className="text-sm text-slate-500">
          {train.phase ? FASE_LABEL[train.phase] : 'Encolando el trabajo…'} (puede tardar; se ejecuta
          aparte de la predicción)
        </p>
      )}

      {train.status === 'error' && train.error && <ErrorPanel error={train.error} />}
      {train.status === 'done' && train.result && <Comparacion r={train.result} />}
    </section>
  )
}
