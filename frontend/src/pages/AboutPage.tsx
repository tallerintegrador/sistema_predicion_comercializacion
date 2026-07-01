import { ShieldCheck, Info, Sparkles } from 'lucide-react'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'

/**
 * "Acerca del sistema". Reúne la honestidad del producto en lenguaje simple —cómo
 * funciona, qué tan exactas son las estimaciones— y deja los tecnicismos en un bloque
 * colapsable, fuera del camino del usuario no técnico.
 */
export function AboutPage() {
  return (
    <div className="space-y-5">
      <ModuleHeader view="about" />

      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <Info className="h-5 w-5 text-slate-400" aria-hidden="true" />
          <h3 className="text-base font-semibold text-slate-800">¿Cómo funciona?</h3>
        </div>
        <p className="text-sm leading-relaxed text-slate-600">
          SPC aprende de <strong>tus propios datos</strong> para estimar lo que viene: cuánto venderás,
          cuánto conviene reponer y qué productos podrían agotarse. No usa un modelo prefabricado: cada
          vez que pides un análisis, entrena varios modelos con los datos que envías, se queda con el
          mejor con validación honesta y te muestra el resultado con un gráfico y un resumen.
        </p>
      </section>

      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-500" aria-hidden="true" />
          <h3 className="text-base font-semibold text-slate-800">Qué tan exactas son las estimaciones</h3>
        </div>
        <p className="text-sm leading-relaxed text-slate-600">
          La calidad depende de la historia que aportes: mientras más y mejores datos, más fiables los
          resultados. Cada análisis reporta sus <strong>métricas honestas</strong> (medidas sobre datos
          que el modelo no vio al entrenar), para que sepas qué tan confiable es antes de decidir.
        </p>
        <div className="flex items-start gap-2 rounded-lg bg-training-50 px-4 py-3 text-sm text-training-700">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            ¿No sabes por dónde empezar? Cada módulo trae una <strong>demo</strong> con datos de ejemplo
            del propio sistema, para verlo funcionar sin aportar datos.
          </p>
        </div>
      </section>

      <TechnicalDetails>
        <p>
          Dos motores, ambos entrenados <strong>en el momento</strong> (sin artefactos congelados): el
          análisis 3×3 por dominio (ventas/compras/almacén), con tres modelos por dominio —regresión,
          clasificación y clustering— sobre un formato fijo; y la predicción agnóstica, donde declaras tu
          propio esquema y traes columnas libres.
        </p>
        <p>
          Los modelos son scikit-learn livianos, con validación temporal sin fuga de datos y selección del
          ganador en una partición de validación. La interfaz no fabrica datos ni resultados: cuando una
          función todavía no está soportada, se muestra deshabilitada con la etiqueta «Próximamente».
        </p>
      </TechnicalDetails>
    </div>
  )
}
