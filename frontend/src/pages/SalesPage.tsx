import { BarChart3 } from 'lucide-react'
import { VistaV3Modulo } from '../components/v3/VistaV3Modulo'
import { SECTION_BY_ID } from '../theme/modules'

/** Ventas: análisis catálogo v3 (10 consultas predefinidas automáticas). */
export function SalesPage() {
  return (
    <VistaV3Modulo
      view="sales"
      modulo="ventas"
      accent={SECTION_BY_ID.sales.accent}
      empty={{
        icon: BarChart3,
        titulo: 'Aún no hay análisis',
        mensaje: 'Descarga la plantilla, carga tus datos de ventas y automáticamente verás 10 análisis: predicciones, alertas y segmentos.',
      }}
    />
  )
}
