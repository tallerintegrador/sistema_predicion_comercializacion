import { BarChart3 } from 'lucide-react'
import { AnalisisV2 } from '../components/v2/AnalisisV2'
import { SECTION_BY_ID } from '../theme/modules'

/** Ventas: análisis 3×3 del dominio (pronóstico + demanda alta + segmentos), motor /v2. */
export function SalesPage() {
  return (
    <AnalisisV2
      view="sales"
      dominio="ventas"
      accent={SECTION_BY_ID.sales.accent}
      empty={{
        icon: BarChart3,
        titulo: 'Aún no hay análisis',
        mensaje: 'Corre la demo o sube tus ventas para ver el pronóstico, las alertas de demanda alta y los segmentos de producto.',
      }}
    />
  )
}
