/**
 * Contexto y hook de **autenticación**. Separado de `AuthContext.tsx` (que solo exporta el
 * componente `AuthProvider`) para que Fast Refresh funcione: un archivo de componentes no
 * debe exportar además hooks/objetos.
 */
import { createContext, useContext } from 'react'
import type { SessionUser } from '../api/auth'

export type Estado = 'loading' | 'anon' | 'authed'

export interface AuthContextValue {
  status: Estado
  user: SessionUser | null
  login: (userId: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  hasPerm: (key: string) => boolean
  canModule: (domain: string) => boolean
  isAdmin: boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>.')
  return ctx
}
