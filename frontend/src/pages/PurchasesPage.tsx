import { PrediccionGuiada } from '../components/prediccion/PrediccionGuiada'
import { makePurchasesConfig } from '../components/prediccion/configs'
import { SECTION_BY_ID } from '../theme/modules'

/** Compras: flujo guiado de reposición sobre el motor agnóstico (ADR-0023). */
const CONFIG = makePurchasesConfig(SECTION_BY_ID.purchases.accent)

export function PurchasesPage() {
  return <PrediccionGuiada view="purchases" config={CONFIG} />
}
