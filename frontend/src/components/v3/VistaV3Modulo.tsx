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
import type { RespuestaModulo, ConsultaInfo, V3Domain } from '../../api/types'
import { ModuleHeader } from '../ui/ModuleHeader'
import { StepSection } from '../ui/StepSection'
import { EmptyState } from '../ui/EmptyState'
import { ErrorPanel } from '../ErrorPanel'
import { SeccionReportes } from './SeccionReportes'
import { BloqueTendencia } from './BloqueTendencia'
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
  const [catalogo, setCatalogo] = useState<ConsultaInfo[]>([])
  const [data, setData] = useState<RespuestaModulo | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  // Carga catálogo al montar
  useEffect(() => {
    let vivo = true
    getV3Catalogo()
      .then((c) => vivo && setCatalogo(c.consultas.filter((x) => x.modulo === modulo)))
      .catch(() => vivo && setCatalogo([]))
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
        const result = await postFile<RespuestaModulo>(`/v3/${modulo}/archivo`, file)
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

  // Filtrar reportes por tipo
  const reportesRegresion = data?.reportes.filter((r) => r.tipo === 'regresion') ?? []
  const reportesClasificacion = data?.reportes.filter((r) => r.tipo === 'clasificacion') ?? []
  const reportesClustering = data?.reportes.filter((r) => r.tipo === 'clustering') ?? []

  return (
    <div className="space-y-5">
      <ModuleHeader view={view} />

      {/* PASO 1 — ¿Qué datos necesito? */}
      <StepSection
        step={1}
        title="¿Qué datos necesito?"
        accentChip={accent.chip}
        description="Estas columnas son las que debes traer. El sistema te predecirá automáticamente con 10 análisis."
      >
        <div className="space-y-4">
          {/* Listado de consultas */}
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
                  {catalogo.length > 0 ? (
                    catalogo.map((q) => (
                      <tr key={q.consulta_id} className="border-b border-slate-100 last:border-0">
                        <td className="px-3 py-2">
                          <span className="inline-block rounded-full px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: `${accent.hex}20`, color: accent.hex }}>
                            {q.tipo === 'regresion'
                              ? 'Predicción'
                              : q.tipo === 'clasificacion'
                                ? 'Alerta'
                                : 'Segmento'}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-700">{q.pregunta}</td>
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
          {/* SECCIÓN A: Predicciones (regresión) */}
          {reportesRegresion.length > 0 && (
            <SeccionReportes
              titulo="Predicciones"
              icono="📊"
              descripcion="Números: qué esperar según los factores de tu negocio"
              reportes={reportesRegresion}
              accentHex={accent.hex}
            />
          )}

          {/* SECCIÓN B: Alertas (clasificación) */}
          {reportesClasificacion.length > 0 && (
            <SeccionReportes
              titulo="Alertas"
              icono="🔔"
              descripcion="Sí/No: qué requiere tu atención"
              reportes={reportesClasificacion}
              accentHex={accent.hex}
            />
          )}

          {/* SECCIÓN C: Grupos (clustering) */}
          {reportesClustering.length > 0 && (
            <SeccionReportes
              titulo="Grupos"
              icono="🧩"
              descripcion="Segmentación: cómo agrupar tus datos para mejor gestión"
              reportes={reportesClustering}
              accentHex={accent.hex}
            />
          )}

          {/* SECCIÓN D: Análisis/Tendencia */}
          {data.analisis_tendencia && (
            <BloqueTendencia
              bloque={data.analisis_tendencia}
              accentHex={accent.hex}
            />
          )}

          {/* Fecha de ejecución */}
          <div className="text-xs text-slate-400 text-center pt-4 border-t border-slate-200">
            Análisis realizado el {new Date(data.fecha_ejecución).toLocaleString('es-PE')}
          </div>
        </div>
      )}
    </div>
  )
}
