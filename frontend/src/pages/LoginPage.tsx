import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'

/** Pantalla de ingreso (id + contraseña). Pública: única vista sin sesión. */
export function LoginPage() {
  const { login } = useAuth()
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(userId.trim(), password)
    } catch (err) {
      // Mensaje genérico: no revelamos si el id existe (igual que el backend).
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Id o contraseña incorrectos.'
          : 'No se pudo iniciar sesión. Verifique la conexión con el servidor.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-slate-900">SPC</h1>
          <p className="text-sm text-slate-500">Sistema Predictivo de Comercialización</p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">Iniciar sesión</h2>

          <div>
            <label className="label" htmlFor="user_id">Usuario</label>
            <input
              id="user_id"
              className="input"
              autoComplete="username"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="Id de usuario"
              required
            />
          </div>

          <div>
            <label className="label" htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              className="input"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
              {error}
            </p>
          )}

          <button className="btn-primary w-full" type="submit" disabled={busy || !userId || !password}>
            {busy ? 'Ingresando…' : 'Ingresar'}
          </button>

          <p className="text-center text-xs text-slate-400">
            Cuentas de demostración (no de producción): 256317 y 256370, con contraseña igual al id.
          </p>
        </form>
      </div>
    </div>
  )
}
