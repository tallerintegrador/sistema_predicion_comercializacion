import { useMemo } from 'react'

/**
 * Forma mínima para resumir un histórico cargado. La comparten el bloque `history` del
 * contrato y las filas editables (Compras/Almacén), de modo que el resumen sirve a las
 * tres pantallas sin fabricar datos: solo describe lo que el usuario ya ingresó.
 */
type SummarizableRow = { date?: string; store_id?: string; product_id?: string }

/** ¿La fila tiene algún dato real? (evita contar filas en blanco recién agregadas). */
function tieneDato(row: SummarizableRow): boolean {
  return Boolean(row.date || row.store_id || row.product_id)
}

/** Resumen del histórico cargado: filas, rango de fechas y series. */
export function HistoryPreview({ history }: { history: SummarizableRow[] }) {
  const summary = useMemo(() => {
    // Solo cuenta filas con contenido real: una fila en blanco NO suma a «Filas».
    const reales = history.filter(tieneDato)
    if (reales.length === 0) {
      return { rows: 0, from: '—', to: '—', stores: 0, products: 0 }
    }
    const dates = reales.map((h) => h.date).filter((d): d is string => !!d).sort()
    const stores = new Set(reales.map((h) => h.store_id).filter(Boolean))
    const products = new Set(reales.map((h) => h.product_id).filter(Boolean))
    return {
      rows: reales.length,
      from: dates[0] ?? '—',
      to: dates[dates.length - 1] ?? '—',
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
