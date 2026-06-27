/**
 * «Predicción a tu medida» — modo libre, agnóstico al rubro (ADR-0023). Reemplaza al antiguo
 * editor JSON crudo (AutoPage) por el **mismo flujo guiado** que Ventas/Compras/Almacén, con
 * un selector de objetivo arriba: el cliente elige qué quiere (pronóstico, riesgo de quiebre
 * o reposición) y trae sus columnas de cualquier rubro. Una sola pantalla cubre los tres,
 * sin duplicar la mecánica: reutiliza {@link PrediccionGuiada} con el acento de marca.
 */
import { useState } from 'react'
import { PrediccionGuiada } from '../components/prediccion/PrediccionGuiada'
import { makeInventoryConfig, makePurchasesConfig, makeSalesConfig } from '../components/prediccion/configs'
import { SECTION_BY_ID } from '../theme/modules'

type Objetivo = 'sales' | 'inventory' | 'purchases'

const ACCENT = SECTION_BY_ID.auto.accent // acento de marca (sección «Predicción a tu medida»)

const OBJ_LABEL: Record<Objetivo, string> = {
  sales: 'Pronóstico de demanda',
  inventory: 'Riesgo de quiebre',
  purchases: 'Reposición',
}

const CONFIG = {
  sales: makeSalesConfig(ACCENT),
  inventory: makeInventoryConfig(ACCENT),
  purchases: makePurchasesConfig(ACCENT),
}

export function LibrePage() {
  const [objetivo, setObjetivo] = useState<Objetivo>('sales')

  const selector = (
    <section className="card space-y-2">
      <div>
        <h3 className="text-base font-semibold text-slate-800">¿Qué quieres obtener?</h3>
        <p className="text-sm text-slate-500">
          Elige el tipo de análisis. Sea cual sea tu rubro, traes tus columnas y el sistema entrena el
          mejor modelo para ellas.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {(Object.keys(OBJ_LABEL) as Objetivo[]).map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => setObjetivo(o)}
            className={`badge ${objetivo === o ? ACCENT.solid : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            {OBJ_LABEL[o]}
          </button>
        ))}
      </div>
    </section>
  )

  // `key` por objetivo: remonta el flujo (estado limpio) al cambiar de tipo de análisis.
  if (objetivo === 'inventory')
    return <PrediccionGuiada key="inventory" view="auto" config={CONFIG.inventory} intro={selector} />
  if (objetivo === 'purchases')
    return <PrediccionGuiada key="purchases" view="auto" config={CONFIG.purchases} intro={selector} />
  return <PrediccionGuiada key="sales" view="auto" config={CONFIG.sales} intro={selector} />
}
