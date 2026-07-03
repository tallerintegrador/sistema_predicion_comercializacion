/**
 * Tooltip informativo discreto (A7): un ⓘ que muestra una explicación al pasar el cursor.
 * Sin dependencias externas; accesible (role="tooltip" + texto para lectores de pantalla).
 */
interface InfoTooltipProps {
  text: string
  className?: string
}

export function InfoTooltip({ text, className = '' }: InfoTooltipProps) {
  return (
    <span className={`group relative inline-flex align-middle ${className}`}>
      <span
        className="inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-slate-300 text-[9px] font-bold leading-none text-slate-400"
        aria-hidden="true"
      >
        i
      </span>
      <span className="sr-only">{text}</span>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1 w-56 -translate-x-1/2 rounded-md bg-slate-800 px-2.5 py-1.5 text-xs font-normal leading-snug text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  )
}
