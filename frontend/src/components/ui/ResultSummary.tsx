import { Lightbulb } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Tarjeta de resumen en lenguaje natural (ADR-0019): destaca, en una frase clara, qué
 * significa el resultado. El texto lo calculan funciones puras sobre datos reales
 * (utils/resumen.ts); aquí solo se presenta con el acento del módulo.
 */
export function ResultSummary({
  text,
  tone = 'bg-brand-50 text-brand-900',
  children,
}: {
  text: string
  /** Clases de tinte (bg + text) del acento del módulo. */
  tone?: string
  children?: ReactNode
}) {
  return (
    <div className={`flex items-start gap-3 rounded-xl px-4 py-3 ${tone}`} role="status">
      <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 opacity-80" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium leading-relaxed">{text}</p>
        {children}
      </div>
    </div>
  )
}
