/** Columnas numéricas del editor de items por dominio (motor agnóstico, ADR-0023). */
export interface NumCol {
  key: string
  label: string
  help: string
  /** Valor por defecto al agregar una fila en blanco. */
  default: number
}

/** Compras: stock actual + tiempo de entrega + cobertura objetivo. */
export const ITEM_COLS_COMPRAS: NumCol[] = [
  { key: 'current_stock', label: 'Stock actual', help: 'Existencias hoy', default: 0 },
  { key: 'lead_time_days', label: 'Días de entrega', help: 'Tiempo del proveedor', default: 5 },
  { key: 'target_coverage_days', label: 'Días de cobertura', help: 'Cuánto quieres cubrir', default: 14 },
]

/** Almacén: stock actual + tiempo de entrega. */
export const ITEM_COLS_ALMACEN: NumCol[] = [
  { key: 'current_stock', label: 'Stock actual', help: 'Existencias hoy', default: 0 },
  { key: 'lead_time_days', label: 'Días de entrega', help: 'Tiempo del proveedor', default: 5 },
]
