import { History } from 'lucide-react'
import { ComingSoon } from '../ui/ComingSoon'

/**
 * Aviso honesto de **reutilización del historial entre módulos** (sección F del rediseño).
 *
 * El corpus del cliente ya se persiste en el backend (ADR-0011), pero el frontend aún no
 * puede leer ese historial guardado. Por eso la experiencia se muestra, pero **deshabilitada**
 * y rotulada «Próximamente»: nunca se simula que el historial ya está cargado. Queda
 * registrado en docs/alineacion_frontend_backend.md (AGREGAR EN BACKEND: exponer el historial
 * guardado del cliente al frontend).
 */
export function ReuseHistoryNotice() {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50/60 px-3 py-2 text-xs text-slate-500">
      <History className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
      <p className="flex-1">
        Pronto podrás reutilizar el historial que ya cargaste: solo tendrías que añadir el estado
        actual de tu inventario, sin volver a subir tus ventas pasadas.{' '}
        <ComingSoon className="align-middle" />
      </p>
    </div>
  )
}
