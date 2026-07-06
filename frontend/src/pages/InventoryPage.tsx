import { Package } from 'lucide-react'
import { VistaV3Modulo } from '../components/v3/VistaV3Modulo'
import { SECTION_BY_ID } from '../theme/modules'

/** Almacén: análisis catálogo v3 (10 consultas predefinidas automáticas). */
export function InventoryPage() {
  return (
    <VistaV3Modulo
      view="inventory"
      modulo="almacen"
      accent={SECTION_BY_ID.inventory.accent}
      empty={{
        icon: Package,
        titulo: 'Aún no hay análisis',
        mensaje: 'Descarga la plantilla, carga tus datos de inventario y automáticamente verás 10 análisis: demanda prevista, alertas de quiebre y segmentación ABC.',
      }}
    />
  )
}
