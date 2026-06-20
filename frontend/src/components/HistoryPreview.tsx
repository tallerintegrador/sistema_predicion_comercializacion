import { useMemo } from 'react'
import type { HistoryItem } from '../api/types'

/** Resumen del bloque `history` cargado: filas, rango de fechas y series. */
export function HistoryPreview({ history }: { history: HistoryItem[] }) {
  const summary = useMemo(() => {
    if (history.length === 0) {
      return { rows: 0, from: '—', to: '—', stores: 0, products: 0 }
    }
    const dates = history.map((h) => h.date).sort()
    const stores = new Set(history.map((h) => h.store_id))
    const products = new Set(history.map((h) => h.product_id))
    return {
      rows: history.length,
      from: dates[0],
      to: dates[dates.length - 1],
      stores: stores.size,
      products: products.size,
    }
  }, [history])

  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <Chip label="Filas" value={summary.rows} />
      <Chip label="Tiendas" value={summary.stores} />
      <Chip label="Productos" value={summary.products} />
      <Chip label="Desde" value={summary.from} />
      <Chip label="Hasta" value={summary.to} />
    </div>
  )
}

function Chip({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="badge bg-slate-100 text-slate-700">
      <span className="text-slate-500">{label}:</span>&nbsp;<strong>{value}</strong>
    </span>
  )
}
