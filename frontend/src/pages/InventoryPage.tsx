import { PrediccionGuiada } from '../components/prediccion/PrediccionGuiada'
import { makeInventoryConfig } from '../components/prediccion/configs'
import { SECTION_BY_ID } from '../theme/modules'

/** Almacén: flujo guiado de riesgo de quiebre sobre el motor agnóstico (ADR-0023). */
const CONFIG = makeInventoryConfig(SECTION_BY_ID.inventory.accent)

export function InventoryPage() {
  return <PrediccionGuiada view="inventory" config={CONFIG} />
}
