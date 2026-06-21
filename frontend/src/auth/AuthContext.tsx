/**
 * Contexto de **autenticación y autorización** del frontend (ADR-0014/0015).
 *
 * Mantiene la sesión (usuario + permisos) y la restaura al recargar si hay un token
 * guardado. Expone helpers de permisos (`hasPerm`, `canModule`) que la UI usa para
 * filtrar el sidebar y proteger pantallas. La autorización REAL la aplica el backend en
 * cada endpoint: esto es solo experiencia de usuario (no mostrar lo que no se puede usar).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getMe, login as apiLogin } from '../api/auth'
import type { SessionUser } from '../api/auth'
import { getAuthToken, setAuthToken, setUnauthorizedHandler } from '../api/client'

type Estado = 'loading' | 'anon' | 'authed'

interface AuthContextValue {
  status: Estado
  user: SessionUser | null
  login: (userId: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  hasPerm: (key: string) => boolean
  canModule: (domain: string) => boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Estado>('loading')
  const [user, setUser] = useState<SessionUser | null>(null)

  const logout = useCallback(() => {
    setAuthToken(null)
    setUser(null)
    setStatus('anon')
  }, [])

  // Si el backend rechaza el token (p. ej. expiró), cerramos sesión limpiamente.
  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  // Restauración de sesión al arrancar: si hay token, validarlo con /auth/me.
  useEffect(() => {
    let activo = true
    if (!getAuthToken()) {
      setStatus('anon')
      return
    }
    getMe()
      .then((u) => {
        if (!activo) return
        setUser(u)
        setStatus('authed')
      })
      .catch(() => {
        if (!activo) return
        setAuthToken(null)
        setStatus('anon')
      })
    return () => {
      activo = false
    }
  }, [])

  const login = useCallback(async (userId: string, password: string) => {
    const res = await apiLogin(userId, password)
    setAuthToken(res.token)
    setUser(res.user)
    setStatus('authed')
  }, [])

  const refreshUser = useCallback(async () => {
    const u = await getMe()
    setUser(u)
  }, [])

  const hasPerm = useCallback((key: string) => !!user?.permissions.includes(key), [user])
  const canModule = useCallback(
    (domain: string) => !!user?.permissions.includes(`module:${domain}`),
    [user],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login,
      logout,
      refreshUser,
      hasPerm,
      canModule,
      isAdmin: hasPerm('action:users_manage'),
    }),
    [status, user, login, logout, refreshUser, hasPerm, canModule],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>.')
  return ctx
}
