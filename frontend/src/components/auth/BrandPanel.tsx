import { TrendingUp, ShoppingCart, PackageCheck } from 'lucide-react'

/**
 * Panel de marca para las pantallas de acceso (ADR-0020). Da identidad y bienvenida con el
 * gradiente de marca, el monograma, la tagline y tres beneficios en lenguaje claro. Se
 * oculta en pantallas pequeñas (el formulario manda en móvil).
 */
export function BrandPanel() {
  return (
    <div className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-600 to-brand-800 p-10 text-white lg:flex">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 text-base font-bold tracking-wide"
        >
          SPC
        </span>
        <div>
          <p className="text-lg font-bold leading-tight">SPC</p>
          <p className="text-sm text-brand-100">Pronóstico para PYMEs</p>
        </div>
      </div>

      <div>
        <h2 className="max-w-xs text-2xl font-bold leading-snug">
          Anticipa tu demanda y decide con datos
        </h2>
        <ul className="mt-6 space-y-4 text-sm text-brand-50">
          <Beneficio icon={TrendingUp} texto="Estima cuánto vas a vender en los próximos días, semanas o meses." />
          <Beneficio icon={ShoppingCart} texto="Sabe cuánto y cuándo reponer cada producto." />
          <Beneficio icon={PackageCheck} texto="Evita quedarte sin existencias con avisos a tiempo." />
        </ul>
      </div>

      <p className="text-xs text-brand-200">
        Estimaciones referenciales, basadas en un comercio de ejemplo.
      </p>
    </div>
  )
}

function Beneficio({ icon: Icon, texto }: { icon: typeof TrendingUp; texto: string }) {
  return (
    <li className="flex items-start gap-3">
      <span aria-hidden="true" className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/15">
        <Icon className="h-4 w-4" />
      </span>
      <span>{texto}</span>
    </li>
  )
}
