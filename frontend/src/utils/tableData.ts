/**
 * Utilidades para las tablas de entrada editables (carga manual). Las filas se guardan
 * como texto (lo que escribe el usuario) y se **coaccionan al tipo del contrato** al
 * enviar, usando el `type` de cada columna del catálogo. Así no se hardcodean tipos y se
 * respeta la validación estricta del backend (un entero es entero, no "5.0").
 */
import type { CatalogColumn, InputTable } from '../api/types'

/** Fila editable: cada columna guarda su valor como texto. */
export type EditableRow = Record<string, string>

/** Crea una fila vacía con todas las columnas de la tabla. */
export function emptyRow(table: InputTable): EditableRow {
  return Object.fromEntries(table.columns.map((c) => [c.name, '']))
}

/** ¿La fila tiene completos todos los campos obligatorios? */
export function rowComplete(columns: CatalogColumn[], row: EditableRow): boolean {
  return columns.every((c) => !c.required || (row[c.name] ?? '').trim() !== '')
}

/** ¿Todas las filas están completas (y hay al menos una)? */
export function rowsComplete(columns: CatalogColumn[], rows: EditableRow[]): boolean {
  return rows.length > 0 && rows.every((r) => rowComplete(columns, r))
}

/** Convierte objetos del contrato (p. ej. de un JSON subido) en filas editables de texto. */
export function objectsToRows(
  columns: CatalogColumn[],
  objs: Record<string, unknown>[],
): EditableRow[] {
  return objs.map((o) => {
    const row: EditableRow = {}
    for (const c of columns) {
      const v = o[c.name]
      row[c.name] = v == null ? '' : c.type === 'bool' ? (v ? 'true' : 'false') : String(v)
    }
    return row
  })
}

/** Coacciona un valor de texto al tipo declarado por la columna del contrato. */
function coerceValue(type: string, raw: string): string | number | boolean {
  switch (type) {
    case 'int':
      return Number.parseInt(raw, 10)
    case 'float':
      return Number(raw)
    case 'bool':
      return raw === 'true'
    default: // 'date' | 'str' y cualquier otro: texto tal cual
      return raw
  }
}

/**
 * Convierte filas editables en objetos tipados del contrato. Omite los campos opcionales
 * vacíos (degradan con elegancia); los obligatorios deben venir completos (gatear antes
 * con `rowsComplete`).
 */
export function coerceRows(columns: CatalogColumn[], rows: EditableRow[]): Record<string, unknown>[] {
  return rows.map((row) => {
    const obj: Record<string, unknown> = {}
    for (const col of columns) {
      const raw = (row[col.name] ?? '').trim()
      if (raw === '') continue // opcional vacío → se omite (usa el default del contrato)
      obj[col.name] = coerceValue(col.type, raw)
    }
    return obj
  })
}
