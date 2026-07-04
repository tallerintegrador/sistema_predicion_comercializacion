/**
 * Tarjeta de un reporte del catálogo v3 (compacta).
 * Vista principal en lenguaje de negocio; métricas técnicas SOLO en "Ver detalle técnico".
 * Etiquetas honestas: el WAPE se muestra como "Error promedio" (menor = mejor), nunca "Precisión".
 * Contrato en inglés (ADR-0028): type, question, warning, technical_detail...
 */
import { TechnicalDetails } from '../ui/TechnicalDetails'
import { InfoTooltip } from '../ui/InfoTooltip'
import type { QueryReport } from '../../api/types'

const NUM = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 })

/** Explicación en simple de cada métrica (A7). */
function ayudaMetrica(metrica: string): string {
  return (
    {
      wape: 'Error promedio: qué tan lejos (en %) quedan las predicciones del valor real. Menor es mejor.',
      pr_auc: 'Confianza de la alerta: qué tan bien separa los casos con y sin alerta (0 a 1; mayor es mejor).',
      f1_macro: 'Acierto equilibrado entre todas las categorías (0 a 1; mayor es mejor).',
      silhouette: 'Cohesión de los grupos: qué tan separados y compactos son (−1 a 1; mayor es mejor).',
      value_share_a: 'Concentración de la clase A: qué % del valor total (volumen de movimiento) mueven los pocos productos de la clase A. Es una regla de Pareto (ABC), no un modelo.',
    }[metrica.toLowerCase()] || 'Métrica técnica del modelo.'
  )
}

interface ReporteCardProps {
  reporte: QueryReport
  accent: { hex: string }
  children?: React.ReactNode
}

function etiquetaTipo(tipo: string): string {
  return { regression: 'Predicción', classification: 'Alerta', clustering: 'Segmento' }[tipo] || tipo
}

/** Nombre humano de la métrica (nunca "Precisión" para el WAPE). */
function etiquetaMetrica(metrica: string): string {
  return (
    {
      wape: 'Error promedio',
      pr_auc: 'Confianza',
      f1_macro: 'Acierto (F1)',
      silhouette: 'Cohesión de grupos',
      value_share_a: 'Concentración clase A',
    }[metrica.toLowerCase()] || metrica
  )
}

/** Valor de la métrica formateado según su tipo. */
function valorMetrica(metrica: string, valor: number): string {
  const m = metrica.toLowerCase()
  if (m === 'wape') return `${(valor * 100).toFixed(0)}% (menor = mejor)`
  if (m === 'value_share_a') return `${(valor * 100).toFixed(0)}% del valor en clase A`
  return NUM.format(valor)
}

export function ReporteCard({ reporte, accent, children }: ReporteCardProps) {
  const { type, question, description, warning, columns_used, technical_detail } = reporte
  const m = technical_detail.metric
  // La calidad la decide el backend con los umbrales del catálogo (fuente única, ADR-0028).
  const calidad = technical_detail.quality

  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* Encabezado */}
      <div className="mb-1">
        <span
          className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
          style={{ backgroundColor: `${accent.hex}1a`, color: accent.hex }}
        >
          {etiquetaTipo(type)}
        </span>
      </div>
      <h3 className="text-base font-semibold text-slate-800">{question}</h3>
      {description && <p className="text-sm text-slate-500 mt-0.5 mb-2">{description}</p>}

      {/* Aviso honesto (si aplica) */}
      {warning && (
        <p className="mb-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">⚠️ {warning}</p>
      )}

      {/* Columnas en que se basa la predicción (transparencia + ⓘ por columna) */}
      {columns_used && columns_used.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-slate-500">Basado en:</span>
          {columns_used.map((col) => {
            const esObjetivo = col.role === 'objetivo'
            return (
              <span
                key={col.name}
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
                  esObjetivo
                    ? 'border-indigo-200 bg-indigo-50 font-medium text-indigo-700'
                    : 'border-slate-200 bg-slate-50 text-slate-600'
                }`}
                title={esObjetivo ? 'Lo que se predice' : undefined}
              >
                {esObjetivo && <span aria-hidden="true">🎯</span>}
                {col.label}
                {col.description && <InfoTooltip text={col.description} />}
              </span>
            )
          })}
        </div>
      )}

      {/* Contenido específico por tipo */}
      {children && <div className="flex-1 border-t border-slate-100 pt-3">{children}</div>}

      {/* Detalle técnico (colapsado) */}
      <div className="mt-3">
        <TechnicalDetails title="Ver detalle técnico">
          <p>
            <span className="font-medium">Modelo ganador:</span>{' '}
            <span className="font-mono">{technical_detail.winner_model}</span>
          </p>
          <p>
            <span className="font-medium">{etiquetaMetrica(m)}</span>{' '}
            <InfoTooltip text={ayudaMetrica(m)} />{': '}
            {valorMetrica(m, technical_detail.metric_value)}{' · '}
            <span className={calidad === 'buena' ? 'text-emerald-600 font-medium' : 'text-amber-600 font-medium'}>
              {calidad === 'buena' ? '✓ calidad buena' : '⚠️ señal limitada'}
            </span>
          </p>

          {technical_detail.technical_note && (
            <p className="italic text-slate-500">ℹ️ {technical_detail.technical_note}</p>
          )}

          {technical_detail.comparison_table.length > 0 && (
            <div className="mt-2 border-t border-slate-200 pt-2">
              <p className="mb-1 font-medium text-slate-600">Comparación de candidatos:</p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="px-1 py-0.5 text-left font-medium">Modelo</th>
                    <th className="px-1 py-0.5 text-right font-medium">{etiquetaMetrica(m)}</th>
                  </tr>
                </thead>
                <tbody>
                  {technical_detail.comparison_table.map((fila) => (
                    <tr key={fila.model} className="border-b border-slate-100 last:border-0">
                      <td className="px-1 py-0.5">
                        {fila.model}
                        {fila.winner && <span className="ml-1 font-bold text-emerald-600">✓</span>}
                      </td>
                      <td className="px-1 py-0.5 text-right font-mono">{NUM.format(fila.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="mt-2 border-t border-slate-200 pt-1 text-slate-400">
            Entrenado: {technical_detail.trained_at.slice(0, 10)}
          </p>
        </TechnicalDetails>
      </div>
    </div>
  )
}
