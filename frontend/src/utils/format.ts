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

const miles = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0 })
const soles = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const idx = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 })

/**
 * Formatea un valor según la unidad de la consulta (leída del backend):
 * unidades (entero + separador de miles), S/ (soles con miles), días, % (cumplimiento 0..1),
 * índice. Sin unidad → número simple.
 */
export function fmtValor(valor: number | null | undefined, unidad?: string): string {
  if (valor == null || Number.isNaN(valor)) return '—'
  switch (unidad) {
    case 'S/':
      return `S/ ${soles.format(valor)}`
    case 'unidades':
      return `${miles.format(Math.round(valor))} unidades`
    case 'días':
      return `${idx.format(valor)} días`
    case '%':
      return `${(valor <= 1.5 ? valor * 100 : valor).toFixed(1)}%`
    case 'índice':
      return idx.format(valor)
    default:
      return idx.format(valor)
  }
}
