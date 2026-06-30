import { PrediccionGuiada } from '../components/prediccion/PrediccionGuiada'
import { makeSalesConfig } from '../components/prediccion/configs'
import { SECTION_BY_ID } from '../theme/modules'

/** Ventas: flujo guiado de pronóstico de demanda sobre el motor agnóstico (ADR-0023). */
const CONFIG = makeSalesConfig(SECTION_BY_ID.sales.accent)

export function SalesPage() {
  return <PrediccionGuiada view="sales" config={CONFIG} />
}
