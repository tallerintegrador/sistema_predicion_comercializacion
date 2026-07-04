/**
 * Renderidores compactos por tipo de reporte.
 * - Regresión: número principal + barras por dimensión (primario) + tabla; scatter real-vs-predicho colapsado.
 * - Clasificación: binaria (dona + tabla) o multiclase (barras por categoría + tabla).
 * - Clustering: tarjetas por grupo (primario) + mapa de segmentos (coordenadas REALES) colapsado.
 * Unidades y formato leídos del backend (result.unit). Claves del contrato en inglés (ADR-0028).
 */
import { useMemo, useState } from 'react'
import type { QueryReport, AutoRow } from '../../api/types'
import { TablaInteractiva } from '../ui/TablaInteractiva'
import { ScatterChart } from '../charts/ScatterChart'
import { BarrasTop } from '../charts/BarrasTop'
import { InfoTooltip } from '../ui/InfoTooltip'
import { fmtValor } from '../../utils/format'
import {
  ScatterChart as RechartsScatter,
  Scatter,
  Cell,
  ResponsiveContainer,
  PieChart,
  Pie,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

interface RenderidorProps {
  reporte: QueryReport
  accentHex: string
}

const COLORES_GRUPO = ['#2563eb', '#f97316', '#16a34a', '#db2777', '#7c3aed', '#0891b2']

function humaniza(col: string): string {
  const mapeo: Record<string, string> = {
    id_tienda: 'Tienda',
    id_proveedor: 'Proveedor',
    sku: 'Producto',
    categoria: 'Categoría',
    fecha: 'Fecha',
    fecha_orden: 'Fecha',
    canal_venta: 'Canal',
    metodo_pago: 'Método de pago',
    zona_almacen: 'Zona',
    en_promocion: 'En promoción',
    descuento_pct: 'Descuento %',
    descuento_volumen: 'Descuento volumen',
    es_fin_de_semana: 'Fin de semana',
    dias_a_proximo_feriado: 'Días a feriado',
    tiempo_reposicion_dias: 'Días de reposición',
    lead_time_dias: 'Días de entrega',
    unidades_vendidas: 'Unidades',
    ingreso: 'Ingreso',
    precio_unitario: 'Precio',
    precio_unitario_compra: 'Precio compra',
    cantidad_pedida: 'Cantidad',
    stock_actual: 'Stock actual',
    stock_maximo: 'Stock máximo',
    demanda_diaria_promedio: 'Demanda media',
    dias_de_cobertura: 'Días de cobertura',
    rotacion: 'Rotación',
  }
  return mapeo[col] ?? col.replace(/_/g, ' ')
}

/** Regresión: número principal + barras por dimensión + tabla; scatter real-vs-predicho colapsado. */
export function RenderidorRegresion({ reporte, accentHex }: RenderidorProps) {
  const resultado = reporte.result as Record<string, unknown>
  const unidad = (reporte.unit || (resultado.unit as string) || '') as string
  const predicciones = Array.isArray(resultado?.predictions)
    ? (resultado.predictions as Array<Record<string, unknown>>)
    : []

  // A2: el recuadro resumen lo decide el backend (suma para extensivas, promedio para
  // intensivas), leído del catálogo. El frontend solo lo muestra.
  const summary = reporte.summary

  // Agrupar por dimensiones (todo excepto value/actual/fecha)
  const filas: AutoRow[] = useMemo(() => {
    const mapa = new Map<string, { dims: Record<string, unknown>; total: number; n: number }>()
    for (const p of predicciones) {
      const dims = Object.fromEntries(
        Object.entries(p).filter(([k]) => !['value', 'actual', 'fecha', 'fecha_orden'].includes(k)),
      )
      const id = JSON.stringify(dims)
      const e = mapa.get(id) ?? { dims, total: 0, n: 0 }
      e.total += Number(p.value) || 0
      e.n += 1
      mapa.set(id, e)
    }
    return [...mapa.values()]
      .map((e) => ({
        ...Object.fromEntries(Object.entries(e.dims).map(([k, v]) => [humaniza(k), v])),
        'Total estimado': Math.round(e.total),
        'Promedio': Math.round((e.total / Math.max(1, e.n)) * 10) / 10,
      }))
      .sort((a, b) => Number(b['Total estimado']) - Number(a['Total estimado']))
  }, [predicciones])

  const topItems = useMemo(
    () =>
      filas.slice(0, 8).map((f) => {
        const keys = Object.keys(f).filter((k) => k !== 'Total estimado' && k !== 'Promedio')
        return { nombre: String(f[keys[0]] ?? '?'), valor: Number(f['Total estimado'] ?? 0) }
      }),
    [filas],
  )

  const scatter = useMemo(
    () =>
      predicciones
        .slice(0, 200)
        .map((p) => ({ x: Number(p.actual) || 0, y: Number(p.value) || 0 })),
    [predicciones],
  )

  const columnas = filas[0] ? Object.keys(filas[0]) : []

  if (predicciones.length === 0)
    return <p className="text-sm text-slate-500 italic">Sin predicciones con los datos proporcionados.</p>

  return (
    <div className="space-y-3">
      {/* Número principal (A2): suma o promedio según la magnitud del objetivo (del catálogo) */}
      {summary && (
        <div className="rounded-lg px-3 py-2" style={{ backgroundColor: `${accentHex}10` }}>
          <div className="text-xs text-slate-500">{summary.label} (periodo reciente)</div>
          <div className="text-3xl font-bold" style={{ color: accentHex }}>
            {fmtValor(summary.value, summary.unit || unidad)}
          </div>
        </div>
      )}

      {/* Gráfico primario: barras por dimensión */}
      {topItems.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500 mb-1">Top por {columnas[0]?.toLowerCase()}:</p>
          <BarrasTop data={topItems} hex={accentHex} valorLabel={`Total (${unidad || 'valor'})`} />
          <p className="text-xs text-slate-400 mt-1">
            Cada barra suma el valor estimado del periodo por {columnas[0]?.toLowerCase()}
            {unidad ? ` (en ${unidad})` : ''}.
          </p>
        </div>
      )}

      {/* Tabla por dimensión */}
      {filas.length > 0 && (
        <TablaInteractiva rows={filas} columns={columnas} inicial={5} buscarPlaceholder="Buscar…" />
      )}

      {/* Secundario colapsado: real vs. predicho */}
      {scatter.length >= 2 && (
        <details className="rounded-lg border border-slate-200 bg-slate-50/60 p-2">
          <summary className="cursor-pointer select-none text-xs font-medium text-slate-500">
            Ver precisión: valor real vs. predicho
          </summary>
          <div className="mt-2">
            <ScatterChart
              data={scatter}
              xLabel="Valor real"
              yLabel="Valor predicho"
              hex={accentHex}
              showTrendline
            />
            <p className="text-xs text-slate-400 mt-1">
              Cada punto es un caso del periodo de prueba. Cuanto más cerca de la línea, mejor la predicción.
            </p>
          </div>
        </details>
      )}
    </div>
  )
}

/** Clasificación: binaria (dona) o multiclase (barras por categoría predicha). */
export function RenderidorClasificacion({ reporte, accentHex }: RenderidorProps) {
  const resultado = reporte.result as Record<string, unknown>
  const predicciones = Array.isArray(resultado?.predictions)
    ? (resultado.predictions as Array<Record<string, unknown>>)
    : []
  const esMulticlase = predicciones.length > 0 && 'predicted_class' in predicciones[0]

  if (predicciones.length === 0)
    return <p className="text-sm text-slate-500 italic">Sin predicciones.</p>

  return esMulticlase ? (
    <RenderMulticlase predicciones={predicciones} accentHex={accentHex} />
  ) : (
    <RenderBinaria predicciones={predicciones} accentHex={accentHex} />
  )
}

function RenderBinaria({
  predicciones,
  accentHex,
}: {
  predicciones: Array<Record<string, unknown>>
  accentHex: string
}) {
  const [soloAlerta, setSoloAlerta] = useState(true)
  const enAlerta = predicciones.filter((p) => Number(p.class) === 1).length
  const normal = predicciones.length - enAlerta

  const filas: AutoRow[] = useMemo(
    () =>
      predicciones
        .map((p) => {
          const dims = Object.fromEntries(
            Object.entries(p).filter(([k]) => !['class', 'probability'].includes(k)),
          )
          return {
            ...Object.fromEntries(Object.entries(dims).map(([k, v]) => [humaniza(k), v])),
            '¿En alerta?': Number(p.class) === 1 ? 'Sí' : 'No',
            'Confianza (%)': Math.round(Number(p.probability ?? 0) * 100),
          }
        })
        .filter((f) => (soloAlerta ? f['¿En alerta?'] === 'Sí' : true))
        .sort((a, b) => Number(b['Confianza (%)']) - Number(a['Confianza (%)'])),
    [predicciones, soloAlerta],
  )

  const dona = [
    { name: `En alerta (${enAlerta})`, value: enAlerta },
    { name: `Normal (${normal})`, value: normal },
  ]
  const cols = filas[0] ? Object.keys(filas[0]) : []

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <ResponsiveContainer width="45%" height={160}>
          <PieChart>
            <Pie data={dona} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={40} outerRadius={70}>
              <Cell fill={accentHex} />
              <Cell fill="#e2e8f0" />
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
        <div className="text-sm">
          <div className="text-2xl font-bold" style={{ color: accentHex }}>{enAlerta}</div>
          <div className="text-slate-500">
            en alerta de {predicciones.length}{' '}
            <InfoTooltip text={`De ${predicciones.length} casos del conjunto de prueba (los más recientes, que el modelo no vio al entrenar), ${enAlerta} quedaron marcados en alerta.`} />
          </div>
        </div>
      </div>
      <p className="text-xs text-slate-400">
        El aro muestra cuántos casos quedaron <b>en alerta</b> vs. normales, sobre {predicciones.length} casos del
        periodo de prueba.
      </p>

      <label className="flex items-center gap-2 text-xs text-slate-600">
        <input type="checkbox" checked={soloAlerta} onChange={(e) => setSoloAlerta(e.target.checked)} />
        Mostrar solo alertas
      </label>
      {filas.length > 0 ? (
        <TablaInteractiva rows={filas} columns={cols} inicial={6} buscarPlaceholder="Buscar…" />
      ) : (
        <p className="text-sm text-slate-500 italic">
          {soloAlerta ? '¡Ninguno en alerta con los datos de prueba!' : 'Sin datos.'}
        </p>
      )}
    </div>
  )
}

function RenderMulticlase({
  predicciones,
  accentHex,
}: {
  predicciones: Array<Record<string, unknown>>
  accentHex: string
}) {
  const conteo = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of predicciones) {
      const c = String(p.predicted_class ?? '—')
      m.set(c, (m.get(c) ?? 0) + 1)
    }
    return [...m.entries()].map(([nombre, valor]) => ({ nombre, valor })).sort((a, b) => b.valor - a.valor)
  }, [predicciones])

  // ITEM 7: la tabla sigue el MISMO orden que el gráfico (primero la categoría más frecuente,
  // mismo ranking que las barras) y, dentro de cada categoría, por confianza. Así tabla y
  // gráfico coinciden y no confunden (antes la tabla ordenaba solo por confianza).
  const rankCategoria = useMemo(() => {
    const m = new Map<string, number>()
    conteo.forEach((c, i) => m.set(c.nombre, i))
    return m
  }, [conteo])

  const filas: AutoRow[] = useMemo(
    () =>
      predicciones
        .map((p) => {
          const dims = Object.fromEntries(
            Object.entries(p).filter(([k]) => !['predicted_class', 'probability'].includes(k)),
          )
          return {
            ...Object.fromEntries(Object.entries(dims).map(([k, v]) => [humaniza(k), v])),
            'Predicción': String(p.predicted_class ?? '—'),
            'Confianza (%)': Math.round(Number(p.probability ?? 0) * 100),
          }
        })
        .sort((a, b) => {
          const ra = rankCategoria.get(String(a['Predicción'])) ?? 999
          const rb = rankCategoria.get(String(b['Predicción'])) ?? 999
          return ra !== rb ? ra - rb : Number(b['Confianza (%)']) - Number(a['Confianza (%)'])
        }),
    [predicciones, rankCategoria],
  )
  const cols = filas[0] ? Object.keys(filas[0]) : []

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Esta alerta <b>elige una categoría</b> (no es sí/no). Predicción más frecuente:{' '}
        <b>{conteo[0]?.nombre}</b>.
      </p>
      <BarrasTop data={conteo} hex={accentHex} valorLabel="Casos previstos" />
      <p className="text-xs text-slate-400">
        Cada barra = cuántos casos del periodo de prueba caen en esa categoría. La tabla de abajo
        sigue el mismo orden (categoría más frecuente primero, y dentro de cada una por confianza).
      </p>
      {filas.length > 0 && (
        <TablaInteractiva rows={filas} columns={cols} inicial={6} buscarPlaceholder="Buscar…" />
      )}
    </div>
  )
}

/** Clustering: tarjetas por grupo (primario) + mapa de segmentos con coordenadas REALES (colapsado). */
export function RenderidorClustering({ reporte }: RenderidorProps) {
  const resultado = reporte.result as Record<string, unknown>
  const segmentos = Array.isArray(resultado?.predictions)
    ? (resultado.predictions as Array<Record<string, unknown>>)
    : []
  const ejes = (resultado.axes as { x?: string; y?: string }) ?? {}

  const grupos = useMemo(() => {
    const m = new Map<string, { entidades: string[]; grupo: number }>()
    for (const s of segmentos) {
      const et = String(s.label ?? 'Grupo')
      const e = m.get(et) ?? { entidades: [], grupo: Number(s.group ?? 0) }
      e.entidades.push(String(s.entity ?? '—'))
      m.set(et, e)
    }
    return [...m.entries()].sort((a, b) => b[1].entidades.length - a[1].entidades.length)
  }, [segmentos])

  const colorDe = (grupo: number) => COLORES_GRUPO[grupo % COLORES_GRUPO.length]

  const puntos = useMemo(
    () =>
      segmentos.map((s) => ({
        x: Number(s.x) || 0,
        y: Number(s.y) || 0,
        color: colorDe(Number(s.group ?? 0)),
        entidad: String(s.entity ?? ''),
      })),
    [segmentos],
  )

  if (grupos.length === 0)
    return <p className="text-sm text-slate-500 italic">Sin segmentos identificados con estos datos.</p>

  return (
    <div className="space-y-3">
      {/* Tarjetas por grupo (primario) */}
      <div className="grid gap-2 sm:grid-cols-2">
        {grupos.map(([etiqueta, { entidades, grupo }]) => (
          <GrupoCard key={etiqueta} etiqueta={etiqueta} entidades={entidades} color={colorDe(grupo)} />
        ))}
      </div>

      {/* Mapa de segmentos con coordenadas reales (colapsado) */}
      {puntos.length > 0 && (
        <details className="rounded-lg border border-slate-200 bg-slate-50/60 p-2">
          <summary className="cursor-pointer select-none text-xs font-medium text-slate-500">
            Ver mapa de segmentos
          </summary>
          <div className="mt-2">
            <ResponsiveContainer width="100%" height={240}>
              <RechartsScatter margin={{ top: 12, right: 16, bottom: 28, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  type="number"
                  dataKey="x"
                  name={humaniza(ejes.x ?? 'x')}
                  tick={{ fontSize: 10 }}
                  label={{ value: humaniza(ejes.x ?? ''), position: 'bottom', offset: 0, fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  name={humaniza(ejes.y ?? 'y')}
                  tick={{ fontSize: 10 }}
                  label={{ value: humaniza(ejes.y ?? ''), angle: -90, position: 'insideLeft', fontSize: 11 }}
                />
                <ZAxis range={[60, 60]} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(value) => Number(value).toFixed(2)} />
                <Scatter data={puntos}>
                  {puntos.map((p, i) => (
                    <Cell key={i} fill={p.color} />
                  ))}
                </Scatter>
              </RechartsScatter>
            </ResponsiveContainer>
            <p className="text-xs text-slate-400 mt-1">
              Cómo leer esto: cada punto es una entidad y cada color un grupo. Los ejes son una
              proyección 2D para <b>ver similitud</b> (no tienen unidades de negocio): puntos cercanos = parecidos.
            </p>
          </div>
        </details>
      )}
    </div>
  )
}

function GrupoCard({ etiqueta, entidades, color }: { etiqueta: string; entidades: string[]; color: string }) {
  const [abierto, setAbierto] = useState(false)
  const muestra = abierto ? entidades : entidades.slice(0, 4)
  return (
    <div className="rounded-lg border p-2.5" style={{ borderColor: color, backgroundColor: `${color}0d` }}>
      <div className="flex items-center gap-2">
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: color }}
          role="img"
          aria-label={`Color del grupo ${etiqueta}`}
        />
        <p className="text-sm font-semibold text-slate-800">{etiqueta}</p>
      </div>
      <p className="text-xs text-slate-500 mt-0.5">{entidades.length} elementos</p>
      <p className="text-xs text-slate-600 mt-1">{muestra.join(', ')}</p>
      {entidades.length > 4 && (
        <button type="button" className="mt-1 text-xs font-medium" style={{ color }} onClick={() => setAbierto((v) => !v)}>
          {abierto ? 'Ver menos' : `Ver todos (${entidades.length})`}
        </button>
      )}
    </div>
  )
}
