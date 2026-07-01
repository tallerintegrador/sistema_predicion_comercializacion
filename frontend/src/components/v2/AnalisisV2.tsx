/**
 * Análisis **3×3 por dominio** (ADR-0024/0025). Una sola llamada a `/v2/{dominio}` entrena
 * en el momento los tres modelos —regresión, clasificación y clustering— sobre el formato
 * fijo del dominio y los muestra en tres bloques. En ALMACÉN añade los indicadores de
 * inventario derivados del pronóstico de demanda.
 *
 * El usuario puede correr la **demo** (datos sintéticos del propio sistema) o subir sus
 * datos en JSON con el formato fijo del dominio.
 */
import { useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { getV2Demo, postV2 } from '../../api/endpoints'
import type { AutoRow, V2Domain, V2Response } from '../../api/types'
import { SerieChart } from '../charts/SerieChart'
import { ModuleHeader } from '../ui/ModuleHeader'
import { StepSection } from '../ui/StepSection'
import { EmptyState } from '../ui/EmptyState'
import { ErrorPanel } from '../ErrorPanel'
import type { Accent, View } from '../../theme/modules'
import { fmtNum } from '../../utils/format'
import type { LucideIcon } from 'lucide-react'

const NUM = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 })

function Metricas({ metrics }: { metrics: Record<string, number> }) {
  const entradas = Object.entries(metrics)
  if (entradas.length === 0) return null
  return (
    <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
      {entradas.map(([k, v]) => (
        <span key={k}>
          <span className="font-medium text-slate-600">{k}</span>=<span className="font-mono">{NUM.format(v)}</span>
        </span>
      ))}
    </p>
  )
}

/** Tabla genérica sobre registros (muestra las primeras `limite` filas). */
function Tabla({ rows, columns, limite = 12 }: { rows: AutoRow[]; columns: string[]; limite?: number }) {
  const visibles = rows.slice(0, limite)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
            {columns.map((c) => (
              <th key={c} className="px-2 py-1 font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visibles.map((r, i) => (
            <tr key={i} className="border-b border-slate-100">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1 font-mono text-slate-700">
                  {typeof r[c] === 'number' ? NUM.format(r[c] as number) : String(r[c] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > limite && (
        <p className="mt-1 text-xs text-slate-400">… y {fmtNum(rows.length - limite)} filas más.</p>
      )}
    </div>
  )
}

export interface AnalisisV2Props {
  view: View
  dominio: V2Domain
  accent: Accent
  empty: { icon: LucideIcon; titulo: string; mensaje: string }
}

export function AnalisisV2({ view, dominio, accent, empty }: AnalisisV2Props) {
  const [data, setData] = useState<V2Response | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  const correr = async (fn: () => Promise<V2Response>) => {
    setBusy(true)
    setError(null)
    setAviso(null)
    setData(null)
    try {
      setData(await fn())
    } catch (e) {
      if (e instanceof ApiError) setError(e)
      else setAviso(String(e))
    } finally {
      setBusy(false)
    }
  }

  const onJson = async (file: File) => {
    setAviso(null)
    try {
      const parsed = JSON.parse(await file.text())
      const rows: AutoRow[] = Array.isArray(parsed) ? parsed : parsed?.rows
      if (!Array.isArray(rows) || rows.length === 0) {
        setAviso('El JSON debe ser un arreglo de filas (o un objeto con «rows») en el formato del dominio.')
        return
      }
      await correr(() => postV2(dominio, rows))
    } catch {
      setAviso('El archivo no es un JSON válido.')
    }
  }

  const Empty = empty.icon

  return (
    <div className="space-y-5">
      <ModuleHeader view={view} />

      <StepSection step={1} title="Ejecuta el análisis" accentChip={accent.chip} description="Corre la demo con datos sintéticos del sistema o sube tus datos en el formato del dominio (JSON).">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`btn ${accent.solid}`} onClick={() => void correr(() => getV2Demo(dominio))} disabled={busy}>
            {busy ? 'Entrenando y prediciendo…' : 'Ver demo'}
          </button>
          <label className="btn-ghost cursor-pointer">
            Subir JSON
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onJson(f)
                e.target.value = ''
              }}
            />
          </label>
        </div>
        <p className="help">Los tres modelos (regresión, clasificación, clustering) se entrenan en el momento sobre los datos enviados.</p>
        {aviso && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800" role="alert">{aviso}</p>
        )}
      </StepSection>

      {error && <ErrorPanel error={error} />}

      {!data && !busy && !error && (
        <EmptyState icon={Empty} title={empty.titulo} message={empty.mensaje} />
      )}

      {data && <Resultado data={data} accent={accent} />}
    </div>
  )
}

function Resultado({ data, accent }: { data: V2Response; accent: Accent }) {
  const { regresion, clasificacion, clustering } = data

  const forePoints = useMemo(() => {
    const byDate = new Map<string, number>()
    for (const r of regresion.prediccion) {
      const d = String(r.fecha)
      byDate.set(d, (byDate.get(d) ?? 0) + Number(r.prediccion || 0))
    }
    return [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, value]) => ({ date, value }))
  }, [regresion])

  const colsPred = regresion.prediccion[0] ? Object.keys(regresion.prediccion[0]) : []
  const colsAlert = clasificacion.alertas[0] ? Object.keys(clasificacion.alertas[0]) : []

  // Agrupa los segmentos por etiqueta narrativa (cuántas entidades en cada grupo).
  const grupos = useMemo(() => {
    const clave = clustering.entidad ?? Object.keys(clustering.segmentos[0] ?? {}).find((k) => k !== 'segmento' && k !== 'etiqueta') ?? 'entidad'
    const m = new Map<string, { etiqueta: string; ids: string[] }>()
    for (const s of clustering.segmentos) {
      const et = String(s.etiqueta)
      const g = m.get(et) ?? { etiqueta: et, ids: [] }
      g.ids.push(String(s[clave]))
      m.set(et, g)
    }
    return [...m.values()].sort((a, b) => b.ids.length - a.ids.length)
  }, [clustering])

  const alertasPositivas = clasificacion.alertas.filter((a) => Number(a.clase) === 1).length

  return (
    <div className="space-y-4">
      {/* BLOQUE 1 — REGRESIÓN */}
      <section className="card space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold text-slate-800">Pronóstico · {regresion.objetivo}</h3>
          <span className={`badge ${accent.badge}`}>modelo: {regresion.modelo_ganador}</span>
        </div>
        <Metricas metrics={regresion.metricas_honestas} />
        {forePoints.length > 0 && (
          <SerieChart history={[]} forecast={forePoints} histLabel="" foreLabel={`Pronóstico (${regresion.horizonte} períodos)`} hex={accent.hex} />
        )}
        {regresion.prediccion.length > 0 ? (
          <Tabla rows={regresion.prediccion} columns={colsPred} />
        ) : (
          <p className="text-sm text-slate-500">Sin pronóstico (el dominio no es temporal o faltó historia).</p>
        )}
      </section>

      {/* BLOQUE 2 — CLASIFICACIÓN */}
      <section className="card space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold text-slate-800">Alertas · {clasificacion.etiqueta}</h3>
          <span className={`badge ${accent.badge}`}>modelo: {clasificacion.modelo_ganador}</span>
        </div>
        <p className="text-sm text-slate-500">{clasificacion.definicion}</p>
        <p className="text-xs text-slate-500">
          umbral <span className="font-mono">{NUM.format(clasificacion.umbral)}</span> · prevalencia{' '}
          <span className="font-mono">{NUM.format(clasificacion.prevalencia)}</span> · {alertasPositivas} de {clasificacion.alertas.length} series en alerta
        </p>
        <Metricas metrics={clasificacion.metricas_honestas} />
        {clasificacion.alertas.length > 0 && <Tabla rows={clasificacion.alertas} columns={colsAlert} />}
      </section>

      {/* BLOQUE 3 — CLUSTERING */}
      <section className="card space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold text-slate-800">Segmentos · {clustering.entidad ?? 'entidad'}</h3>
          <span className={`badge ${accent.badge}`}>k={clustering.k}{clustering.silueta != null ? ` · silueta ${NUM.format(clustering.silueta)}` : ''}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {grupos.map((g) => (
            <div key={g.etiqueta} className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">
              <p className="text-sm font-semibold text-slate-700">{g.etiqueta}</p>
              <p className="text-xs text-slate-500">{g.ids.length} entidades</p>
              <p className="mt-1 max-w-xs truncate font-mono text-xs text-slate-400">{g.ids.join(', ')}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ALMACÉN — indicadores de inventario derivados */}
      {data.indicadores_inventario && data.indicadores_inventario.length > 0 && (
        <section className="card space-y-3">
          <h3 className="text-base font-semibold text-slate-800">Indicadores de inventario</h3>
          <p className="text-sm text-slate-500">Cobertura, punto de reposición y stock de seguridad derivados del pronóstico de demanda.</p>
          <Tabla rows={data.indicadores_inventario as unknown as AutoRow[]} columns={Object.keys(data.indicadores_inventario[0])} />
        </section>
      )}

      <p className="text-xs text-slate-400">{data.nota}</p>
    </div>
  )
}
