/**
 * Etiquetas legibles por columna — fuente única en el BACKEND (catálogo YAML).
 *
 * El frontend ya no mantiene su propio diccionario duplicado (auditoría 2026-07-03): al
 * cargar el catálogo (`GET /v3/catalogo`) se llama `setColumnLabels(column_labels)` y los
 * renderidores usan `humaniza(col)`. Fallback: reemplazar guiones bajos por espacios.
 */

let COLUMN_LABELS: Record<string, string> = {}

/** Guarda las etiquetas servidas por el backend (idempotente). */
export function setColumnLabels(labels?: Record<string, string>): void {
  if (labels && Object.keys(labels).length > 0) {
    COLUMN_LABELS = labels
  }
}

/** Nombre legible de una columna; si no hay etiqueta, formatea el identificador. */
export function humaniza(col: string): string {
  return COLUMN_LABELS[col] ?? col.replace(/_/g, ' ')
}
