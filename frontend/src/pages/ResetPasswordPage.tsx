import { useState } from 'react'
import { ApiError } from '../api/client'
import { resetPassword } from '../api/auth'
import { BrandPanel } from '../components/auth/BrandPanel'
import { PasswordInput } from '../components/auth/PasswordInput'

/**
 * Pantalla de restablecimiento: se abre desde el enlace del correo (`/reset?token=...`).
 * Lee el token de la URL, pide la nueva contraseña y la confirma contra el backend.
 */
export function ResetPasswordPage() {
  const token = new URLSearchParams(window.location.search).get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirmar, setConfirmar] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [ok, setOk] = useState(false)

  const irALogin = () => {
    // Vuelve a la raíz limpiando el token de la URL (la app renderiza el login).
    window.history.replaceState(null, '', '/')
    window.location.assign('/')
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password !== confirmar) {
      setError('Las contraseñas no coinciden.')
      return
    }
    setBusy(true)
    try {
      await resetPassword(token, password)
      setOk(true)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'No pudimos restablecer tu contraseña. Solicita un enlace nuevo.',
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
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-slate-900">Elige una nueva contraseña</h1>
            <p className="mt-1 text-sm text-slate-500">
              Escribe tu nueva contraseña. El enlace caduca pronto y solo puede usarse una vez.
            </p>
          </div>

          {!token ? (
            <div className="space-y-4">
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                Enlace inválido: falta el token. Solicita un nuevo enlace desde «¿Olvidaste tu contraseña?».
              </p>
              <button type="button" className="btn-ghost w-full" onClick={irALogin}>
                Ir a iniciar sesión
              </button>
            </div>
          ) : ok ? (
            <div className="space-y-4">
              <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">
                Tu contraseña se actualizó. Ya puedes iniciar sesión con la nueva.
              </p>
              <button type="button" className="btn-primary w-full" onClick={irALogin}>
                Ir a iniciar sesión
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div>
                <label className="label" htmlFor="new_password">
                  Nueva contraseña
                </label>
                <PasswordInput
                  id="new_password"
                  value={password}
                  onChange={setPassword}
                  autoComplete="new-password"
                  placeholder="Al menos 4 caracteres"
                  required
                />
              </div>
              <div>
                <label className="label" htmlFor="confirm_password">
                  Confirmar contraseña
                </label>
                <PasswordInput
                  id="confirm_password"
                  value={confirmar}
                  onChange={setConfirmar}
                  autoComplete="new-password"
                  placeholder="Repite la contraseña"
                  required
                />
              </div>

              {error && (
                <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                  {error}
                </p>
              )}

              <button
                className="btn-primary w-full"
                type="submit"
                disabled={busy || password.length < 4 || !confirmar}
              >
                {busy ? 'Guardando…' : 'Guardar contraseña'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
