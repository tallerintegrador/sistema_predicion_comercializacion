import { useAuth } from '../auth/useAuth'
import { SECTIONS, type SectionDef } from '../theme/modules'

/** Secciones visibles para el usuario actual, según sus permisos (la verdad la da el backend). */
export function useSeccionesVisibles(): SectionDef[] {
  const { hasPerm } = useAuth()
  return SECTIONS.filter((item) => item.perms.every(hasPerm))
}
