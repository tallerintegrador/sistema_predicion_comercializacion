import { useState } from 'react'
import { CheckCircle2, Database, Scale } from 'lucide-react'
import { TrainingPanel } from '../components/TrainingPanel'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { ComingSoon } from '../components/ui/ComingSoon'

/** Qué predicción se quiere mejorar. Hoy solo Ventas se entrena; Almacén está planificado. */
type Objetivo = 'sales' | 'inventory'

/**
 * Sección **Mejorar las predicciones** (reentrenamiento por cliente). Punto de entrada
 * honesto y en lenguaje claro: el sistema usa por defecto un "modelo base"; el usuario
 * puede entrenar uno con su propia historia, y solo se adopta si de verdad mejora. No se
 * simulan métricas: el estado real lo muestra `TrainingPanel` (ADR-0013).
 *
 * El insumo de entrenamiento es UNA sola plantilla: el historial de ventas (la misma de
 * Ventas). El inventario NO es dato de entrenamiento, por eso aquí no se pide. Se puede
 * elegir qué mejorar: Ventas (disponible) o Almacén («Próximamente»); Compras no se entrena
 * por separado, mejora cuando mejora Ventas.
 */
export function TrainingPage() {
  const [objetivo, setObjetivo] = useState<Objetivo>('sales')

  return (
    <div className="space-y-5">
      <ModuleHeader view="training" />

      <section className="card space-y-4">
        <div>
          <h3 className="text-base font-semibold text-slate-800">¿Qué quieres mejorar?</h3>
          <p className="text-sm text-slate-600">
            Elige qué predicción afinar con tu propia historia. El insumo es siempre el mismo: tu
            historial de ventas.
          </p>
        </div>

        <fieldset className="grid gap-3 sm:grid-cols-2">
          <legend className="sr-only">Qué predicción quieres mejorar</legend>
          <ObjetivoOpcion
            value="sales"
            checked={objetivo === 'sales'}
            onChange={() => setObjetivo('sales')}
            titulo="Ventas"
            descripcion="Afina el pronóstico de demanda con tu historial de ventas."
          />
          <ObjetivoOpcion
            value="inventory"
            checked={false}
            disabled
            titulo="Almacén"
            descripcion="Afinar el riesgo de agotamiento con tus datos."
            badge={<ComingSoon />}
          />
        </fieldset>

        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <strong>Compras</strong> no se entrena por separado: mejora automáticamente cuando mejora
          Ventas (su recomendación se calcula a partir del pronóstico de ventas).
        </p>
      </section>

      <section className="card space-y-4">
        <h3 className="text-base font-semibold text-slate-800">Cómo funciona</h3>
        <p className="text-sm leading-relaxed text-slate-600">
          De forma predeterminada, el sistema usa un <strong>modelo base</strong> entrenado con datos
          de un comercio de ejemplo. Si tienes suficiente historia propia, puedes pedirle que aprenda
          de <strong>tus</strong> datos. El sistema compara tu versión con la base y{' '}
          <strong>solo la adopta si mejora de verdad</strong>.
        </p>

        <ul className="space-y-3">
          <Punto icon={Database} titulo="Necesitas suficientes datos">
            Se recomienda al menos alrededor de <strong>un año de ventas</strong> y varios registros por
            producto. Con muy pocos datos, entrenar no suele ayudar.
            <span className="ml-2 inline-flex items-center gap-1 align-middle">
              <ComingSoon />
              <span className="text-xs text-slate-400">verificación automática de datos suficientes</span>
            </span>
          </Punto>
          <Punto icon={Scale} titulo="Se mide si realmente mejora">
            El sistema evalúa tu modelo con tu propia historia de forma honesta. Si no supera al modelo
            base, mantiene la base.
          </Punto>
          <Punto icon={CheckCircle2} titulo="«No mejora» es un resultado válido">
            Es normal que, con ciertos negocios o pocos datos, el modelo propio no mejore. En ese caso no
            pasa nada: sigues con la base, que ya funciona.
          </Punto>
        </ul>
      </section>

      {objetivo === 'sales' && <TrainingPanel />}
    </div>
  )
}

/** Una opción del selector «¿Qué quieres mejorar?» (radio accesible con tarjeta). */
function ObjetivoOpcion({
  value,
  checked,
  onChange,
  disabled = false,
  titulo,
  descripcion,
  badge,
}: {
  value: Objetivo
  checked: boolean
  onChange?: () => void
  disabled?: boolean
  titulo: string
  descripcion: string
  badge?: React.ReactNode
}) {
  return (
    <label
      className={`flex items-start gap-3 rounded-lg border p-3 transition-colors ${
        checked ? 'border-training-600 bg-training-50' : 'border-slate-200'
      } ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:border-slate-300'}`}
    >
      <input
        type="radio"
        name="objetivo-entrenamiento"
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="mt-1"
      />
      <span>
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          {titulo}
          {badge}
        </span>
        <span className="mt-0.5 block text-xs text-slate-500">{descripcion}</span>
      </span>
    </label>
  )
}

function Punto({
  icon: Icon,
  titulo,
  children,
}: {
  icon: typeof Database
  titulo: string
  children: React.ReactNode
}) {
  return (
    <li className="flex items-start gap-3">
      <span aria-hidden="true" className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-training-100 text-training-700">
        <Icon className="h-4 w-4" />
      </span>
      <div>
        <p className="text-sm font-semibold text-slate-800">{titulo}</p>
        <p className="text-sm leading-relaxed text-slate-600">{children}</p>
      </div>
    </li>
  )
}
