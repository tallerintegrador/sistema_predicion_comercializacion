/**
 * Tarjeta de un reporte del catálogo v3 (compacta).
 * Vista principal en lenguaje de negocio; métricas técnicas SOLO en "Ver detalle técnico".
 * Etiquetas honestas: el WAPE se muestra como "Error promedio" (menor = mejor), nunca "Precisión".
 */
import { TechnicalDetails } from '../ui/TechnicalDetails'
import type { ReporteConsulta } from '../../api/types'

const NUM = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 })

interface ReporteCardProps {
  reporte: ReporteConsulta
  accent: { hex: string }
  children?: React.ReactNode
}

function etiquetaTipo(tipo: string): string {
  return { regresion: 'Predicción', clasificacion: 'Alerta', clustering: 'Segmento' }[tipo] || tipo
}

/** Nombre humano de la métrica (nunca "Precisión" para el WAPE). */
function etiquetaMetrica(metrica: string): string {
  return (
    {
      wape: 'Error promedio',
      pr_auc: 'Confianza',
      f1_macro: 'Acierto (F1)',
      silhouette: 'Cohesión de grupos',
    }[metrica.toLowerCase()] || metrica
  )
}

/** Valor de la métrica formateado según su tipo. */
function valorMetrica(metrica: string, valor: number): string {
  const m = metrica.toLowerCase()
  if (m === 'wape') return `${(valor * 100).toFixed(0)}% (menor = mejor)`
  return NUM.format(valor)
}

/** Calidad cualitativa según la métrica (honesta). */
function calidadMetrica(metrica: string, valor: number): 'buena' | 'limitada' {
  const m = metrica.toLowerCase()
  if (m === 'wape') return valor <= 0.25 ? 'buena' : 'limitada'
  if (m === 'pr_auc') return valor >= 0.6 ? 'buena' : 'limitada'
  if (m === 'f1_macro') return valor >= 0.5 ? 'buena' : 'limitada'
  if (m === 'silhouette') return valor >= 0.5 ? 'buena' : 'limitada'
  return valor >= 0.5 ? 'buena' : 'limitada'
}

export function ReporteCard({ reporte, accent, children }: ReporteCardProps) {
  const { tipo, pregunta, descripcion, advertencia, detalle_tecnico } = reporte
  const m = detalle_tecnico.metrica
  const calidad = calidadMetrica(m, detalle_tecnico.valor_metrica)

  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* Encabezado */}
      <div className="mb-1">
        <span
          className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
          style={{ backgroundColor: `${accent.hex}1a`, color: accent.hex }}
        >
          {etiquetaTipo(tipo)}
        </span>
      </div>
      <h3 className="text-base font-semibold text-slate-800">{pregunta}</h3>
      {descripcion && <p className="text-sm text-slate-500 mt-0.5 mb-2">{descripcion}</p>}

      {/* Aviso honesto (si aplica) */}
      {advertencia && (
        <p className="mb-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">⚠️ {advertencia}</p>
      )}

      {/* Contenido específico por tipo */}
      {children && <div className="flex-1 border-t border-slate-100 pt-3">{children}</div>}

      {/* Detalle técnico (colapsado) */}
      <div className="mt-3">
        <TechnicalDetails title="Ver detalle técnico">
          <p>
            <span className="font-medium">Modelo ganador:</span>{' '}
            <span className="font-mono">{detalle_tecnico.modelo_ganador}</span>
          </p>
          <p>
            <span className="font-medium">{etiquetaMetrica(m)}:</span>{' '}
            {valorMetrica(m, detalle_tecnico.valor_metrica)}{' · '}
            <span className={calidad === 'buena' ? 'text-emerald-600 font-medium' : 'text-amber-600 font-medium'}>
              {calidad === 'buena' ? '✓ calidad buena' : '⚠️ señal limitada'}
            </span>
          </p>

          {detalle_tecnico.nota_tecnica && (
            <p className="italic text-slate-500">ℹ️ {detalle_tecnico.nota_tecnica}</p>
          )}

          {detalle_tecnico.tabla_comparacion.length > 0 && (
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
                  {detalle_tecnico.tabla_comparacion.map((fila) => (
                    <tr key={fila.modelo} className="border-b border-slate-100 last:border-0">
                      <td className="px-1 py-0.5">
                        {fila.modelo}
                        {fila.ganador && <span className="ml-1 font-bold text-emerald-600">✓</span>}
                      </td>
                      <td className="px-1 py-0.5 text-right font-mono">{NUM.format(fila.valor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="mt-2 border-t border-slate-200 pt-1 text-slate-400">
            Entrenado: {detalle_tecnico.fecha_entrenamiento.slice(0, 10)}
          </p>
        </TechnicalDetails>
      </div>
    </div>
  )
}
