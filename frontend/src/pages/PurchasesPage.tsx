import { ShoppingCart } from 'lucide-react'
import { VistaV3Modulo } from '../components/v3/VistaV3Modulo'
import { SECTION_BY_ID } from '../theme/modules'

/** Compras: análisis catálogo v3 (10 consultas predefinidas automáticas). */
export function PurchasesPage() {
  return (
    <VistaV3Modulo
      view="purchases"
      modulo="compras"
      accent={SECTION_BY_ID.purchases.accent}
      empty={{
        icon: ShoppingCart,
        titulo: 'Aún no hay análisis',
        mensaje: 'Descarga la plantilla, carga tus órdenes de compra y automáticamente verás 10 análisis: predicciones de cantidad, alertas de riesgo y segmentos de proveedor.',
      }}
    />
  )
}
