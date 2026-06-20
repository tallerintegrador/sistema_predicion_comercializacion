import type { ReactNode } from 'react'
import { apiBaseUrl } from '../api/client'

export type View = 'catalog' | 'sales' | 'purchases' | 'inventory'

const TABS: { id: View; label: string }[] = [
  { id: 'catalog', label: 'Catálogo' },
  { id: 'sales', label: 'Ventas' },
  { id: 'purchases', label: 'Compras' },
  { id: 'inventory', label: 'Inventario' },
]

export function Layout({
  active,
  onChange,
  children,
}: {
  active: View
  onChange: (v: View) => void
  children: ReactNode
}) {
  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col px-4">
      <header className="pt-6">
        <div className="flex items-baseline justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">SPC</h1>
            <p className="text-sm text-slate-500">
              Sistema Predictivo de Comercialización — plataforma de pronóstico para PYMEs
            </p>
          </div>
          <span className="badge bg-slate-100 text-slate-500" title="API conectada">
            API: {apiBaseUrl}
          </span>
        </div>
        <nav className="mt-4 flex gap-1 border-b border-slate-200">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => onChange(t.id)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                active === t.id
                  ? 'border-indigo-600 text-indigo-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="flex-1 py-6">{children}</main>
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-400">
        Modelo congelado (opción A) · contrato v1.0.1 · ajuste por cliente diferido
      </footer>
    </div>
  )
}
