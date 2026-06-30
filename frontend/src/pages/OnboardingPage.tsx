import { useEffect, useMemo, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { getProfileOptions, saveProfile } from '../api/auth'
import type { ProfileOptions } from '../api/auth'
import { useAuth } from '../auth/useAuth'
import { ApiError } from '../api/client'
import {
  CURRENCY_LABELS,
  PREFERRED_ORDER,
  REGION_LABELS,
  SECTOR_LABELS,
  SIZE_LABELS,
  labelFor,
  orderCodes,
} from '../data/onboardingLabels'

type Campo = 'business_name' | 'sector' | 'size' | 'region' | 'currency'

interface SelectDef {
  key: Exclude<Campo, 'business_name'>
  label: string
  help: string
  options?: string[]
  map: Record<string, string>
  order?: string[]
}

/**
 * Onboarding del negocio (primer ingreso de un usuario no administrador). Las opciones
 * (sector/tamaño/región/moneda) las sirve el backend como códigos; aquí se muestran con
 * **etiquetas en español** (data/onboardingLabels.ts) sin cambiar el valor que se envía.
 */
export function OnboardingPage() {
  const { refreshUser, logout } = useAuth()
  const [opciones, setOpciones] = useState<ProfileOptions | null>(null)
  const [optError, setOptError] = useState<string | null>(null)
  const [form, setForm] = useState({
    business_name: '',
    sector: '',
    size: '',
    region: '',
    currency: '',
  })
  const [touched, setTouched] = useState<Set<Campo>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getProfileOptions()
      .then(setOpciones)
      .catch(() => setOptError('No pudimos cargar las opciones del formulario. Recarga la página e inténtalo otra vez.'))
  }, [])

  const selects: SelectDef[] = useMemo(
    () => [
      { key: 'sector', label: 'Rubro o sector', help: '¿A qué se dedica tu negocio?', options: opciones?.sectors, map: SECTOR_LABELS },
      { key: 'size', label: 'Tamaño aproximado', help: 'Según tu número de empleados o nivel de ventas.', options: opciones?.sizes, map: SIZE_LABELS },
      { key: 'region', label: 'Región o ubicación', help: 'Dónde opera principalmente tu negocio.', options: opciones?.regions, map: REGION_LABELS, order: PREFERRED_ORDER.region },
      { key: 'currency', label: 'Moneda', help: 'La moneda en la que registras tus ventas.', options: opciones?.currencies, map: CURRENCY_LABELS, order: PREFERRED_ORDER.currency },
    ],
    [opciones],
  )

  const set = (campo: Campo) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [campo]: e.target.value })
  const marcarTocado = (campo: Campo) => () => setTouched((t) => new Set(t).add(campo))
  const vacio = (campo: Campo) => form[campo].trim() === ''
  const mostrarError = (campo: Campo) => touched.has(campo) && vacio(campo)

  const completo = (Object.keys(form) as Campo[]).every((c) => !vacio(c))

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await saveProfile(form)
      await refreshUser() // ahora onboarding_done = true → la app muestra el panel principal
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No pudimos guardar tus datos. Inténtalo de nuevo.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-full bg-slate-50">
      {/* Cerrar sesión, discreto, para no competir con la acción principal. */}
      <div className="mx-auto flex max-w-2xl justify-end px-4 pt-4">
        <button
          type="button"
          onClick={logout}
          className="text-xs font-medium text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200"
        >
          Cerrar sesión
        </button>
      </div>

      <div className="mx-auto max-w-2xl px-4 pb-12 pt-2">
        {/* Bienvenida */}
        <div className="mb-5">
          <span className="badge bg-brand-50 text-brand-700">Paso de configuración inicial</span>
          <h1 className="mt-3 text-2xl font-bold text-slate-900">¡Te damos la bienvenida a SPC!</h1>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">
            Cuéntanos un poco sobre tu negocio para adaptar la experiencia a lo que necesitas. Es rápido y
            solo lo pediremos esta vez.
          </p>
        </div>

        {/* Honestidad, en lenguaje simple */}
        <div className="mb-5 flex items-start gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Nuestro sistema aprendió con los datos de un comercio de ejemplo. Para negocios de otros rubros,
            las predicciones son una <strong>referencia útil</strong>, no una cifra exacta. Más adelante
            podrás mejorarlas con tus propios datos.
          </p>
        </div>

        {optError && (
          <p className="mb-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
            {optError}
          </p>
        )}

        <form onSubmit={onSubmit} className="card space-y-5" noValidate>
          <div>
            <label className="label" htmlFor="business_name">
              Nombre del negocio
            </label>
            <input
              id="business_name"
              className="input"
              value={form.business_name}
              onChange={set('business_name')}
              onBlur={marcarTocado('business_name')}
              placeholder="Ej.: Bodega La Esquina"
              aria-invalid={mostrarError('business_name')}
              required
            />
            {mostrarError('business_name') && (
              <p className="mt-1 text-xs text-rose-600">Escribe el nombre de tu negocio.</p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            {selects.map((s) => (
              <div key={s.key}>
                <label className="label" htmlFor={s.key}>
                  {s.label}
                </label>
                <select
                  id={s.key}
                  className="input"
                  value={form[s.key]}
                  onChange={set(s.key)}
                  onBlur={marcarTocado(s.key)}
                  aria-invalid={mostrarError(s.key)}
                  required
                >
                  <option value="" disabled>
                    Selecciona una opción…
                  </option>
                  {orderCodes(s.options ?? [], s.order).map((code) => (
                    <option key={code} value={code}>
                      {labelFor(s.map, code)}
                    </option>
                  ))}
                </select>
                {mostrarError(s.key) ? (
                  <p className="mt-1 text-xs text-rose-600">Selecciona una opción.</p>
                ) : (
                  <p className="help">{s.help}</p>
                )}
              </div>
            ))}
          </div>

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
              {error}
            </p>
          )}

          <button className="btn-primary w-full" type="submit" disabled={busy || !completo}>
            {busy ? 'Guardando…' : 'Guardar y continuar'}
          </button>
        </form>
      </div>
    </div>
  )
}
