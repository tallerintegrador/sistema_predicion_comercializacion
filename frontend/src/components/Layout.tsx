import type { ReactNode } from 'react'
import { apiBaseUrl } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export type View =
  | 'catalog'
  | 'sales'
  | 'purchases'
  | 'inventory'
  | 'training'
  | 'users'

interface NavItem {
  id: View
  label: string
  /** Permiso(s) requerido(s) para ver la sección (todos deben cumplirse). */
  perms: string[]
}

// El orden del sidebar. Cada sección se muestra solo si el rol tiene sus permisos: la
// fuente de verdad de los permisos es el backend (/auth/me); aquí solo se filtra la vista.
export const NAV: NavItem[] = [
  { id: 'catalog', label: 'Catálogo', perms: ['action:catalog'] },
  { id: 'sales', label: 'Ventas', perms: ['module:sales'] },
  { id: 'purchases', label: 'Compras', perms: ['module:purchases'] },
  { id: 'inventory', label: 'Almacén', perms: ['module:inventory'] },
  { id: 'training', label: 'Reentrenamiento', perms: ['action:training'] },
  { id: 'users', label: 'Administración de usuarios', perms: ['action:users_manage'] },
]

/** Secciones visibles para el usuario actual, según sus permisos. */
export function useSeccionesVisibles(): NavItem[] {
  const { hasPerm } = useAuth()
  return NAV.filter((item) => item.perms.every(hasPerm))
}

export function Layout({
  active,
  onChange,
  children,
}: {
  active: View
  onChange: (v: View) => void
  children: ReactNode
}) {
  const { user, logout } = useAuth()
  const items = useSeccionesVisibles()

  return (
    <div className="flex min-h-full">
      <aside className="flex w-60 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-4">
          {/* Monograma de marca (ADR-0017): cuadrado redondeado con el color primario. */}
          <span
            aria-hidden="true"
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold tracking-wide text-white"
          >
            SPC
          </span>
          <div>
            <h1 className="text-lg font-bold leading-tight text-slate-900">SPC</h1>
            <p className="text-xs text-slate-500">Pronóstico para PYMEs</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-2 py-3">
          {items.map((item) => (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              aria-current={active === item.id ? 'page' : undefined}
              className={`block w-full rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 ${
                active === item.id
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="border-t border-slate-200 px-4 py-3">
          <p className="truncate text-sm font-medium text-slate-700" title={user?.user_id}>
            {user?.user_id}
          </p>
          <p className="mb-2 truncate text-xs text-slate-400" title={user?.role}>{user?.role}</p>
          <button className="btn-ghost w-full text-xs" onClick={logout}>Cerrar sesión</button>
        </div>
      </aside>

      <div className="flex min-h-full flex-1 flex-col">
        <header className="flex items-center justify-end border-b border-slate-200 bg-white px-6 py-2">
          <span className="badge bg-slate-100 text-slate-500" title="API conectada">
            API: {apiBaseUrl}
          </span>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-6">{children}</main>
        <footer className="border-t border-slate-200 py-3 text-center text-xs text-slate-400">
          Modelo congelado · contrato v1.0.1 · Favorita es cliente de ejemplo, no el producto ·
          reentrenamiento por cliente opt-in y experimental
        </footer>
      </div>
    </div>
  )
}
