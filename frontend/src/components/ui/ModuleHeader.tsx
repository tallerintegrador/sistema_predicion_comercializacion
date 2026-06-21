import type { ReactNode } from 'react'
import { SECTION_BY_ID, type View } from '../../theme/modules'

/**
 * Encabezado de módulo (ADR-0020): ícono con el acento del módulo, título y una frase
 * clara de "qué hace y para qué sirve". Centraliza el copy en `theme/modules.ts`.
 */
export function ModuleHeader({ view, children }: { view: View; children?: ReactNode }) {
  const s = SECTION_BY_ID[view]
  const Icon = s.icon
  return (
    <section className="card">
      <div className="flex items-start gap-4">
        <span
          aria-hidden="true"
          className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${s.accent.chip}`}
        >
          <Icon className="h-6 w-6" />
        </span>
        <div className="min-w-0">
          <h2 className="text-xl font-semibold text-slate-900">{s.label}</h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.blurb}</p>
          {children}
        </div>
      </div>
    </section>
  )
}
