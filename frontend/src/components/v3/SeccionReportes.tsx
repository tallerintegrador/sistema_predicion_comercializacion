/**
 * Agrupa reportes del mismo tipo bajo una sección (Predicciones, Alertas, Grupos).
 */
import type { QueryReport } from '../../api/types'
import { ReporteCard } from './ReporteCard'
import {
  RenderidorRegresion,
  RenderidorClasificacion,
  RenderidorClustering,
} from './renderidores'

interface SeccionReportesProps {
  titulo: string
  icono: string
  descripcion: string
  reportes: QueryReport[]
  accentHex: string
}

export function SeccionReportes({
  titulo,
  icono,
  descripcion,
  reportes,
  accentHex,
}: SeccionReportesProps) {
  if (reportes.length === 0) return null

  // Renderizador según el tipo
  const renderizador = (reporte: QueryReport) => {
    const tipo = reporte.type
    if (tipo === 'regression') return <RenderidorRegresion reporte={reporte} accentHex={accentHex} />
    if (tipo === 'classification') return <RenderidorClasificacion reporte={reporte} accentHex={accentHex} />
    if (tipo === 'clustering') return <RenderidorClustering reporte={reporte} accentHex={accentHex} />
    return null
  }

  return (
    <section className="space-y-4">
      {/* Encabezado de sección */}
      <div className="border-b border-slate-200 pb-2">
        <h2 className="text-xl font-bold text-slate-800">
          {icono} {titulo}
        </h2>
        <p className="text-sm text-slate-500 mt-0.5">{descripcion}</p>
      </div>

      {/* Grid de reportes: máximo 2 columnas en desktop (menos scroll, más aire) */}
      <div className="grid gap-4 lg:grid-cols-2">
        {reportes.map((reporte) => (
          <ReporteCard key={reporte.query_id} reporte={reporte} accent={{ hex: accentHex }}>
            {renderizador(reporte)}
          </ReporteCard>
        ))}
      </div>
    </section>
  )
}
