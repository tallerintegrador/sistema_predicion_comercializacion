import type { ComponentType } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { useSeccionesVisibles } from './hooks/useSeccionesVisibles'
import { useAuth } from './auth/useAuth'
import type { View } from './theme/modules'
import { LoginPage } from './pages/LoginPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { HomePage } from './pages/HomePage'
import { AboutPage } from './pages/AboutPage'
import { CatalogPage } from './pages/CatalogPage'
import { SalesPage } from './pages/SalesPage'
import { PurchasesPage } from './pages/PurchasesPage'
import { InventoryPage } from './pages/InventoryPage'
import { LibrePage } from './pages/LibrePage'
import { UsersPage } from './pages/UsersPage'

/** Componente de página por sección. La visibilidad la decide el permiso, no este mapa. */
const PAGES: Record<View, ComponentType> = {
  home: HomePage,
  catalog: CatalogPage,
  sales: SalesPage,
  purchases: PurchasesPage,
  inventory: InventoryPage,
  auto: LibrePage,
  users: UsersPage,
  about: AboutPage,
}

/** Panel principal (con sesión y onboarding resuelto): rutas dentro del layout. */
function MainApp() {
  const secciones = useSeccionesVisibles()

  if (secciones.length === 0) {
    return (
      <div className="flex min-h-full items-center justify-center px-4 text-center text-sm text-slate-500">
        Su rol no tiene acceso a ninguna sección. Solicite permisos a un administrador.
      </div>
    )
  }

  // Destino de respaldo: primera sección permitida (para rutas desconocidas o sin acceso).
  const inicio = secciones[0].path

  return (
    <Routes>
      <Route element={<Layout />}>
        {secciones.map((s) => {
          const Page = PAGES[s.id]
          return <Route key={s.id} path={s.path} element={<Page />} />
        })}
        <Route path="*" element={<Navigate to={inicio} replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  const { status, user, isAdmin } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex min-h-full items-center justify-center text-sm text-slate-500">
        Cargando…
      </div>
    )
  }

  if (status === 'anon' || !user) return <LoginPage />

  // Onboarding obligatorio en el primer ingreso de un usuario no administrador.
  if (!user.onboarding_done && !isAdmin) return <OnboardingPage />

  return <MainApp />
}
