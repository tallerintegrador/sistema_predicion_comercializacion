import { useEffect, useState } from 'react'
import { Layout, useSeccionesVisibles } from './components/Layout'
import type { View } from './components/Layout'
import { useAuth } from './auth/AuthContext'
import { LoginPage } from './pages/LoginPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { HomePage } from './pages/HomePage'
import { AboutPage } from './pages/AboutPage'
import { CatalogPage } from './pages/CatalogPage'
import { SalesPage } from './pages/SalesPage'
import { PurchasesPage } from './pages/PurchasesPage'
import { InventoryPage } from './pages/InventoryPage'
import { TrainingPage } from './pages/TrainingPage'
import { UsersPage } from './pages/UsersPage'

/** Panel principal (con sesión y onboarding resuelto): sidebar + sección activa. */
function MainApp() {
  const secciones = useSeccionesVisibles()
  const [view, setView] = useState<View | null>(null)

  // Vista por defecto = primera sección permitida; corrige si la actual deja de estar visible.
  useEffect(() => {
    if (secciones.length === 0) return
    if (view === null || !secciones.some((s) => s.id === view)) {
      setView(secciones[0].id)
    }
  }, [secciones, view])

  if (secciones.length === 0) {
    return (
      <div className="flex min-h-full items-center justify-center px-4 text-center text-sm text-slate-500">
        Su rol no tiene acceso a ninguna sección. Solicite permisos a un administrador.
      </div>
    )
  }

  const activo = view ?? secciones[0].id

  return (
    <Layout active={activo} onChange={setView}>
      {activo === 'home' && <HomePage onNavigate={setView} />}
      {activo === 'catalog' && <CatalogPage />}
      {activo === 'sales' && <SalesPage />}
      {activo === 'purchases' && <PurchasesPage />}
      {activo === 'inventory' && <InventoryPage />}
      {activo === 'training' && <TrainingPage />}
      {activo === 'users' && <UsersPage />}
      {activo === 'about' && <AboutPage />}
    </Layout>
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
