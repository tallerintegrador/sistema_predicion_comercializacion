import type { ReactNode } from 'react'
import { LogOut } from 'lucide-react'
import { apiBaseUrl } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { SECTIONS, type SectionDef, type View } from '../theme/modules'

export type { View }

/** Secciones visibles para el usuario actual, según sus permisos (la verdad la da el backend). */
export function useSeccionesVisibles(): SectionDef[] {
  const { hasPerm } = useAuth()
  return SECTIONS.filter((item) => item.perms.every(hasPerm))
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
  const { user, logout, isAdmin } = useAuth()
  const items = useSeccionesVisibles()

  return (
    <div className="flex min-h-full">
      <aside className="flex w-16 flex-col border-r border-slate-200 bg-white transition-all md:w-64">
        <div className="flex items-center gap-3 border-b border-slate-200 px-3 py-4 md:px-4">
          {/* Monograma de marca (ADR-0017): cuadrado redondeado con el color primario. */}
          <span
            aria-hidden="true"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold tracking-wide text-white"
          >
            SPC
          </span>
          <div className="hidden md:block">
            <h1 className="text-lg font-bold leading-tight text-slate-900">SPC</h1>
            <p className="text-xs text-slate-500">Pronóstico para tu negocio</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-2 py-3" aria-label="Secciones">
          {items.map((item) => {
            const Icon = item.icon
            const isActive = active === item.id
            return (
              <button
                key={item.id}
                onClick={() => onChange(item.id)}
                aria-current={isActive ? 'page' : undefined}
                title={item.label}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 ${
                  isActive ? item.accent.navActive : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                <span className="hidden truncate md:inline">{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="border-t border-slate-200 px-3 py-3 md:px-4">
          <p className="hidden truncate text-sm font-medium text-slate-700 md:block" title={user?.user_id}>
            {user?.user_id}
          </p>
          <p className="mb-2 hidden truncate text-xs text-slate-400 md:block" title={user?.role}>
            {user?.role}
          </p>
          <button className="btn-ghost w-full text-xs" onClick={logout} title="Cerrar sesión">
            <LogOut className="h-4 w-4" aria-hidden="true" />
            <span className="hidden md:inline">Cerrar sesión</span>
          </button>
        </div>
      </aside>

      <div className="flex min-h-full flex-1 flex-col">
        {/* La dirección técnica de la API solo se muestra al administrador. */}
        {isAdmin && (
          <header className="flex items-center justify-end border-b border-slate-200 bg-white px-6 py-2">
            <span className="badge bg-slate-100 text-slate-500" title="Conexión con el servidor">
              Servidor: {apiBaseUrl}
            </span>
          </header>
        )}
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">{children}</main>
        <footer className="flex flex-wrap items-center justify-center gap-1 border-t border-slate-200 px-4 py-3 text-center text-xs text-slate-400">
          <span>Las estimaciones son referenciales y se basan en un comercio de ejemplo.</span>
          <button
            type="button"
            onClick={() => onChange('about')}
            className="font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200"
          >
            Acerca del sistema
          </button>
        </footer>
      </div>
    </div>
  )
}
