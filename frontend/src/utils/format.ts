/** Formateo numérico/fecha para la UI (es). */
const num = new Intl.NumberFormat('es', { maximumFractionDigits: 1 })
const ent = new Intl.NumberFormat('es', { maximumFractionDigits: 0 })

export const fmtNum = (n: number | null | undefined): string =>
  n == null ? '—' : num.format(n)

/** Entero (sin decimales): para cantidades de stock/reposición. */
export const fmtInt = (n: number | null | undefined): string =>
  n == null ? '—' : ent.format(n)

export const fmtPct = (n: number | null | undefined): string =>
  n == null ? '—' : `${(n * 100).toFixed(1)}%`

/** Acorta una fecha ISO a YYYY-MM-DD (la API ya la entrega así). */
export const fmtDate = (iso: string): string => iso.slice(0, 10)
