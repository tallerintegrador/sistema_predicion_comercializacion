/**
 * Vista principal del análisis v3: 3 pasos guiados + 10 reportes automáticos + tendencia.
 *
 * Flujo:
 * 1. ¿Qué datos necesito? → tabla de columnas + listado de 10 consultas
 * 2. Descarga formato → plantilla Excel o JSON (ambas ya traen filas de ejemplo)
 * 3. Analiza tus datos → sube tu plantilla llena (Excel o JSON)
 */
import { useEffect, useState } from 'react'
import { ApiError, postFile } from '../../api/client'
import {
  getV3Plantilla,
  getV3PlantillaJson,
  getV3Catalogo,
} from '../../api/endpoints'
import type { AutoRow, ModuleResponse, QueryInfo, V3Domain } from '../../api/types'
import { ModuleHeader } from '../ui/ModuleHeader'
import { StepSection } from '../ui/StepSection'
import { EmptyState } from '../ui/EmptyState'
import { ErrorPanel } from '../ErrorPanel'
import { SeccionReportes } from './SeccionReportes'
import { BloqueTendencia } from './BloqueTendencia'
import { ValidacionCarga } from './ValidacionCarga'
import { HistorialV3 } from './HistorialV3'
import { TIPOS_REPORTE, ORDEN_TIPO, INFO_POR_TIPO } from '../../data/tiposReporte'
import { setColumnLabels } from '../../data/etiquetas'
import type { Accent, View } from '../../theme/modules'
import type { LucideIcon } from 'lucide-react'

interface VistaV3ModuloProps {
  view: View
  modulo: V3Domain
  accent: Accent
  empty: { icon: LucideIcon; titulo: string; mensaje: string }
}

function descargarArchivo(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function VistaV3Modulo({
  view,
  modulo,
  accent,
  empty,
}: VistaV3ModuloProps) {
  const [catalogo, setCatalogo] = useState<QueryInfo[]>([])
  const [muestra, setMuestra] = useState<AutoRow[]>([])
  const [data, setData] = useState<ModuleResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  // Carga catálogo y una muestra de la plantilla (A9) al montar
  useEffect(() => {
    let vivo = true
    getV3Catalogo()
      .then((c) => {
        if (!vivo) return
        setColumnLabels(c.column_labels) // etiquetas legibles desde el catálogo (fuente única)
        setCatalogo(c.queries.filter((x) => x.module === modulo))
      })
      .catch(() => vivo && setCatalogo([]))
    getV3PlantillaJson(modulo)
      .then(({ blob }) => blob.text())
      .then((t) => {
        const j = JSON.parse(t)
        const rows: AutoRow[] = Array.isArray(j) ? j : (j.rows ?? [])
        if (vivo) setMuestra(rows.slice(0, 3))
      })
      .catch(() => vivo && setMuestra([]))
    return () => {
      vivo = false
    }
  }, [modulo])

  const onArchivo = async (file: File) => {
    setAviso(null)
    setBusy(true)
    setError(null)
    setData(null)

    const nombre = file.name.toLowerCase()
    try {
      if (nombre.endsWith('.xlsx') || nombre.endsWith('.json')) {
        // Usar endpoint /archivo que procesa Excel/JSON
        const result = await postFile<ModuleResponse>(`/v3/${modulo}/archivo`, file)
        setData(result.data)
        return
      }
      setAviso('Sube un archivo .xlsx (Excel) o .json.')
    } catch (e) {
      if (e instanceof ApiError) setError(e)
      else setAviso(String(e))
    } finally {
      setBusy(false)
    }
  }

  const descargarPlantilla = async () => {
    setAviso(null)
    try {
      const { blob, filename } = await getV3Plantilla(modulo)
      descargarArchivo(blob, filename)
    } catch {
      setAviso('No se pudo descargar la plantilla Excel.')
    }
  }

  const descargarPlantillaJson = async () => {
    setAviso(null)
    try {
      const { blob, filename } = await getV3PlantillaJson(modulo)
      descargarArchivo(blob, filename)
    } catch {
      setAviso('No se pudo descargar la plantilla JSON.')
    }
  }

  const Empty = empty.icon

  // A1: listado del Paso 1 ordenado como los resultados (Predicción → Alerta → Segmento)
  const catalogoOrdenado = [...catalogo].sort((a, b) => ORDEN_TIPO[a.type] - ORDEN_TIPO[b.type])

  return (
    <div className="space-y-5">
      <ModuleHeader view={view} />

      {/* PASO 1 — ¿Qué análisis obtendrás? */}
      <StepSection
        step={1}
        title="¿Qué análisis obtendrás?"
        accentChip={accent.chip}
        description="El sistema ejecuta 10 análisis automáticos por ti. Estos son y qué responden."
      >
        <div className="space-y-4">
          {/* Explicación de los 3 tipos (misma fuente que los resultados) */}
          <div className="grid gap-2 sm:grid-cols-3">
            {TIPOS_REPORTE.map((t) => (
              <div key={t.type} className="rounded-lg border border-slate-200 bg-slate-50/60 p-2.5">
                <p className="text-sm font-semibold text-slate-800">{t.icono} {t.chip}</p>
                <p className="mt-0.5 text-xs text-slate-500">{t.explicacion}</p>
              </div>
            ))}
          </div>

          {/* Listado de consultas (ordenado como los resultados) */}
          <div>
            <p className="text-sm font-medium text-slate-700 mb-2">
              10 análisis que se ejecutarán automáticamente:
            </p>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                    <th className="px-3 py-2 font-medium">Tipo</th>
                    <th className="px-3 py-2 font-medium">Pregunta</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogoOrdenado.length > 0 ? (
                    catalogoOrdenado.map((q) => (
                      <tr key={q.id} className="border-b border-slate-100 last:border-0">
                        <td className="px-3 py-2">
                          <span className="inline-block rounded-full px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: `${accent.hex}20`, color: accent.hex }}>
                            {INFO_POR_TIPO[q.type].chip}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-700">{q.question}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-2 text-slate-400" colSpan={2}>
                        Cargando catálogo…
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-sm text-slate-500 italic">
            Todos estos análisis se entrenan automáticamente cuando subes tus datos (sin que tengas que elegir nada).
          </p>
        </div>
      </StepSection>

      {/* PASO 2 — Descarga el formato (Excel o JSON, con ejemplos incluidos) */}
      <StepSection
        step={2}
        title="Descarga el formato"
        accentChip={accent.chip}
        description="Baja una plantilla para llenar con tus datos. Ya viene con filas de ejemplo: reemplázalas por las tuyas y súbela en el Paso 3."
      >
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-ghost" onClick={() => void descargarPlantilla()}>
            Descargar plantilla (Excel)
          </button>
          <button type="button" className="btn-ghost" onClick={() => void descargarPlantillaJson()}>
            Descargar plantilla (JSON)
          </button>
        </div>
        <p className="help mt-2">
          Ambas plantillas traen todas las columnas necesarias y filas de ejemplo listas para reemplazar.
        </p>

        {/* A9: mini-tabla de muestra para no descargar "a ciegas" */}
        {muestra.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-medium text-slate-500">Así se ven las columnas (ejemplo):</p>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 uppercase tracking-wide text-slate-400">
                    {Object.keys(muestra[0]).map((c) => (
                      <th key={c} className="whitespace-nowrap px-2.5 py-1.5 font-medium">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {muestra.map((fila, i) => (
                    <tr key={i} className="border-b border-slate-100 last:border-0">
                      {Object.keys(muestra[0]).map((c) => (
                        <td key={c} className="whitespace-nowrap px-2.5 py-1.5 text-slate-600">
                          {String(fila[c] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </StepSection>

      {/* PASO 3 — Analiza tus datos */}
      <StepSection
        step={3}
        title="Analiza tus datos"
        accentChip={accent.chip}
        description="Sube tu plantilla (Excel o JSON) y automáticamente verás los 10 análisis."
      >
        <div className="flex flex-wrap items-center gap-3">
          <label className={`btn ${accent.solid} cursor-pointer`}>
            {busy ? 'Analizando (~5 segundos)…' : 'Subir mi plantilla (Excel o JSON)'}
            <input
              type="file"
              accept=".xlsx,.json,application/json"
              className="hidden"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onArchivo(f)
                e.target.value = ''
              }}
            />
          </label>
        </div>
        {aviso && (
          <p
            className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"
            role="alert"
          >
            {aviso}
          </p>
        )}
      </StepSection>

      {/* PASO 4 — Historial de análisis por categoría */}
      <StepSection
        step={4}
        title="Historial de análisis"
        accentChip={accent.chip}
        description="Revisa los análisis que hiciste antes en esta categoría y vuelve a ver sus resultados."
      >
        <HistorialV3 modulo={modulo} refrescar={data?.executed_at} />
      </StepSection>

      {error && <ErrorPanel error={error} />}

      {!data && !busy && !error && (
        <EmptyState icon={Empty} title={empty.titulo} message={empty.mensaje} />
      )}

      {/* Skeleton de carga */}
      {busy && (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-6">
          <div className="h-4 w-1/3 animate-pulse rounded bg-slate-200" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-slate-200" />
          <p className="text-sm text-slate-500 mt-4">Analizando tus datos (~5 segundos)…</p>
        </div>
      )}

      {/* Resultados: 3 secciones + tendencia */}
      {data && (
        <div className="space-y-8">
          {/* A8: retroalimentación de la carga */}
          {data.dataset_info && <ValidacionCarga info={data.dataset_info} />}

          {/* A7: leyenda de vocabulario (puente vista ↔ términos técnicos) */}
          <p className="text-xs text-slate-500">
            <span className="font-medium">Cómo leer esto:</span>{' '}
            <b>Predicción</b> = regresión (un número) · <b>Alerta</b> = clasificación (sí/no o categoría) ·{' '}
            <b>Segmento</b> = agrupación (clustering). El detalle técnico está en «Ver detalle técnico».
          </p>

          {/* Secciones de resultados: mismo orden y fuente que el Paso 1 (A1) */}
          {TIPOS_REPORTE.map((t) => {
            const reps = data.reports.filter((r) => r.type === t.type)
            return reps.length > 0 ? (
              <SeccionReportes
                key={t.type}
                titulo={t.titulo}
                icono={t.icono}
                descripcion={t.descripcion}
                reportes={reps}
                accentHex={accent.hex}
              />
            ) : null
          })}

          {/* SECCIÓN D: Análisis/Tendencia */}
          {data.trend_analysis && (
            <BloqueTendencia
              bloque={data.trend_analysis}
              accentHex={accent.hex}
            />
          )}

          {/* Fecha de ejecución */}
          <div className="text-xs text-slate-400 text-center pt-4 border-t border-slate-200">
            Análisis realizado el {new Date(data.executed_at).toLocaleString('es-PE')}
          </div>
        </div>
      )}
    </div>
  )
}
