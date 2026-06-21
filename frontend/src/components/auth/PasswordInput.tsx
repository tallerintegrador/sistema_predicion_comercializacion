import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

/**
 * Campo de contraseña con botón **mostrar/ocultar** accesible. Reutilizable en el login
 * (y donde haga falta). El botón no envía el formulario (`type="button"`) y describe su
 * acción con `aria-label`.
 */
export function PasswordInput({
  id,
  value,
  onChange,
  autoComplete = 'current-password',
  placeholder,
  required,
}: {
  id: string
  value: string
  onChange: (v: string) => void
  autoComplete?: string
  placeholder?: string
  required?: boolean
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        id={id}
        type={show ? 'text' : 'password'}
        className="input pr-11"
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}
        aria-pressed={show}
        className="absolute inset-y-0 right-0 flex items-center rounded-r-lg px-3 text-slate-400 transition-colors hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200"
      >
        {show ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
      </button>
    </div>
  )
}
