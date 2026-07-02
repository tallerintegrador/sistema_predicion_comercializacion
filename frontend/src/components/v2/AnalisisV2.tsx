/**
 * Análisis **3×3 por dominio** (ADR-0024/0025) en lenguaje simple.
 *
 * Guía a una PYME en 3 pasos: (1) qué datos necesita y qué se le va a predecir,
 * (2) descargar la plantilla / un ejemplo con datos, (3) elegir cuántos días predecir y
 * analizar (ver ejemplo o subir su archivo Excel o JSON). Los resultados se muestran sin
 * tecnicismos, con buscador y "mostrar más" para no abrumar; el detalle técnico (modelo,
 * métricas, umbral, silueta) queda en un panel plegable.
 *
 * Las tres páginas (Ventas/Compras/Almacén) usan este mismo componente.
 */
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../../api/client'
import {
  downloadV2Plantilla,
  getV2Demo,
  getV2Esquema,
  getV2PlantillaJson,
  postV2,
  postV2Excel,
} from '../../api/endpoints'
import type { AutoRow, V2Domain, V2Esquema, V2PrediccionItem, V2Response } from '../../api/types'
import { SerieChart } from '../charts/SerieChart'
import { BarrasTop } from '../charts/BarrasTop'
import { ModuleHeader } from '../ui/ModuleHeader'
import { StepSection } from '../ui/StepSection'
import { EmptyState } from '../ui/EmptyState'
import { ErrorPanel } from '../ErrorPanel'
import type { Accent, View } from '../../theme/modules'
import type { LucideIcon } from 'lucide-react'

const NUM = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 })
const HORIZONTES = [7, 14, 30]

// Nombres de columna → etiqueta amigable.
const ETIQUETA: Record<string, string> = {
  id_tienda: 'Tienda',
  id_proveedor: 'Proveedor',
  sku: 'Producto',
  categoria: 'Categoría',
  fecha: 'Fecha',
  fecha_orden: 'Fecha de orden',
  prediccion: 'Predicción',
  unidades_vendidas: 'Unidades vendidas',
  cantidad_pedida: 'Cantidad a pedir',
  demanda_dia: 'Demanda del día',
}
const label = (c: string) => ETIQUETA[c] ?? c.replace(/_/g, ' ')

const TITULO_PRONOSTICO: Record<string, string> = {
  unidades_vendidas: 'Cuánto vas a vender',
  cantidad_pedida: 'Cuánto conviene pedir',
  demanda_dia: 'Cuánta demanda vas a tener',
}
const TITULO_ALERTA: Record<string, string> = {
  demanda_alta: 'Productos con demanda alta',
  entrega_con_retraso: 'Órdenes con riesgo de llegar tarde',
  riesgo_quiebre: 'Productos con riesgo de quedarse sin stock',
}

function DetalleTecnico({ children }: { children: ReactNode }) {
  return (
    <details className="mt-1 text-xs text-slate-500">
      <summary className="cursor-pointer select-none text-slate-400 hover:text-slate-600">Ver detalle técnico</summary>
      <div className="mt-2 space-y-1">{children}</div>
    </details>
  )
}

function Metricas({ metrics }: { metrics: Record<string, number> }) {
  const entradas = Object.entries(metrics)
  if (entradas.length === 0) return null
  return (
    <p className="flex flex-wrap gap-x-3 gap-y-1">
      {entradas.map(([k, v]) => (
        <span key={k}>
          <span className="font-medium">{k}</span>=<span className="font-mono">{NUM.format(v)}</span>
        </span>
      ))}
    </p>
  )
}

/** Tabla con **buscador** y **mostrar más** (cabeceras ya amigables). */
function TablaInteractiva({
  rows,
  columns,
  buscarPlaceholder = 'Buscar…',
  inicial = 8,
}: {
  rows: AutoRow[]
  columns: string[]
  buscarPlaceholder?: string
  inicial?: number
}) {
  const [q, setQ] = useState('')
  const [limite, setLimite] = useState(inicial)

  const filtradas = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return rows
    return rows.filter((r) => columns.some((c) => String(r[c] ?? '').toLowerCase().includes(t)))
  }, [rows, columns, q])
  const visibles = filtradas.slice(0, limite)

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setLimite(inicial)
          }}
          placeholder={buscarPlaceholder}
          className="w-full max-w-xs rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:border-slate-400 focus:outline-none"
        />
        <span className="text-xs text-slate-400">
          {filtradas.length === rows.length ? `${rows.length} filas` : `${filtradas.length} de ${rows.length}`}
        </span>
      </div>
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
                  <td key={c} className="px-2 py-1 text-slate-700">
                    {typeof r[c] === 'number' ? NUM.format(r[c] as number) : String(r[c] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
            {visibles.length === 0 && (
              <tr>
                <td className="px-2 py-3 text-sm text-slate-400" colSpan={columns.length}>Sin resultados para «{q}».</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {filtradas.length > limite && (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost text-xs" onClick={() => setLimite((l) => l + 20)}>
            Mostrar más
          </button>
          <button type="button" className="btn-ghost text-xs" onClick={() => setLimite(filtradas.length)}>
            Mostrar todo ({filtradas.length})
          </button>
        </div>
      )}
    </div>
  )
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

export interface AnalisisV2Props {
  view: View
  dominio: V2Domain
  accent: Accent
  empty: { icon: LucideIcon; titulo: string; mensaje: string }
}

export function AnalisisV2({ view, dominio, accent, empty }: AnalisisV2Props) {
  const [esquema, setEsquema] = useState<V2Esquema | null>(null)
  const [data, setData] = useState<V2Response | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [horizon, setHorizon] = useState(14)

  useEffect(() => {
    let vivo = true
    getV2Esquema(dominio)
      .then((e) => vivo && setEsquema(e))
      .catch(() => vivo && setEsquema(null))
    return () => {
      vivo = false
    }
  }, [dominio])

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

  const onArchivo = async (file: File) => {
    setAviso(null)
    const nombre = file.name.toLowerCase()
    if (nombre.endsWith('.xlsx')) {
      await correr(() => postV2Excel(dominio, file, horizon))
      return
    }
    if (nombre.endsWith('.json')) {
      try {
        const parsed = JSON.parse(await file.text())
        const rows: AutoRow[] = Array.isArray(parsed) ? parsed : parsed?.rows
        if (!Array.isArray(rows) || rows.length === 0) {
          setAviso('El JSON debe ser un arreglo de filas (o un objeto con «rows») en el formato del dominio.')
          return
        }
        await correr(() => postV2(dominio, rows, horizon))
      } catch {
        setAviso('El archivo no es un JSON válido.')
      }
      return
    }
    setAviso('Sube un archivo .xlsx (Excel) o .json.')
  }

  const descargar = async (contenido: 'basica' | 'rica', formato: 'excel' | 'json') => {
    setAviso(null)
    try {
      if (formato === 'excel') {
        const { blob, filename } = await downloadV2Plantilla(dominio, contenido)
        descargarArchivo(blob, filename)
      } else {
        const cuerpo = await getV2PlantillaJson(dominio, contenido)
        const blob = new Blob([JSON.stringify(cuerpo, null, 2)], { type: 'application/json' })
        descargarArchivo(blob, `${contenido === 'rica' ? 'ejemplo' : 'plantilla'}_${dominio}.json`)
      }
    } catch {
      setAviso('No se pudo descargar el archivo.')
    }
  }

  const Empty = empty.icon

  return (
    <div className="space-y-5">
      <ModuleHeader view={view} />

      {/* PASO 1 — ¿Qué datos necesito? */}
      <StepSection step={1} title="¿Qué datos necesito?" accentChip={accent.chip} description="Estas son las columnas que debes traer y lo que el sistema te va a predecir.">
        {esquema ? (
          <div className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-3">
              <Prediccion titulo="Pronóstico" texto={esquema.que_se_predice.regresion.explicacion} />
              <Prediccion titulo="Alerta" texto={esquema.que_se_predice.clasificacion.explicacion} />
              <Prediccion titulo="Grupos" texto={esquema.que_se_predice.clustering.explicacion} />
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                    <th className="px-3 py-2 font-medium">Columna</th>
                    <th className="px-3 py-2 font-medium">Qué es</th>
                    <th className="px-3 py-2 font-medium">Ejemplo</th>
                  </tr>
                </thead>
                <tbody>
                  {esquema.columnas.map((c) => (
                    <tr key={c.nombre} className="border-b border-slate-100 last:border-0">
                      <td className="px-3 py-2">
                        <span className="font-medium text-slate-700">{label(c.nombre)}</span>{' '}
                        <span className="font-mono text-xs text-slate-400">{c.nombre}</span>
                        {c.se_calcula_sola && (
                          <span className="ml-1 rounded bg-slate-100 px-1 text-[10px] text-slate-500">se calcula sola</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{c.descripcion}</td>
                      <td className="px-3 py-2 font-mono text-xs text-slate-500">{String(c.ejemplo ?? '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="help">Cargando el detalle de las columnas…</p>
        )}
      </StepSection>

      {/* PASO 2 — Descarga el formato */}
      <StepSection step={2} title="Descarga el formato" accentChip={accent.chip} description="Baja una plantilla vacía para llenar con tus datos, o un ejemplo ya lleno para probar.">
        <div className="flex flex-wrap gap-3">
          <button type="button" className="btn-ghost" onClick={() => void descargar('basica', 'excel')}>
            Plantilla (Excel)
          </button>
          <button type="button" className="btn-ghost" onClick={() => void descargar('rica', 'excel')}>
            Ejemplo con datos (Excel)
          </button>
          <button type="button" className="btn-ghost" onClick={() => void descargar('rica', 'json')}>
            Ejemplo (JSON)
          </button>
        </div>
        <p className="help">La plantilla trae una hoja de instrucciones. El ejemplo con datos se puede subir tal cual en el paso 3.</p>
      </StepSection>

      {/* PASO 3 — Analiza */}
      <StepSection step={3} title="Analiza tus datos" accentChip={accent.chip} description="Elige cuántos días predecir y sube tu archivo (Excel o JSON), o mira un ejemplo.">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-600">¿Cuántos días predecir?</span>
          {HORIZONTES.map((h) => (
            <button
              key={h}
              type="button"
              disabled={busy}
              onClick={() => setHorizon(h)}
              className={`rounded-full px-3 py-1 text-sm transition ${
                horizon === h ? `${accent.solid} text-white` : 'border border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              {h} días
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className={`btn ${accent.solid} cursor-pointer`}>
            {busy ? 'Entrenando y prediciendo…' : 'Subir mi archivo (Excel o JSON)'}
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
          <button type="button" className="btn-ghost" onClick={() => void correr(() => getV2Demo(dominio, horizon))} disabled={busy}>
            Ver ejemplo
          </button>
        </div>
        <p className="help">Al analizar, el sistema aprende con tus datos en el momento (puede tardar unos segundos). A más días, tarda un poco más y el pronóstico es menos preciso.</p>
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

function Prediccion({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">
      <p className="text-sm font-semibold text-slate-700">{titulo}</p>
      <p className="mt-0.5 text-xs text-slate-500">{texto}</p>
    </div>
  )
}

/** Resumen del pronóstico POR ENTIDAD (total y promedio en el horizonte) en vez del
 *  detalle diario, que puede ser de miles de filas. */
function resumenPorSerie(pred: V2PrediccionItem[]): AutoRow[] {
  if (pred.length === 0) return []
  const claves = Object.keys(pred[0]).filter((k) => k !== 'fecha' && k !== 'prediccion')
  const m = new Map<string, { serie: Record<string, string | number>; total: number; n: number }>()
  for (const r of pred) {
    const id = claves.map((k) => String(r[k])).join(' · ')
    const e = m.get(id) ?? { serie: Object.fromEntries(claves.map((k) => [k, r[k]])), total: 0, n: 0 }
    e.total += Number(r.prediccion || 0)
    e.n += 1
    m.set(id, e)
  }
  return [...m.values()]
    .map((e) => ({
      ...Object.fromEntries(Object.entries(e.serie).map(([k, v]) => [label(k), v])),
      'Total previsto': Math.round(e.total),
      'Promedio/día': Math.round((e.total / Math.max(1, e.n)) * 10) / 10,
    }))
    .sort((a, b) => Number(b['Total previsto']) - Number(a['Total previsto']))
}

function GrupoCard({ etiqueta, ids, unidad }: { etiqueta: string; ids: string[]; unidad: string }) {
  const [abierto, setAbierto] = useState(false)
  const muestra = abierto ? ids : ids.slice(0, 8)
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">
      <p className="text-sm font-semibold text-slate-700">{etiqueta}</p>
      <p className="text-xs text-slate-500">{ids.length} {unidad}</p>
      <p className="mt-1 font-mono text-xs text-slate-400">{muestra.join(', ')}</p>
      {ids.length > 8 && (
        <button type="button" className="mt-1 text-xs text-slate-500 hover:text-slate-700" onClick={() => setAbierto((v) => !v)}>
          {abierto ? 'ver menos' : `ver los ${ids.length} ${unidad}`}
        </button>
      )}
    </div>
  )
}

function Resultado({ data, accent }: { data: V2Response; accent: Accent }) {
  const { regresion, clasificacion, clustering } = data
  const [soloAlerta, setSoloAlerta] = useState(true)
  const [soloReponer, setSoloReponer] = useState(true)
  const [ejeGrafico, setEjeGrafico] = useState<'total' | 'producto' | 'tienda'>('total')
  const [seleccion, setSeleccion] = useState('')

  // Clave de "tienda" según el dominio (ventas/almacén: id_tienda; compras: id_proveedor).
  const claveTienda =
    regresion.prediccion[0] && 'id_tienda' in regresion.prediccion[0]
      ? 'id_tienda'
      : regresion.prediccion[0] && 'id_proveedor' in regresion.prediccion[0]
        ? 'id_proveedor'
        : null
  const etiquetaTienda = claveTienda === 'id_proveedor' ? 'proveedor' : 'tienda'
  const modos: ('total' | 'producto' | 'tienda')[] = claveTienda
    ? ['total', 'producto', 'tienda']
    : ['total', 'producto']

  const productos = useMemo(
    () => [...new Set(regresion.prediccion.map((r) => String(r.sku)))].sort(),
    [regresion],
  )
  const tiendas = useMemo(
    () => (claveTienda ? [...new Set(regresion.prediccion.map((r) => String(r[claveTienda])))].sort() : []),
    [regresion, claveTienda],
  )

  const cambiarEje = (modo: 'total' | 'producto' | 'tienda') => {
    setEjeGrafico(modo)
    if (modo === 'producto') setSeleccion(productos[0] ?? '')
    else if (modo === 'tienda') setSeleccion(tiendas[0] ?? '')
    else setSeleccion('')
  }

  const forePoints = useMemo(() => {
    let items = regresion.prediccion
    if (ejeGrafico === 'producto' && seleccion) items = items.filter((r) => String(r.sku) === seleccion)
    else if (ejeGrafico === 'tienda' && seleccion && claveTienda) items = items.filter((r) => String(r[claveTienda]) === seleccion)
    const byDate = new Map<string, number>()
    for (const r of items) {
      const d = String(r.fecha)
      byDate.set(d, (byDate.get(d) ?? 0) + Number(r.prediccion || 0))
    }
    return [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, value]) => ({ date, value }))
  }, [regresion, ejeGrafico, seleccion, claveTienda])

  const topProductos = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of regresion.prediccion) {
      const k = String(r.sku)
      m.set(k, (m.get(k) ?? 0) + Number(r.prediccion || 0))
    }
    return [...m.entries()]
      .map(([nombre, valor]) => ({ nombre, valor: Math.round(valor) }))
      .sort((a, b) => b.valor - a.valor)
      .slice(0, 10)
  }, [regresion])

  const resumen = useMemo(() => resumenPorSerie(regresion.prediccion), [regresion])
  const resumenCols = resumen[0] ? Object.keys(resumen[0]) : []

  const alertRows = useMemo(() => {
    const ordenadas = [...clasificacion.alertas].sort(
      (x, y) => Number(y.probabilidad) - Number(x.probabilidad),
    )
    return ordenadas
      .filter((a) => (soloAlerta ? Number(a.clase) === 1 : true))
      .map((a) => {
        const serie = Object.fromEntries(
          Object.entries(a)
            .filter(([k]) => k !== 'clase' && k !== 'probabilidad')
            .map(([k, v]) => [label(k), v]),
        )
        return {
          ...serie,
          '¿En alerta?': Number(a.clase) === 1 ? 'Sí' : 'No',
          Probabilidad: `${Math.round(Number(a.probabilidad) * 100)}%`,
        }
      })
  }, [clasificacion, soloAlerta])
  const alertCols = alertRows[0] ? Object.keys(alertRows[0]) : []
  const enAlerta = clasificacion.alertas.filter((a) => Number(a.clase) === 1).length

  const grupos = useMemo(() => {
    const clave = clustering.entidad ?? 'entidad'
    const m = new Map<string, string[]>()
    for (const s of clustering.segmentos) {
      const et = String(s.etiqueta)
      const arr = m.get(et) ?? []
      arr.push(String(s[clave]))
      m.set(et, arr)
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length)
  }, [clustering])
  const unidadGrupo = clustering.entidad === 'id_proveedor' ? 'proveedores' : 'productos'

  const indRows = useMemo(() => {
    const base = (data.indicadores_inventario ?? [])
      .filter((r) => (soloReponer ? r.alerta_reposicion : true))
      .sort((a, b) => (a.dias_cobertura_proyectada ?? 1e9) - (b.dias_cobertura_proyectada ?? 1e9))
    return base.map((r) => ({
      Producto: r.sku,
      Tienda: r.id_tienda,
      'Demanda prevista/día': r.demanda_diaria_prevista,
      'Stock actual': r.stock_actual,
      'Stock de seguridad': r.stock_seguridad,
      'Punto de reposición': r.punto_reposicion,
      'Días de cobertura': r.dias_cobertura_proyectada,
      '¿Reponer ya?': r.alerta_reposicion ? 'Sí' : 'No',
    }))
  }, [data, soloReponer])
  const totalReponer = (data.indicadores_inventario ?? []).filter((r) => r.alerta_reposicion).length

  const tituloPron = TITULO_PRONOSTICO[regresion.objetivo] ?? `Pronóstico de ${label(regresion.objetivo)}`
  const tituloAlerta = TITULO_ALERTA[clasificacion.etiqueta] ?? `Alertas de ${label(clasificacion.etiqueta)}`

  return (
    <div className="space-y-4">
      {/* PRONÓSTICO */}
      <section className="card space-y-3">
        <h3 className="text-base font-semibold text-slate-800">📈 {tituloPron} · próximos {regresion.horizonte} días</h3>
        {resumen.length > 0 ? (
          <>
            {/* Controles del gráfico de línea: total / por producto / por tienda */}
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-500">Ver:</span>
              {modos.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => cambiarEje(m)}
                  className={`rounded-full px-3 py-1 ${ejeGrafico === m ? `${accent.solid} text-white` : 'border border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                >
                  {m === 'total' ? 'Total' : m === 'producto' ? 'Por producto' : `Por ${etiquetaTienda}`}
                </button>
              ))}
              {ejeGrafico === 'producto' && (
                <select value={seleccion} onChange={(e) => setSeleccion(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1 text-sm">
                  {productos.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              )}
              {ejeGrafico === 'tienda' && (
                <select value={seleccion} onChange={(e) => setSeleccion(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1 text-sm">
                  {tiendas.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              )}
            </div>
            {forePoints.length > 0 && (
              <SerieChart history={[]} forecast={forePoints} histLabel="" foreLabel={`${ejeGrafico === 'total' ? 'Total' : seleccion} por día`} hex={accent.hex} />
            )}

            {/* Top productos (barras) */}
            {topProductos.length > 1 && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-600">Top {topProductos.length} productos por total previsto</p>
                <BarrasTop data={topProductos} hex={accent.hex} valorLabel="Total previsto" />
              </div>
            )}

            <p className="text-sm text-slate-500">Total previsto por {unidadGrupo === 'proveedores' ? 'proveedor y producto' : 'producto'} en los próximos {regresion.horizonte} días:</p>
            <TablaInteractiva rows={resumen} columns={resumenCols} buscarPlaceholder="Buscar producto/tienda…" />
          </>
        ) : (
          <p className="text-sm text-slate-500">Sin pronóstico (faltó historia suficiente).</p>
        )}
        <DetalleTecnico>
          <p>Modelo elegido: <span className="font-mono">{regresion.modelo_ganador}</span> · filas de entrenamiento: {regresion.n_filas_entrenamiento}</p>
          <Metricas metrics={regresion.metricas_honestas} />
        </DetalleTecnico>
      </section>

      {/* ALERTAS */}
      <section className="card space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold text-slate-800">🔔 {tituloAlerta}</h3>
          <span className={`badge ${accent.badge}`}>{enAlerta} de {clasificacion.alertas.length} en alerta</span>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={soloAlerta} onChange={(e) => setSoloAlerta(e.target.checked)} />
          Mostrar solo los que están en alerta
        </label>
        {alertRows.length > 0 ? (
          <TablaInteractiva rows={alertRows} columns={alertCols} buscarPlaceholder="Buscar producto/proveedor…" />
        ) : (
          <p className="text-sm text-slate-500">Ninguno en alerta. 🎉</p>
        )}
        <DetalleTecnico>
          <p>{clasificacion.definicion}</p>
          <p>Modelo: <span className="font-mono">{clasificacion.modelo_ganador}</span> · umbral {NUM.format(clasificacion.umbral)} · prevalencia {NUM.format(clasificacion.prevalencia)}</p>
          <Metricas metrics={clasificacion.metricas_honestas} />
        </DetalleTecnico>
      </section>

      {/* GRUPOS */}
      <section className="card space-y-3">
        <h3 className="text-base font-semibold text-slate-800">🧩 Grupos parecidos ({unidadGrupo})</h3>
        <div className="flex flex-wrap gap-2">
          {grupos.map(([etiqueta, ids]) => (
            <GrupoCard key={etiqueta} etiqueta={etiqueta} ids={ids} unidad={unidadGrupo} />
          ))}
        </div>
        <DetalleTecnico>
          <p>Algoritmo: {clustering.algoritmo} · grupos (k): {clustering.k}{clustering.silueta != null ? ` · silueta ${NUM.format(clustering.silueta)}` : ''}</p>
        </DetalleTecnico>
      </section>

      {/* ALMACÉN — reposición */}
      {(data.indicadores_inventario?.length ?? 0) > 0 && (
        <section className="card space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-base font-semibold text-slate-800">📦 Qué y cuándo reponer</h3>
            <span className={`badge ${accent.badge}`}>{totalReponer} por reponer</span>
          </div>
          <p className="text-sm text-slate-500">Calculado a partir del pronóstico de demanda: cuánto colchón dejar, cuándo pedir y si ya toca reponer.</p>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={soloReponer} onChange={(e) => setSoloReponer(e.target.checked)} />
            Mostrar solo los que hay que reponer ya
          </label>
          {indRows.length > 0 ? (
            <TablaInteractiva rows={indRows} columns={Object.keys(indRows[0])} buscarPlaceholder="Buscar producto/tienda…" />
          ) : (
            <p className="text-sm text-slate-500">Nada urgente por reponer. 🎉</p>
          )}
        </section>
      )}

      <DetalleTecnico>{data.nota}</DetalleTecnico>
    </div>
  )
}
