/**
 * Panel de validación de la carga (A8): qué se reconoció y qué se descartó al subir.
 */
import type { DatasetInfo } from '../../api/types'

const NUM = new Intl.NumberFormat('es-PE')

export function ValidacionCarga({ info }: { info: DatasetInfo }) {
  const { recognized_columns, missing_columns, rows_received, rows_discarded } = info
  const validas = rows_received - rows_discarded

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="text-emerald-700">
          ✓ {recognized_columns.length} columnas reconocidas
        </span>
        <span className="text-slate-600">
          {NUM.format(validas)} filas analizadas
          {rows_discarded > 0 && (
            <span className="text-amber-700">
              {' '}· {NUM.format(rows_discarded)} descartadas (vacías)
            </span>
          )}
        </span>
      </div>
      {missing_columns.length > 0 && (
        <p className="mt-1 text-amber-800">
          ⚠️ Faltan columnas: <span className="font-mono">{missing_columns.join(', ')}</span>
        </p>
      )}
      <details className="mt-1">
        <summary className="cursor-pointer text-xs text-slate-400">Ver columnas reconocidas</summary>
        <p className="mt-1 font-mono text-xs text-slate-500">{recognized_columns.join(', ')}</p>
      </details>
    </div>
  )
}
