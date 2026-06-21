import type { ReactNode } from 'react'

/**
 * Bloque colapsable "Detalles técnicos" (ADR-0019). Cualquier término técnico necesario
 * (versión de contrato, nombre de modelo, métricas internas) vive AQUÍ, oculto por
 * defecto, para no exponer tecnicismos al usuario no técnico.
 */
export function TechnicalDetails({
  children,
  title = 'Detalles técnicos',
}: {
  children: ReactNode
  title?: string
}) {
  return (
    <details className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <summary className="cursor-pointer select-none text-xs font-medium text-slate-500 hover:text-slate-700">
        {title}
      </summary>
      <div className="mt-2 space-y-1 text-xs leading-relaxed text-slate-500">{children}</div>
    </details>
  )
}
