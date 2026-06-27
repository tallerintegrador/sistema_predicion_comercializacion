import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Estado vacío amigable y honesto (ADR-0020): se usa cuando todavía no hay datos o
 * resultados. Nunca rellena con datos inventados; explica el siguiente paso.
 */
export function EmptyState({
  icon: Icon,
  title,
  message,
  children,
}: {
  icon?: LucideIcon
  title: string
  message?: string
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50/60 px-6 py-10 text-center">
      {Icon && <Icon aria-hidden="true" className="mb-3 h-10 w-10 text-slate-300" />}
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {message && <p className="mt-1 max-w-md text-sm text-slate-500">{message}</p>}
      {children && <div className="mt-4 flex flex-wrap items-center justify-center gap-3">{children}</div>}
    </div>
  )
}
