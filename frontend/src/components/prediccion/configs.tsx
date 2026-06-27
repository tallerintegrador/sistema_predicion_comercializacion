/**
 * Configuración por dominio del motor {@link PrediccionGuiada}. Cada `makeXConfig(accent)`
 * arma el `DomainConfig` de un modo (Ventas, Compras, Almacén) parametrizado solo por el
 * acento de color: así la **misma** configuración sirve para la sección dedicada (su acento)
 * y para el modo «Otro rubro» dentro de «Predicción a tu medida» (acento de marca), sin
 * duplicar la lógica de carga, predicción ni presentación del resultado.
 */
import { BarChart3, Package, ShoppingCart } from 'lucide-react'
import { postAutoInventory, postAutoPurchases, postAutoSales, uploadAutoExcel } from '../../api/endpoints'
import type {
  AutoInventoryResponse,
  AutoPurchasesResponse,
  AutoRow,
  AutoSalesResponse,
  Granularity,
} from '../../api/types'
import { ITEM_COLS_ALMACEN } from '../auto/itemCols'
import { ComingSoon } from '../ui/ComingSoon'
import type { Accent } from '../../theme/modules'
import { generarItemsDemo, generarItemsDemoAlmacen } from '../../demo/retailDemo'
import type { DomainConfig, ItemsConfig } from './PrediccionGuiada'
import { AlmacenResult, ComprasResult, VentasResult } from './resultados'
import { granularidadDe, horizonteDe, percentilDe } from './resumen'

// === Extractores de filas (+items) desde un JSON cargado ====================
function extraerFilasVentas(data: unknown): { rows: AutoRow[]; items: AutoRow[] } | null {
  if (Array.isArray(data)) return { rows: data as AutoRow[], items: [] }
  if (data && typeof data === 'object') {
    const o = data as { rows?: unknown; history?: unknown }
    if (Array.isArray(o.rows)) return { rows: o.rows as AutoRow[], items: [] }
    if (Array.isArray(o.history)) return { rows: o.history as AutoRow[], items: [] }
  }
  return null
}

function extraerConItems(data: unknown, itemKeys: string[]): { rows: AutoRow[]; items: AutoRow[] } | null {
  if (Array.isArray(data)) return { rows: data as AutoRow[], items: [] }
  if (data && typeof data === 'object') {
    const o = data as Record<string, unknown>
    const rows = Array.isArray(o.rows) ? o.rows : Array.isArray(o.history) ? o.history : null
    if (rows) {
      const itemsRaw = itemKeys.map((k) => o[k]).find(Array.isArray)
      return { rows: rows as AutoRow[], items: (itemsRaw as AutoRow[]) ?? [] }
    }
  }
  return null
}

// === Secciones de productos (Compras / Almacén) =============================
const ITEMS_COMPRAS: ItemsConfig = {
  titulo: 'Productos a reponer',
  ayuda: 'Stock actual, días de entrega y cobertura objetivo por producto.',
  avisoSinItems: 'Historial cargado. Genera o agrega los productos a reponer abajo.',
  generarDemo: generarItemsDemo,
  nuevoItem: () => ({ current_stock: 0, lead_time_days: 5, target_coverage_days: 14 }),
  valido: (it, series) =>
    series.every((k) => String(it[k] ?? '') !== '') &&
    Number(it.lead_time_days) > 0 &&
    Number(it.target_coverage_days) > 0,
}

const ITEMS_ALMACEN: ItemsConfig = {
  titulo: 'Estado del inventario',
  ayuda: 'Existencias actuales y tiempo de entrega por producto.',
  numCols: ITEM_COLS_ALMACEN,
  avisoSinItems: 'Historial cargado. Genera o agrega el estado del inventario abajo.',
  generarDemo: generarItemsDemoAlmacen,
  nuevoItem: () => ({ current_stock: 0, lead_time_days: 5 }),
  valido: (it, series) => series.every((k) => String(it[k] ?? '') !== '') && Number(it.lead_time_days) > 0,
}

const limpiarCompras = (items: AutoRow[]): AutoRow[] =>
  items.map((it) => ({
    ...it,
    current_stock: Number(it.current_stock) || 0,
    lead_time_days: Number(it.lead_time_days) || 0,
    target_coverage_days: Number(it.target_coverage_days) || 0,
  }))

const limpiarAlmacen = (items: AutoRow[]): AutoRow[] =>
  items.map((it) => ({
    ...it,
    current_stock: Number(it.current_stock) || 0,
    lead_time_days: Number(it.lead_time_days) || 0,
  }))

const quantileDe = (extra: Record<string, unknown>) => Math.min(0.95, Math.max(0.5, percentilDe(extra) / 100))

// === Builders por dominio (acento parametrizable) ===========================
export function makeSalesConfig(accent: Accent): DomainConfig<AutoSalesResponse> {
  return {
    domain: 'sales',
    accent,
    datosDescripcion:
      'Sube tus ventas pasadas con las columnas que tengas (fecha, tienda, producto, unidades, precio, promoción, categoría, ingresos…). Acepta cualquier columna rica.',
    extraerDatos: extraerFilasVentas,
    excelAviso: (f) => `Excel «${f}» listo: se enviará con la configuración actual al pronosticar.`,
    intencionLabel: {
      producto: 'Unidades vendidas (producto)',
      dinero: 'Ingresos (dinero)',
      otro: 'Otra cantidad',
    },
    paso2Titulo: '¿Qué quieres pronosticar?',
    paso2Desc:
      'Elige qué calcular (unidades, ingresos u otra cantidad) y confirma qué columnas son la fecha y las series. El resto de columnas se usan como factores.',
    mapeoLabels: {
      target: 'Columna a pronosticar',
      targetHelp: 'El valor numérico que quieres estimar a futuro.',
      series: 'Series (desglose)',
      seriesHelp: 'Tienda, producto… por qué columnas separar el pronóstico.',
    },
    extraInicial: {},
    renderExtra: ({ extra, set, busy, options }) =>
      options ? (
        <div className="flex flex-wrap items-start gap-4">
          <div>
            <label className="label" htmlFor="granularity">¿Cada cuánto?</label>
            <select
              id="granularity"
              className="input"
              value={granularidadDe(extra, options)}
              disabled={busy}
              onChange={(e) => set('granularity', e.target.value as Granularity)}
            >
              {options.granularities.map((g) => (
                <option key={g.name} value={g.name}>{g.label}</option>
              ))}
            </select>
            <p className="help">Día, semana o mes.</p>
          </div>
          <div>
            <label className="label" htmlFor="horizon">¿Hasta cuándo? ({options.horizon.min}–{options.horizon.max})</label>
            <input
              id="horizon"
              type="number"
              min={options.horizon.min}
              max={options.horizon.max}
              className="input w-32"
              value={horizonteDe(extra, options)}
              disabled={busy}
              onChange={(e) => {
                const n = Number(e.target.value)
                const { min, max } = options.horizon
                set('horizon', Number.isNaN(n) ? min : Math.min(Math.max(n, min), max))
              }}
            />
            <p className="help">Períodos de la granularidad elegida.</p>
          </div>
          <div className="opacity-60">
            <span className="label flex items-center gap-2">Rango estimado (80%) <ComingSoon /></span>
            <label className="mt-1 inline-flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" disabled />
              Mostrar el margen alto/bajo
            </label>
          </div>
        </div>
      ) : null,
    paso3Titulo: 'Pronostica y revisa el resultado',
    paso3Desc:
      'El sistema entrena varios modelos con tus datos, se queda con el mejor con validación honesta y predice — todo en una llamada.',
    botonAccion: 'Pronosticar',
    botonBusy: 'Entrenando y prediciendo…',
    faltaParaPredecir: 'Carga tus datos (JSON, Excel o el ejemplo) para pronosticar.',
    predecir: ({ schema, rows, extra, options }) =>
      postAutoSales({ schema, horizon: horizonteDe(extra, options), granularity: granularidadDe(extra, options), rows }),
    predecirExcel: ({ schema, file, extra, options }) =>
      uploadAutoExcel<AutoSalesResponse>('sales', file, {
        schema: JSON.stringify(schema),
        horizon: horizonteDe(extra, options),
        granularity: granularidadDe(extra, options),
      }),
    empty: {
      icon: BarChart3,
      titulo: 'Aún no hay un pronóstico',
      mensaje:
        'Carga tus datos, elige qué pronosticar y pulsa «Pronosticar». Verás un gráfico, una tabla descargable y un resumen claro.',
    },
    renderResultado: (a) => <VentasResult {...a} accent={accent} />,
  }
}

export function makePurchasesConfig(accent: Accent): DomainConfig<AutoPurchasesResponse> {
  return {
    domain: 'purchases',
    accent,
    datosDescripcion:
      'Sube tu historial de ventas con las columnas que tengas (cualquier columna rica) y define los productos a reponer.',
    extraerDatos: (d) => extraerConItems(d, ['items', 'replenishment_params']),
    excelAviso: (f) => `Excel «${f}» listo: completa los productos a reponer y calcula.`,
    items: ITEMS_COMPRAS,
    intencionLabel: {
      producto: 'Demanda en unidades (producto)',
      dinero: 'Demanda en dinero',
      otro: 'Otra cantidad',
    },
    paso2Titulo: '¿Qué demanda pronosticar?',
    paso2Desc:
      'Elige qué demanda estimar (unidades, dinero u otra cantidad) y confirma qué columnas son la fecha y las series. El resto de columnas se usan como factores.',
    mapeoLabels: {
      target: 'Columna de demanda',
      targetHelp: 'El valor numérico cuya demanda futura quieres estimar.',
      series: 'Series (producto a reponer)',
      seriesHelp: 'Tienda, producto… deben coincidir con los productos a reponer.',
    },
    paso3Titulo: 'Calcula la reposición',
    paso3Desc:
      'El sistema entrena el mejor modelo para tu demanda con validación honesta y calcula cuánto y cuándo reponer cada producto.',
    botonAccion: 'Calcular reposición',
    botonBusy: 'Calculando…',
    faltaParaPredecir:
      'Carga tu historial, elige qué pronosticar y completa los productos a reponer (entrega y cobertura > 0).',
    predecir: ({ schema, rows, items }) => postAutoPurchases({ schema, rows, items: limpiarCompras(items) }),
    predecirExcel: ({ schema, file, items }) =>
      uploadAutoExcel<AutoPurchasesResponse>('purchases', file, {
        schema: JSON.stringify(schema),
        items: JSON.stringify(limpiarCompras(items)),
      }),
    empty: {
      icon: ShoppingCart,
      titulo: 'Aún no hay recomendaciones',
      mensaje: 'Carga tus productos y su historial, y calcula cuánto y cuándo reponer cada uno.',
    },
    renderResultado: (a) => <ComprasResult {...a} accent={accent} />,
  }
}

export function makeInventoryConfig(accent: Accent): DomainConfig<AutoInventoryResponse> {
  return {
    domain: 'inventory',
    accent,
    datosDescripcion:
      'Sube tu historial de ventas con las columnas que tengas (cualquier columna rica) y añade el estado de tus existencias.',
    extraerDatos: (d) => extraerConItems(d, ['items', 'inventory_status']),
    excelAviso: (f) => `Excel «${f}» listo: completa el estado del inventario y analiza.`,
    items: ITEMS_ALMACEN,
    intencionLabel: {
      producto: 'Demanda en unidades (producto)',
      dinero: 'Demanda en dinero',
      otro: 'Otra cantidad',
    },
    paso2Titulo: '¿Qué demanda evaluar?',
    paso2Desc:
      'Elige qué demanda estimar y confirma qué columnas son la fecha y las series. Define también qué cuenta como «demanda alta».',
    mapeoLabels: {
      target: 'Columna de demanda',
      targetHelp: 'El valor numérico cuya demanda se evalúa.',
      series: 'Series (producto)',
      seriesHelp: 'Deben coincidir con el estado del inventario.',
    },
    extraInicial: { percentil: 75 },
    renderExtra: ({ extra, set, busy }) => (
      <div>
        <label className="label" htmlFor="percentil">¿Qué es «demanda alta»? (percentil)</label>
        <input
          id="percentil"
          type="number"
          min={50}
          max={95}
          className="input w-32"
          value={percentilDe(extra)}
          disabled={busy}
          onChange={(e) => {
            const n = Number(e.target.value)
            set('percentil', Number.isNaN(n) ? 75 : Math.min(95, Math.max(50, n)))
          }}
        />
        <p className="help">Un producto es de demanda alta si supera este percentil de su propia serie.</p>
      </div>
    ),
    paso3Titulo: 'Revisa el riesgo de agotamiento',
    paso3Desc:
      'El sistema entrena un clasificador de demanda alta con validación honesta e identifica qué productos pueden agotarse y cuántas existencias conviene tener.',
    botonAccion: 'Revisar riesgo de agotamiento',
    botonBusy: 'Calculando…',
    faltaParaPredecir: 'Carga tu historial, elige qué evaluar y completa el estado del inventario (entrega > 0).',
    predecir: ({ schema, rows, items, extra }) =>
      postAutoInventory({ schema, rows, items: limpiarAlmacen(items), high_demand_quantile: quantileDe(extra) }),
    predecirExcel: ({ schema, file, items, extra }) =>
      uploadAutoExcel<AutoInventoryResponse>('inventory', file, {
        schema: JSON.stringify(schema),
        items: JSON.stringify(limpiarAlmacen(items)),
        high_demand_quantile: quantileDe(extra),
      }),
    empty: {
      icon: Package,
      titulo: 'Aún no hay un análisis',
      mensaje:
        'Carga tus productos y su historial para ver cuáles tienen riesgo de agotarse y cuántas existencias conviene tener.',
    },
    renderResultado: (a) => <AlmacenResult {...a} accent={accent} />,
  }
}
