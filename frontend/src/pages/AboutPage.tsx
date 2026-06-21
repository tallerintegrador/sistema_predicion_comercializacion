import { useEffect, useState } from 'react'
import { ShieldCheck, Info, Sparkles } from 'lucide-react'
import { getCatalog } from '../api/endpoints'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'

/**
 * "Acerca del sistema" (ADR-0019/0020). Reúne la honestidad del producto en lenguaje
 * simple —en qué datos se entrenó, qué tan exactas son las estimaciones— y deja los
 * tecnicismos (versión de contrato, modelo base) en un bloque colapsable, fuera del
 * camino del usuario no técnico.
 */
export function AboutPage() {
  const [contractVersion, setContractVersion] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    getCatalog()
      .then((c) => alive && setContractVersion(c.contract_version))
      .catch(() => alive && setContractVersion(null))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="space-y-5">
      <ModuleHeader view="about" />

      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <Info className="h-5 w-5 text-slate-400" aria-hidden="true" />
          <h3 className="text-base font-semibold text-slate-800">¿Cómo funciona?</h3>
        </div>
        <p className="text-sm leading-relaxed text-slate-600">
          SPC aprende de tu historial de ventas para estimar lo que viene: cuánto venderás, cuánto
          conviene reponer y qué productos podrían agotarse. Tú aportas los datos; el sistema hace los
          cálculos y te los explica en lenguaje claro, con un gráfico y un resumen.
        </p>
      </section>

      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-500" aria-hidden="true" />
          <h3 className="text-base font-semibold text-slate-800">Qué tan exactas son las estimaciones</h3>
        </div>
        <p className="text-sm leading-relaxed text-slate-600">
          El sistema se entrenó con los datos de un <strong>comercio de ejemplo</strong>. Por eso, para
          otros tipos de negocio las estimaciones son <strong>referenciales</strong>: una guía útil para
          planificar, no una cifra exacta garantizada. Mientras más se parezca tu negocio al de ejemplo,
          más fiables serán los resultados.
        </p>
        <div className="flex items-start gap-2 rounded-lg bg-training-50 px-4 py-3 text-sm text-training-700">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Si tienes suficiente historia propia, puedes pedirle al sistema que aprenda de{' '}
            <strong>tus</strong> datos en la sección «Mejorar las predicciones». Solo adopta tu versión si
            de verdad mejora; si no, mantiene la base. «No mejora» es un resultado normal y válido.
          </p>
        </div>
      </section>

      <TechnicalDetails>
        <p>
          Versión del contrato de datos vigente:{' '}
          <span className="font-mono text-slate-700">{contractVersion ?? '—'}</span>.
        </p>
        <p>
          El sistema usa por defecto un <strong>modelo base</strong> entrenado y fijado con los datos del
          comercio de ejemplo (Corporación Favorita). El reentrenamiento por cliente es opcional, se valida
          con honestidad temporal y solo se adopta si supera al modelo base.
        </p>
        <p>
          La interfaz no fabrica datos ni resultados: cuando una función todavía no está soportada por el
          servidor, se muestra deshabilitada con la etiqueta «Próximamente».
        </p>
      </TechnicalDetails>
    </div>
  )
}
