import { useId, type ReactNode } from 'react'

/**
 * Paso de un flujo guiado (datos → configuración → acción). Da jerarquía visual con una
 * insignia numerada con el acento del módulo, un título y una descripción opcional, para
 * que el usuario entienda la secuencia. El número es decorativo (el lector de pantalla lo
 * anuncia con la palabra «Paso»). El cuerpo lo aporta cada pantalla.
 */
export function StepSection({
  step,
  title,
  description,
  accentChip = 'bg-brand-100 text-brand-700',
  children,
}: {
  step: number
  title: string
  description?: ReactNode
  /** Clases del acento del módulo para la insignia (literal completo de Tailwind). */
  accentChip?: string
  children: ReactNode
}) {
  const headingId = useId()
  return (
    <section className="card" aria-labelledby={headingId}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${accentChip}`}
        >
          {step}
        </span>
        <div className="min-w-0 flex-1">
          <h3 id={headingId} className="text-base font-semibold text-slate-800">
            <span className="sr-only">Paso {step}: </span>
            {title}
          </h3>
          {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
        </div>
      </div>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  )
}
