import { useEffect, useState } from 'react'
import { getProfileOptions, saveProfile } from '../api/auth'
import type { ProfileOptions } from '../api/auth'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'

/**
 * Onboarding del negocio (primer ingreso de un usuario no administrador). Las opciones
 * (sector/tamaño/región/moneda) las sirve el backend (GET /profile/options); no se
 * clavan en la UI. Al guardar, queda ligado al cliente del usuario (X-Client-Id).
 */
export function OnboardingPage() {
  const { refreshUser, logout } = useAuth()
  const [opciones, setOpciones] = useState<ProfileOptions | null>(null)
  const [form, setForm] = useState({
    business_name: '',
    sector: '',
    size: '',
    region: '',
    currency: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getProfileOptions()
      .then(setOpciones)
      .catch(() => setError('No se pudieron cargar las opciones del formulario.'))
  }, [])

  const set = (campo: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [campo]: e.target.value })

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await saveProfile(form)
      await refreshUser() // ahora onboarding_done = true → la app muestra el panel principal
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar el perfil.')
    } finally {
      setBusy(false)
    }
  }

  const completo = form.business_name && form.sector && form.size && form.region && form.currency

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">Cuéntenos sobre su negocio</h1>
        <button className="btn-ghost" onClick={logout}>Cerrar sesión</button>
      </div>

      <p className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
        El modelo está calibrado sobre el cliente de referencia (Favorita). Para otros rubros los
        resultados son <strong>referenciales</strong>, no una garantía de exactitud.
      </p>

      <form onSubmit={onSubmit} className="card space-y-4">
        <div>
          <label className="label" htmlFor="business_name">Nombre del negocio</label>
          <input
            id="business_name"
            className="input"
            value={form.business_name}
            onChange={set('business_name')}
            placeholder="Mi empresa S.A."
            required
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="sector">Rubro / sector</label>
            <select id="sector" className="input" value={form.sector} onChange={set('sector')} required>
              <option value="" disabled>Seleccione…</option>
              {opciones?.sectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="size">Tamaño aproximado</label>
            <select id="size" className="input" value={form.size} onChange={set('size')} required>
              <option value="" disabled>Seleccione…</option>
              {opciones?.sizes.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="region">Región</label>
            <select id="region" className="input" value={form.region} onChange={set('region')} required>
              <option value="" disabled>Seleccione…</option>
              {opciones?.regions.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="currency">Moneda</label>
            <select id="currency" className="input" value={form.currency} onChange={set('currency')} required>
              <option value="" disabled>Seleccione…</option>
              {opciones?.currencies.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        {error && (
          <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>
        )}

        <button className="btn-primary w-full" type="submit" disabled={busy || !completo}>
          {busy ? 'Guardando…' : 'Guardar y continuar'}
        </button>
      </form>
    </div>
  )
}
