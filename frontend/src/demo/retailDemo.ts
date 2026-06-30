/**
 * Datos de ejemplo (rico) compartidos por «Ventas» y «Compras». Una mini cadena minorista:
 * 3 tiendas × 60 días con señal semanal + promociones + clima, con columnas libres
 * (incluye `unidades_vendidas` E `ingresos` para que ambas intenciones funcionen). «Compras»
 * además necesita los productos a reponer (stock/entrega/cobertura).
 *
 * Pensado para demostrar el motor agnóstico (ADR-0023) sin que el usuario traiga datos.
 */
import type { AutoRow } from '../api/types'

interface SerieDemo {
  tienda: string
  sku: string
  categoria: string
  base: number
  precio: number
  elas: number
}

const SERIES_DEMO: SerieDemo[] = [
  { tienda: 'lima_norte', sku: 'ARROZ-5KG', categoria: 'abarrotes', base: 52, precio: 24.9, elas: 0.6 },
  { tienda: 'arequipa', sku: 'GASEOSA-3L', categoria: 'bebidas', base: 47, precio: 9.9, elas: 1.6 },
  { tienda: 'trujillo', sku: 'LECHE-1L', categoria: 'lacteos', base: 70, precio: 4.5, elas: 0.5 },
]

const CLIMAS = ['soleado', 'nublado', 'lluvia']

/** Historial sintético con señal (semanal + promociones + precio/clima). */
export function generarFilasDemo(dias = 60): AutoRow[] {
  const inicio = new Date('2024-01-01')
  const rows: AutoRow[] = []
  for (const s of SERIES_DEMO) {
    for (let i = 0; i < dias; i++) {
      const d = new Date(inicio)
      d.setDate(d.getDate() + i)
      const finde = d.getDay() === 0 || d.getDay() === 6
      const promo = i % 9 < 4 ? 1 : 0
      const descuento = promo ? [10, 15, 20, 25][i % 4] : 0
      const precio = Math.round(s.precio * (1 - descuento / 100) * 100) / 100
      const estacional = 1 + 0.25 * Math.sin((2 * Math.PI * i) / 7)
      const findeF = finde ? (s.categoria === 'bebidas' ? 1.2 : 1.1) : 1
      const promoF = promo ? 1.12 : 1
      const precioF = Math.pow(precio / s.precio, -s.elas)
      const unidades = Math.max(0, Math.round(s.base * estacional * findeF * promoF * precioF))
      rows.push({
        fecha: d.toISOString().slice(0, 10),
        tienda: s.tienda,
        sku: s.sku,
        categoria: s.categoria,
        unidades_vendidas: unidades,
        ingresos: Math.round(unidades * precio * 100) / 100,
        precio,
        en_promo: promo,
        descuento_pct: descuento,
        clima: CLIMAS[i % 3],
        es_finde: finde ? 1 : 0,
      })
    }
  }
  return rows
}

/** Productos a reponer (Compras): stock actual, tiempo de entrega y cobertura objetivo. */
export function generarItemsDemo(): AutoRow[] {
  return SERIES_DEMO.map((s) => ({
    tienda: s.tienda,
    sku: s.sku,
    current_stock: Math.round(s.base * 2),
    lead_time_days: 5,
    target_coverage_days: 14,
  }))
}

/** Estado del inventario (Almacén): stock actual y tiempo de entrega por serie. */
export function generarItemsDemoAlmacen(): AutoRow[] {
  return SERIES_DEMO.map((s) => ({
    tienda: s.tienda,
    sku: s.sku,
    current_stock: Math.round(s.base * 1.2),
    lead_time_days: 5,
  }))
}
