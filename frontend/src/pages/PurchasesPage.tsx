import { ShoppingCart } from 'lucide-react'
import { AnalisisV2 } from '../components/v2/AnalisisV2'
import { SECTION_BY_ID } from '../theme/modules'

/** Compras: análisis 3×3 del dominio (cantidad a pedir + entrega con retraso + segmentos de proveedor), motor /v2. */
export function PurchasesPage() {
  return (
    <AnalisisV2
      view="purchases"
      dominio="compras"
      accent={SECTION_BY_ID.purchases.accent}
      empty={{
        icon: ShoppingCart,
        titulo: 'Aún no hay análisis',
        mensaje: 'Corre la demo o sube tus órdenes de compra para ver la cantidad a pedir, las alertas de entrega con retraso y los segmentos de proveedor.',
      }}
    />
  )
}
