/**
 * Etiqueta "Próximamente" (ADR-0020). Marca de forma honesta una función que se muestra
 * en la interfaz pero que el backend aún no soporta: el control queda visible y
 * deshabilitado, nunca se simula un resultado. Ver docs/alineacion_frontend_backend.md.
 */
export function ComingSoon({ className = '' }: { className?: string }) {
  return (
    <span
      className={`badge bg-amber-100 text-amber-800 ${className}`}
      title="Función planificada; aún no está disponible"
    >
      Próximamente
    </span>
  )
}
