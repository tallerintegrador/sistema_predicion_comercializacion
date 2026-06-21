import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { BrandPanel } from '../components/auth/BrandPanel'
import { PasswordInput } from '../components/auth/PasswordInput'

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
          ? 'Usuario o contraseña incorrectos. Inténtalo de nuevo.'
          : 'No pudimos iniciar sesión. Revisa tu conexión e inténtalo otra vez.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-slate-50 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid-cols-2">
        <BrandPanel />

        <div className="p-8 sm:p-10">
          {/* Marca para móvil (el panel de marca se oculta en pantallas pequeñas). */}
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <span
              aria-hidden="true"
              className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold tracking-wide text-white"
            >
              SPC
            </span>
            <div>
              <p className="font-bold leading-tight text-slate-900">SPC</p>
              <p className="text-xs text-slate-500">Pronóstico para PYMEs</p>
            </div>
          </div>

          <div className="mb-6">
            <h1 className="text-2xl font-bold text-slate-900">Bienvenido de nuevo</h1>
            <p className="mt-1 text-sm text-slate-500">Ingresa para ver tus pronósticos.</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div>
              <label className="label" htmlFor="user_id">
                Usuario
              </label>
              <input
                id="user_id"
                className="input"
                autoComplete="username"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="Tu identificador de usuario"
                required
                autoFocus
              />
            </div>

            <div>
              <label className="label" htmlFor="password">
                Contraseña
              </label>
              <PasswordInput
                id="password"
                value={password}
                onChange={setPassword}
                autoComplete="current-password"
                placeholder="Tu contraseña"
                required
              />
            </div>

            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {error}
              </p>
            )}

            <button className="btn-primary w-full" type="submit" disabled={busy || !userId.trim() || !password}>
              {busy ? 'Ingresando…' : 'Ingresar'}
            </button>
          </form>

          <p className="mt-6 rounded-lg bg-slate-50 px-3 py-2 text-center text-xs text-slate-400">
            Cuentas de demostración (no de producción): <strong>256317</strong> y <strong>256370</strong>,
            con contraseña igual al usuario.
          </p>
        </div>
      </div>
    </div>
  )
}
