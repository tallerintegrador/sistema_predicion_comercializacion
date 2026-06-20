import { useState } from 'react'
import { Layout } from './components/Layout'
import type { View } from './components/Layout'
import { CatalogPage } from './pages/CatalogPage'
import { SalesPage } from './pages/SalesPage'
import { PurchasesPage } from './pages/PurchasesPage'
import { InventoryPage } from './pages/InventoryPage'

export default function App() {
  const [view, setView] = useState<View>('catalog')

  return (
    <Layout active={view} onChange={setView}>
      {view === 'catalog' && <CatalogPage />}
      {view === 'sales' && <SalesPage />}
      {view === 'purchases' && <PurchasesPage />}
      {view === 'inventory' && <InventoryPage />}
    </Layout>
  )
}
