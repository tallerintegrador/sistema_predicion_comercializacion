import { Package } from 'lucide-react'
import { AnalisisV2 } from '../components/v2/AnalisisV2'
import { SECTION_BY_ID } from '../theme/modules'

/** Almacén: análisis 3×3 del dominio (demanda futura + riesgo de quiebre + segmentos ABC) con indicadores de inventario, motor /v2. */
export function InventoryPage() {
  return (
    <AnalisisV2
      view="inventory"
      dominio="almacen"
      accent={SECTION_BY_ID.inventory.accent}
      empty={{
        icon: Package,
        titulo: 'Aún no hay análisis',
        mensaje: 'Corre la demo o sube tu inventario para ver el pronóstico de demanda, el riesgo de quiebre y los segmentos ABC.',
      }}
    />
  )
}
