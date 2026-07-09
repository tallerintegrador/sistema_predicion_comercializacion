/**
 * Historial de análisis por categoría (ventas/compras/almacen).
 *
 * Lista los análisis que el cliente ha ejecutado antes (persistidos en la tabla
 * ``predictions``) y permite abrir uno para re-ver sus valores predichos sin re-ejecutar
 * el modelo. Se refresca cada vez que el módulo cambia o tras un nuevo análisis (`refrescar`).
 */
import { Fragment, useCallback, useEffect, useState } from 'react'
import { getV3Historial, getV3Prediccion } from '../../api/endpoints'
import type { HistorialDetalle, HistorialItem, V3Domain } from '../../api/types'

interface HistorialV3Props {
  modulo: V3Domain
  /** Cambia este valor (p. ej. la fecha del último análisis) para forzar recarga. */
  refrescar?: unknown
}

function formatearFecha(iso: string): string {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('es-PE')
}

export function HistorialV3({ modulo, refrescar }: HistorialV3Props) {
  const [items, setItems] = useState<HistorialItem[]>([])
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detalle, setDetalle] = useState<HistorialDetalle | null>(null)
  const [abierto, setAbierto] = useState<number | null>(null)

  const cargar = useCallback(() => {
    setCargando(true)
    setError(null)
    getV3Historial(modulo)
      .then((r) => setItems(r.items))
      .catch(() => setError('No se pudo cargar el historial.'))
      .finally(() => setCargando(false))
  }, [modulo])

  useEffect(() => {
    cargar()
    setDetalle(null)
    setAbierto(null)
  }, [cargar, refrescar])

  const abrir = (id: number) => {
    if (abierto === id) {
      setAbierto(null)
      setDetalle(null)
      return
    }
    setAbierto(id)
    setDetalle(null)
    getV3Prediccion(id)
      .then(setDetalle)
      .catch(() => setError('No se pudo cargar el detalle.'))
  }

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>
      )}

      {cargando && items.length === 0 ? (
        <p className="text-sm text-slate-500">Cargando historial…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">
          Aún no hay análisis guardados para esta categoría. Sube tus datos en el Paso 3 y aparecerán aquí.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                <th className="px-3 py-2 font-medium">Fecha</th>
                <th className="px-3 py-2 font-medium">Filas</th>
                <th className="px-3 py-2 font-medium">Análisis</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <Fragment key={it.id}>
                  <tr className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-2 text-slate-700">{formatearFecha(it.created_at)}</td>
                    <td className="px-3 py-2 text-slate-600">{it.rows}</td>
                    <td className="px-3 py-2 text-slate-600">{it.reports} reportes</td>
                    <td className="px-3 py-2">
                      <button className="btn-ghost text-xs" onClick={() => abrir(it.id)}>
                        {abierto === it.id ? 'Ocultar' : 'Ver resultados'}
                      </button>
                    </td>
                  </tr>
                  {abierto === it.id && (
                    <tr className="border-b border-slate-100">
                      <td colSpan={4} className="bg-slate-50 px-3 py-3">
                        <DetallePrediccion detalle={detalle} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/** Muestra los valores predichos guardados de un análisis (una tabla por reporte). */
function DetallePrediccion({ detalle }: { detalle: HistorialDetalle | null }) {
  if (detalle === null) return <p className="text-sm text-slate-500">Cargando resultados…</p>
  const reports = detalle.response?.reports ?? []
  if (reports.length === 0) return <p className="text-sm text-slate-500">Este análisis no guardó valores.</p>

  return (
    <div className="space-y-4">
      {reports.map((r) => (
        <div key={r.query_id}>
          <p className="text-sm font-medium text-slate-700">{r.question}</p>
          <p className="mb-1 text-xs text-slate-400">
            {r.type} · {r.winner_model ?? '—'} · {r.n_predictions} predicciones
            {r.unit ? ` · ${r.unit}` : ''}
          </p>
          {r.predictions.length > 0 ? (
            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 uppercase tracking-wide text-slate-400">
                    {Object.keys(r.predictions[0]).map((c) => (
                      <th key={c} className="whitespace-nowrap px-2 py-1 font-medium">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.predictions.slice(0, 20).map((fila, i) => (
                    <tr key={i} className="border-b border-slate-100 last:border-0">
                      {Object.keys(r.predictions[0]).map((c) => (
                        <td key={c} className="whitespace-nowrap px-2 py-1 text-slate-600">
                          {String(fila[c] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {r.predictions.length > 20 && (
                <p className="px-2 py-1 text-xs text-slate-400">
                  Mostrando 20 de {r.predictions.length} filas guardadas.
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400">Sin filas de predicción.</p>
          )}
        </div>
      ))}
    </div>
  )
}
