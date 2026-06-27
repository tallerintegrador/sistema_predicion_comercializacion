/**
 * Tarjeta de **modelo entrenado al vuelo** (motor agnóstico, ADR-0023): algoritmo ganador,
 * si se reutilizó caché y la exactitud sobre datos no vistos (validación honesta) con un
 * veredicto en una frase. Las métricas se traducen a lenguaje claro.
 *
 * Compartida por los modos de predicción a tu medida (Ventas/Compras/Almacén/«Otro rubro»).
 * El acento de color llega por prop para respetar la identidad de cada módulo. Cuando el
 * sistema compara el modelo recién entrenado contra el campeón persistido del cliente
 * («quédate-con-el-mejor», ADR-0023/0013), muestra el veredicto en lenguaje claro.
 */
import type { AutoTrainingInfo } from '../../api/types'
import { fmtNum, fmtPct } from '../../utils/format'

// === Métricas honestas: etiquetas, formato y veredicto legibles ===========
// El backend reporta MAPE/WAPE ya en porcentaje (×100); R² y las métricas de
// clasificación vienen en 0–1. MAE/RMSE/RMSLE van en unidades del objetivo.
type MetricKind = 'units' | 'percent' | 'ratio'
interface MetricMeta { label: string; kind: MetricKind; help: string }

const METRIC_META: Record<string, MetricMeta> = {
  // regresión (ventas / compras)
  MAE: { label: 'Error medio', kind: 'units', help: 'Unidades promedio en que se desvía cada predicción.' },
  RMSE: { label: 'Error cuadrático', kind: 'units', help: 'Como el error medio, pero penaliza más los fallos grandes.' },
  RMSLE: { label: 'Error log.', kind: 'units', help: 'Error en escala logarítmica; mide la desviación relativa.' },
  MAPE: { label: 'Error % medio', kind: 'percent', help: 'Porcentaje medio de desviación frente al valor real.' },
  WAPE: { label: 'Error % ponderado', kind: 'percent', help: 'Suma de errores ÷ suma de ventas reales. Robusto con ceros.' },
  R2: { label: 'Ajuste (R²)', kind: 'ratio', help: 'Cuánta variación explica el modelo (100 % = perfecto).' },
  // clasificación (inventario)
  PR_AUC: { label: 'PR-AUC', kind: 'ratio', help: 'Calidad detectando la alta demanda (mejor cuanto más alto).' },
  ROC_AUC: { label: 'ROC-AUC', kind: 'ratio', help: 'Capacidad de separar alta vs. baja demanda.' },
  Recall: { label: 'Sensibilidad', kind: 'ratio', help: 'De la alta demanda real, qué parte detecta.' },
  Precision: { label: 'Precisión', kind: 'ratio', help: 'De lo marcado como alta demanda, qué parte lo era.' },
  F1: { label: 'F1', kind: 'ratio', help: 'Equilibrio entre precisión y sensibilidad.' },
  Accuracy: { label: 'Acierto global', kind: 'ratio', help: 'Porcentaje de aciertos totales.' },
  prevalencia: { label: 'Prevalencia', kind: 'ratio', help: 'Proporción real de casos de alta demanda.' },
  umbral: { label: 'Umbral', kind: 'ratio', help: 'Probabilidad de corte para marcar alta demanda.' },
}

/** Métricas que se muestran como chip principal; el resto va al detalle técnico. */
const METRICA_PRINCIPAL = new Set(['WAPE', 'MAPE', 'R2', 'MAE', 'PR_AUC', 'ROC_AUC', 'Recall', 'Precision'])

function fmtMetric(meta: MetricMeta, v: number): string {
  if (meta.kind === 'percent') return `${fmtNum(v)}%`
  if (meta.kind === 'ratio') return fmtPct(v)
  return fmtNum(v)
}

/** Veredicto de una frase a partir de la métrica principal del dominio. */
function veredicto(metrics: Record<string, number>): { label: string; tone: string } | null {
  const ok = 'bg-emerald-100 text-emerald-700'
  const med = 'bg-amber-100 text-amber-700'
  const bad = 'bg-rose-100 text-rose-700'
  if ('WAPE' in metrics) {
    const w = metrics.WAPE
    if (w <= 5) return { label: 'Exactitud excelente', tone: ok }
    if (w <= 15) return { label: 'Exactitud buena', tone: ok }
    if (w <= 30) return { label: 'Exactitud regular', tone: med }
    return { label: 'Exactitud mejorable', tone: bad }
  }
  const auc = metrics.ROC_AUC ?? metrics.PR_AUC
  if (auc != null) {
    if (auc >= 0.9) return { label: 'Clasificación excelente', tone: ok }
    if (auc >= 0.8) return { label: 'Clasificación buena', tone: ok }
    if (auc >= 0.7) return { label: 'Clasificación regular', tone: med }
    return { label: 'Clasificación mejorable', tone: bad }
  }
  return null
}

/** Veredicto «quédate-con-el-mejor» en lenguaje claro (candidato vs campeón persistido). */
function SeleccionMensaje({ training }: { training: AutoTrainingInfo }) {
  const s = training.seleccion
  if (!s || !s.comparado) return null
  const meta = METRIC_META[s.metrica]
  const fmt = (v: number | null) => (v == null ? '—' : meta ? fmtMetric(meta, v) : fmtNum(v))

  if (s.adoptado === 'campeon') {
    return (
      <p className="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">
        Entrenamos con tus datos nuevos, pero <strong>no superó</strong> al modelo anterior
        {s.candidato != null && s.campeon != null ? <> ({fmt(s.candidato)} vs {fmt(s.campeon)})</> : null}.
        Mantuvimos el anterior, que predice mejor.
      </p>
    )
  }
  if (s.campeon == null) {
    return (
      <p className="mt-1 text-xs text-slate-500">
        Aprendimos de tus datos y nos quedamos con el mejor modelo.
      </p>
    )
  }
  return (
    <p className="mt-2 rounded-md bg-emerald-50 px-2.5 py-1.5 text-xs text-emerald-800">
      Aprendimos de tus datos nuevos y <strong>mejoró</strong>: {fmt(s.candidato)} frente a{' '}
      {fmt(s.campeon)} del modelo anterior. Adoptamos el nuevo.
    </p>
  )
}

function MetricBadge({ k, v, accentBadge }: { k: string; v: number; accentBadge: string }) {
  const meta = METRIC_META[k]
  return (
    <span className={`badge ${accentBadge}`} title={meta ? `${k} — ${meta.help}` : k}>
      {meta?.label ?? k}: <span className="font-semibold">{meta ? fmtMetric(meta, v) : fmtNum(v)}</span>
    </span>
  )
}

export function TrainingCard({
  training,
  accentSolid,
  accentBadge,
}: {
  training: AutoTrainingInfo
  accentSolid: string
  accentBadge: string
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-800">Modelo entrenado</span>
        <span className={`badge ${accentSolid}`}>{training.winner_algorithm}</span>
        {training.reused_cached_model ? (
          <span className="badge bg-slate-200 text-slate-600">reutilizado</span>
        ) : (
          <span className="badge bg-emerald-100 text-emerald-700">recién entrenado</span>
        )}
        <span className="text-xs text-slate-500">· {fmtNum(training.trained_rows)} filas</span>
      </div>
      <SeleccionMensaje training={training} />
      {!training.seleccion && (
        <p className="mt-1 text-xs text-slate-500">
          Entrenamos varios modelos con tus datos y nos quedamos con el que mejor predice
          {(() => {
            const n = training.candidates ? Object.keys(training.candidates).length : 0
            return n > 1 ? <> (el mejor de {fmtNum(n)})</> : null
          })()}
          .
        </p>
      )}
      {Object.keys(training.honest_metrics).length > 0 && (() => {
        const v = veredicto(training.honest_metrics)
        const entradas = Object.entries(training.honest_metrics)
        const principales = entradas.filter(([k]) => METRICA_PRINCIPAL.has(k))
        const mostrar = principales.length > 0 ? principales : entradas
        return (
          <div className="mt-2">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-slate-500">Exactitud sobre datos no vistos (validación honesta):</p>
              {v && <span className={`badge ${v.tone}`}>{v.label}</span>}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {mostrar.map(([k, val]) => (
                <MetricBadge key={k} k={k} v={val} accentBadge={accentBadge} />
              ))}
            </div>
          </div>
        )
      })()}
    </div>
  )
}
