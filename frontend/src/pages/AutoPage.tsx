import { useMemo, useState } from 'react'
import { Wand2 } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  downloadAutoTemplate,
  postAutoInventory,
  postAutoPurchases,
  postAutoSales,
  uploadAutoExcel,
} from '../api/endpoints'
import type {
  AutoInventoryResponse,
  AutoPurchasesResponse,
  AutoRow,
  AutoSalesResponse,
  AutoSchemaSpec,
} from '../api/types'
import { ErrorPanel } from '../components/ErrorPanel'
import { ResultTable } from '../components/ResultTable'
import { ModuleHeader } from '../components/ui/ModuleHeader'
import { StepSection } from '../components/ui/StepSection'
import { EmptyState } from '../components/ui/EmptyState'
import { TechnicalDetails } from '../components/ui/TechnicalDetails'
import { TrainingCard } from '../components/auto/TrainingCard'
import { SECTION_BY_ID } from '../theme/modules'
import { fmtNum } from '../utils/format'
import { columnasDinamicas } from '../utils/autoColumns'

const ACCENT = SECTION_BY_ID.auto.accent

type AutoDomain = 'sales' | 'inventory' | 'purchases'
type AnyResponse = AutoSalesResponse | AutoInventoryResponse | AutoPurchasesResponse

const DOMAIN_LABEL: Record<AutoDomain, string> = {
  sales: 'Ventas (pronóstico)',
  inventory: 'Almacén (riesgo de quiebre)',
  purchases: 'Compras (reposición)',
}

/** Esquema de demostración: cadena minorista **multi-país** (Perú, Bolivia, España,
 *  México), rubro de almacén con columnas libres. Reúne ~40 drivers en cuatro familias:
 *  comerciales/calendario, macro/país (moneda, tipo de cambio, feriado y día de pago
 *  locales), atributos de producto e inventario (solo-pasado, de una mini-simulación de
 *  stock). Es el mismo esquema que `examples/api/generar_auto_retail.py`. */
const SCHEMA_DEMO: AutoSchemaSpec = {
  target: 'unidades_vendidas',
  date: 'fecha',
  series_keys: ['almacen', 'sku'],
  features: [
    // Comerciales / calendario (conocidas a futuro)
    { name: 'precio', type: 'numeric', known_future: true },
    { name: 'en_promo', type: 'numeric', known_future: true },
    { name: 'descuento_pct', type: 'numeric', known_future: true },
    { name: 'es_feriado', type: 'numeric', known_future: true },
    { name: 'vispera_feriado', type: 'numeric', known_future: true },
    { name: 'campaña_mkt', type: 'numeric', known_future: true },
    { name: 'temperatura', type: 'numeric', known_future: true },
    { name: 'clima', type: 'categorical', known_future: true },
    { name: 'evento_cercano', type: 'categorical', known_future: true },
    { name: 'categoria', type: 'categorical', known_future: true },
    { name: 'segmento_almacen', type: 'categorical', known_future: true },
    { name: 'proveedor', type: 'categorical', known_future: true },
    // Macro / país (conocidas a futuro)
    { name: 'pais', type: 'categorical', known_future: true },
    { name: 'moneda', type: 'categorical', known_future: true },
    { name: 'tipo_cambio_usd', type: 'numeric', known_future: true },
    { name: 'festividad_local', type: 'categorical', known_future: true },
    { name: 'temporada', type: 'categorical', known_future: true },
    { name: 'dia_pago_local', type: 'numeric', known_future: true },
    { name: 'inicio_clases', type: 'numeric', known_future: true },
    // Atributos de producto (conocidas a futuro)
    { name: 'perecedero', type: 'numeric', known_future: true },
    { name: 'vida_util_dias', type: 'numeric', known_future: true },
    { name: 'marca', type: 'categorical', known_future: true },
    { name: 'unidad_medida', type: 'categorical', known_future: true },
    { name: 'peso_kg', type: 'numeric', known_future: true },
    // Logística (conocidas a futuro)
    { name: 'costo_flete', type: 'numeric', known_future: true },
    { name: 'precio_combustible', type: 'numeric', known_future: true },
    { name: 'confiabilidad_proveedor', type: 'numeric', known_future: true },
    // Tienda / competencia (solo pasado)
    { name: 'trafico_tienda', type: 'numeric', known_future: false },
    { name: 'transacciones', type: 'numeric', known_future: false },
    { name: 'competidor_promo', type: 'numeric', known_future: false },
    { name: 'precio_competidor', type: 'numeric', known_future: false },
    { name: 'quiebre_stock_prev', type: 'numeric', known_future: false },
    // Inventario / almacén (solo pasado)
    { name: 'ventas_online', type: 'numeric', known_future: false },
    { name: 'devoluciones', type: 'numeric', known_future: false },
    { name: 'recepciones', type: 'numeric', known_future: false },
    { name: 'stock_inicial_dia', type: 'numeric', known_future: false },
    { name: 'dias_cobertura', type: 'numeric', known_future: false },
    { name: 'rotacion_inventario', type: 'numeric', known_future: false },
    { name: 'pedidos_pendientes', type: 'numeric', known_future: false },
    { name: 'lead_time_real', type: 'numeric', known_future: false },
  ],
}

type PaisDemo = { hemisferio: 'sur' | 'norte'; moneda: string; fxRef: number; fuelRef: number; online: number }

const PAISES_DEMO: Record<string, PaisDemo> = {
  Peru: { hemisferio: 'sur', moneda: 'PEN', fxRef: 3.75, fuelRef: 4.4, online: 0.14 },
  Bolivia: { hemisferio: 'sur', moneda: 'BOB', fxRef: 6.96, fuelRef: 3.74, online: 0.08 },
  Espana: { hemisferio: 'norte', moneda: 'EUR', fxRef: 0.92, fuelRef: 1.65, online: 0.3 },
  Mexico: { hemisferio: 'norte', moneda: 'MXN', fxRef: 17.1, fuelRef: 24.5, online: 0.22 },
}

/** Feriados nacionales 2024 por país (clave MM-DD → festividad local). */
const FERIADOS_DEMO: Record<string, Record<string, string>> = {
  Peru: { '01-01': 'ano_nuevo', '05-01': 'dia_trabajo', '06-29': 'san_pedro' },
  Bolivia: { '01-01': 'ano_nuevo', '01-22': 'estado_plurinacional', '05-01': 'dia_trabajo' },
  Espana: { '01-01': 'ano_nuevo', '01-06': 'reyes', '05-01': 'dia_trabajo' },
  Mexico: { '01-01': 'ano_nuevo', '02-05': 'dia_constitucion', '05-01': 'dia_trabajo' },
}

type SerieDemo = {
  pais: string
  almacen: string
  sku: string
  categoria: string
  segmento: string
  proveedor: string
  base: number
  precio0: number
  elas: number
  traficoBase: number
  tempBase: number
  tempAmp: number
  tempSens: number
  perecedero: number
  vidaUtil: number
  marca: string
  unidad: string
  peso: number
  importado: number
  escolar: number
  lead: number
  moq: number
  costo: number
  flete: number
  conf: number
}

const SERIES_DEMO: SerieDemo[] = [
  { pais: 'Peru', almacen: 'lima_norte', sku: 'ARROZ-5KG', categoria: 'abarrotes', segmento: 'urbano', proveedor: 'Molinos del Norte', base: 52, precio0: 24.9, elas: 0.6, traficoBase: 260, tempBase: 20, tempAmp: 5, tempSens: 0, perecedero: 0, vidaUtil: 540, marca: 'DonArroz', unidad: 'saco', peso: 5, importado: 0.1, escolar: 0.1, lead: 5, moq: 50, costo: 19.5, flete: 1.8, conf: 0.88 },
  { pais: 'Peru', almacen: 'arequipa', sku: 'GASEOSA-3L', categoria: 'bebidas', segmento: 'turistico', proveedor: 'Embotelladora Sur', base: 47, precio0: 9.9, elas: 1.8, traficoBase: 150, tempBase: 16, tempAmp: 6, tempSens: 0.022, perecedero: 0, vidaUtil: 180, marca: 'ColaSur', unidad: 'botella', peso: 3, importado: 0.05, escolar: 0, lead: 3, moq: 80, costo: 7.2, flete: 1.1, conf: 0.9 },
  { pais: 'Bolivia', almacen: 'la_paz', sku: 'LECHE-1L', categoria: 'lacteos', segmento: 'urbano', proveedor: 'Gloria SA', base: 70, precio0: 4.5, elas: 0.5, traficoBase: 200, tempBase: 12, tempAmp: 4, tempSens: 0.004, perecedero: 1, vidaUtil: 7, marca: 'Gloria', unidad: 'litro', peso: 1, importado: 0, escolar: 0.18, lead: 2, moq: 120, costo: 3.4, flete: 0.6, conf: 0.95 },
  { pais: 'Bolivia', almacen: 'santa_cruz', sku: 'ACEITE-1L', categoria: 'abarrotes', segmento: 'residencial', proveedor: 'Alicorp', base: 40, precio0: 11.2, elas: 0.9, traficoBase: 210, tempBase: 25, tempAmp: 5, tempSens: 0, perecedero: 0, vidaUtil: 365, marca: 'Primor', unidad: 'botella', peso: 0.92, importado: 0.3, escolar: 0, lead: 4, moq: 60, costo: 14.1, flete: 1.4, conf: 0.92 },
  { pais: 'Espana', almacen: 'madrid', sku: 'DETERGENTE-2KG', categoria: 'limpieza', segmento: 'urbano', proveedor: 'Alicorp', base: 45, precio0: 18.5, elas: 1, traficoBase: 300, tempBase: 15, tempAmp: 12, tempSens: 0, perecedero: 0, vidaUtil: 730, marca: 'Bolivar', unidad: 'bolsa', peso: 2, importado: 0.2, escolar: 0.05, lead: 4, moq: 60, costo: 14.1, flete: 1.4, conf: 0.92 },
  { pais: 'Espana', almacen: 'barcelona', sku: 'GASEOSA-3L', categoria: 'bebidas', segmento: 'turistico', proveedor: 'Embotelladora Sur', base: 60, precio0: 9.9, elas: 1.8, traficoBase: 280, tempBase: 17, tempAmp: 9, tempSens: 0.022, perecedero: 0, vidaUtil: 180, marca: 'ColaSur', unidad: 'botella', peso: 3, importado: 0.05, escolar: 0, lead: 3, moq: 80, costo: 7.2, flete: 1.1, conf: 0.9 },
  { pais: 'Mexico', almacen: 'cdmx', sku: 'ARROZ-5KG', categoria: 'abarrotes', segmento: 'urbano', proveedor: 'Molinos del Norte', base: 58, precio0: 24.9, elas: 0.6, traficoBase: 320, tempBase: 18, tempAmp: 7, tempSens: 0, perecedero: 0, vidaUtil: 540, marca: 'DonArroz', unidad: 'saco', peso: 5, importado: 0.1, escolar: 0.1, lead: 5, moq: 50, costo: 19.5, flete: 1.8, conf: 0.88 },
  { pais: 'Mexico', almacen: 'monterrey', sku: 'LECHE-1L', categoria: 'lacteos', segmento: 'residencial', proveedor: 'Gloria SA', base: 66, precio0: 4.5, elas: 0.5, traficoBase: 240, tempBase: 24, tempAmp: 10, tempSens: 0.004, perecedero: 1, vidaUtil: 7, marca: 'Gloria', unidad: 'litro', peso: 1, importado: 0, escolar: 0.18, lead: 2, moq: 120, costo: 3.4, flete: 0.6, conf: 0.95 },
]

const CLIMAS_DEMO = ['soleado', 'nublado', 'lluvia']
const r2 = (x: number) => Math.round(x * 100) / 100
const mmdd = (d: Date) => `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const doy = (d: Date) => Math.floor((d.getTime() - new Date(d.getFullYear(), 0, 0).getTime()) / 86400000)

const finDeMes = (d: Date) => {
  const m = new Date(d)
  m.setDate(d.getDate() + 1)
  return m.getDate() === 1
}
const esFeriado = (pais: string, d: Date) => (mmdd(d) in FERIADOS_DEMO[pais] ? 1 : 0)
const festividad = (pais: string, d: Date) => FERIADOS_DEMO[pais][mmdd(d)] ?? 'ninguna'
const vispera = (pais: string, d: Date) => {
  const m = new Date(d)
  m.setDate(d.getDate() + 1)
  return esFeriado(pais, m)
}
const diaPago = (pais: string, d: Date) =>
  pais === 'Espana' ? (finDeMes(d) ? 1 : 0) : d.getDate() === 15 || finDeMes(d) ? 1 : 0
const inicioClases = (pais: string, d: Date) => {
  const hemis = PAISES_DEMO[pais].hemisferio
  if (hemis === 'sur') return d.getMonth() === 2 && d.getDate() <= 14 ? 1 : 0
  return (d.getMonth() === 7 && d.getDate() >= 25) || (d.getMonth() === 8 && d.getDate() <= 10) ? 1 : 0
}
const temporada = (pais: string, d: Date) => {
  const hemis = PAISES_DEMO[pais].hemisferio
  const verano = hemis === 'sur' ? [11, 0, 1] : [5, 6, 7]
  const invierno = hemis === 'sur' ? [5, 6, 7] : [11, 0, 1]
  if (verano.includes(d.getMonth()) || d.getMonth() === 11) return 'alta'
  if (invierno.includes(d.getMonth())) return 'baja'
  return 'media'
}
const tempEstacional = (s: SerieDemo, d: Date) => {
  const pico = PAISES_DEMO[s.pais].hemisferio === 'sur' ? 15 : 196
  return r2(s.tempBase + s.tempAmp * Math.cos((2 * Math.PI * (doy(d) - pico)) / 365))
}
const fxDia = (s: SerieDemo, i: number) => r2(PAISES_DEMO[s.pais].fxRef * (1 + 0.01 * Math.sin(i / 9)))
const fuelDia = (s: SerieDemo, i: number, total: number) =>
  r2(PAISES_DEMO[s.pais].fuelRef * (1 + (0.05 * i) / total + 0.01 * Math.sin(i / 5)))

/** Factor de demanda: mismos drivers que el generador del backend (compacto). */
function factorDemanda(s: SerieDemo, d: Date, ctx: {
  promo: number; descuento: number; campaña: number; clima: string; competidor: number
  temperatura: number; precio: number; precioComp: number; trafRel: number; fx: number; fuel: number
}): number {
  const dow = d.getDay()
  const dowF = dow === 0 || dow === 6 ? (s.categoria === 'bebidas' ? 1.2 : 1.1) : dow === 1 ? 0.9 : 1
  const precioF = Math.pow(ctx.precio / s.precio0, -s.elas)
  const compPrecioF = Math.pow(ctx.precio / ctx.precioComp, -0.8)
  const climaF = s.categoria === 'bebidas' ? (ctx.clima === 'soleado' ? 1.22 : ctx.clima === 'lluvia' ? 0.82 : 1) : 1.02
  const tempF = 1 + s.tempSens * (ctx.temperatura - 20)
  const fer = esFeriado(s.pais, d) ? 1.2 : 1
  const visp = vispera(s.pais, d) ? 1.15 : 1
  const fxF = Math.pow(ctx.fx / PAISES_DEMO[s.pais].fxRef, -0.5 * s.importado)
  const fuelF = Math.pow(ctx.fuel / PAISES_DEMO[s.pais].fuelRef, -0.05)
  const pagoF = diaPago(s.pais, d) ? 1.1 : 1
  const escolarF = 1 + s.escolar * (inicioClases(s.pais, d) ? 1 : 0)
  const tempCom = { alta: 1.06, media: 1, baja: 0.95 }[temporada(s.pais, d)] ?? 1
  const confF = 0.85 + 0.15 * s.conf
  return (
    dowF * precioF * compPrecioF * climaF * tempF * fer * visp * fxF * fuelF * pagoF * escolarF * tempCom * confF *
    (ctx.promo ? 1.12 : 1) * (ctx.campaña ? 1.18 : 1) * (ctx.competidor ? 0.85 : 1) * ctx.trafRel
  )
}

/** Genera filas sintéticas con señal (semanal + drivers + mini-simulación de stock). */
function filasDemo(dias = 70): AutoRow[] {
  const rows: AutoRow[] = []
  const inicio = new Date('2024-01-01')
  for (const s of SERIES_DEMO) {
    const media = s.base * 1.05
    const reorden = media * s.lead
    const online = PAISES_DEMO[s.pais].online
    const retRate = s.perecedero ? 0.05 : 0.025
    const spoil = s.perecedero ? 0.03 : 0
    let stock = s.base * 4
    let demPrev = media
    for (let i = 0; i < dias; i++) {
      const d = new Date(inicio)
      d.setDate(d.getDate() + i)
      const finde = d.getDay() === 0 || d.getDay() === 6 ? 0.2 : 0
      const promo = i % 9 < 4 ? 1 : 0
      const descuento = promo ? [10, 15, 20, 25][i % 4] : 0
      const campaña = i % 11 === 0 ? 1 : 0
      const clima = CLIMAS_DEMO[i % 3]
      const competidor = i % 8 === 0 ? 1 : 0
      const temperatura = tempEstacional(s, d)
      const precio = r2(s.precio0 * (1 - descuento / 100))
      const precioComp = r2(s.precio0 * (0.95 + 0.1 * Math.sin(i)))
      const trafico = Math.round(s.traficoBase * (1 + finde) * (clima === 'soleado' ? 1.1 : 1))
      const fx = fxDia(s, i)
      const fuel = fuelDia(s, i, dias)
      const factor = factorDemanda(s, d, {
        promo, descuento, campaña, clima, competidor, temperatura, precio, precioComp,
        trafRel: trafico / s.traficoBase, fx, fuel,
      })
      const demanda = Math.max(0, Math.round(s.base * (1 + 0.25 * Math.sin((2 * Math.PI * i) / 7)) * factor))
      // Mini-simulación de inventario (genera las solo-pasado coherentes).
      const stockInicial = stock
      const atendida = Math.min(demanda, stock)
      const pendientes = Math.max(0, demanda - stock)
      stock -= atendida
      const mermas = s.perecedero ? Math.round(stock * spoil) : 0
      stock -= mermas
      const devoluciones = Math.round(demPrev * retRate)
      stock += devoluciones
      let recepciones = 0
      if (stock < reorden) {
        recepciones = Math.round(reorden * 1.5 + s.moq)
        stock += recepciones
      }
      const diasCobertura = r2(stock / Math.max(media, 1))
      const rotacion = Math.round((atendida / Math.max(stockInicial, 1)) * 1000) / 1000
      const ventasOnline = Math.round(demanda * online)
      demPrev = demanda
      rows.push({
        fecha: d.toISOString().slice(0, 10),
        almacen: s.almacen,
        sku: s.sku,
        unidades_vendidas: demanda,
        precio,
        en_promo: promo,
        descuento_pct: descuento,
        es_feriado: esFeriado(s.pais, d),
        vispera_feriado: vispera(s.pais, d),
        campaña_mkt: campaña,
        temperatura,
        clima,
        evento_cercano: 'ninguno',
        categoria: s.categoria,
        segmento_almacen: s.segmento,
        proveedor: s.proveedor,
        pais: s.pais,
        moneda: PAISES_DEMO[s.pais].moneda,
        tipo_cambio_usd: fx,
        festividad_local: festividad(s.pais, d),
        temporada: temporada(s.pais, d),
        dia_pago_local: diaPago(s.pais, d),
        inicio_clases: inicioClases(s.pais, d),
        perecedero: s.perecedero,
        vida_util_dias: s.vidaUtil,
        marca: s.marca,
        unidad_medida: s.unidad,
        peso_kg: s.peso,
        costo_flete: s.flete,
        precio_combustible: fuel,
        confiabilidad_proveedor: s.conf,
        trafico_tienda: trafico,
        transacciones: Math.round(trafico * 0.6),
        competidor_promo: competidor,
        precio_competidor: precioComp,
        quiebre_stock_prev: 0,
        ventas_online: ventasOnline,
        devoluciones,
        recepciones,
        stock_inicial_dia: r2(stockInicial),
        dias_cobertura: diasCobertura,
        rotacion_inventario: rotacion,
        pedidos_pendientes: pendientes,
        lead_time_real: s.lead,
      })
    }
  }
  return rows
}

/** Items de inventario/compras: una fila por serie con datos del proveedor real. */
function itemsDemo(conCobertura: boolean): Record<string, unknown>[] {
  return SERIES_DEMO.map((s) => {
    const it: Record<string, unknown> = {
      almacen: s.almacen,
      sku: s.sku,
      current_stock: Math.round(s.base * 3),
      lead_time_days: s.lead,
      proveedor: s.proveedor,
      moq: s.moq,
      costo_unitario: s.costo,
    }
    if (conCobertura) it.target_coverage_days = 14
    return it
  })
}

/** Bloque `future`: features conocidas a futuro ya fijadas para el horizonte (promo
 *  planificada en los días 3-6). Sin esto, el pronóstico asume precio/promo = 0. */
function futureDemo(dias = 70, horizon = 7): AutoRow[] {
  const out: AutoRow[] = []
  const inicio = new Date('2024-01-01')
  for (const s of SERIES_DEMO) {
    for (let k = 0; k < horizon; k++) {
      const d = new Date(inicio)
      d.setDate(d.getDate() + dias + k)
      const promo = k >= 2 && k <= 5 ? 1 : 0
      const descuento = promo ? 20 : 0
      const i = dias + k
      out.push({
        fecha: d.toISOString().slice(0, 10),
        almacen: s.almacen,
        sku: s.sku,
        precio: r2(s.precio0 * (1 - descuento / 100)),
        en_promo: promo,
        descuento_pct: descuento,
        es_feriado: esFeriado(s.pais, d),
        vispera_feriado: vispera(s.pais, d),
        campaña_mkt: k === 0 ? 1 : 0,
        temperatura: tempEstacional(s, d),
        clima: CLIMAS_DEMO[i % 3],
        evento_cercano: 'ninguno',
        categoria: s.categoria,
        segmento_almacen: s.segmento,
        proveedor: s.proveedor,
        pais: s.pais,
        moneda: PAISES_DEMO[s.pais].moneda,
        tipo_cambio_usd: fxDia(s, i),
        festividad_local: festividad(s.pais, d),
        temporada: temporada(s.pais, d),
        dia_pago_local: diaPago(s.pais, d),
        inicio_clases: inicioClases(s.pais, d),
        perecedero: s.perecedero,
        vida_util_dias: s.vidaUtil,
        marca: s.marca,
        unidad_medida: s.unidad,
        peso_kg: s.peso,
        costo_flete: s.flete,
        precio_combustible: fuelDia(s, i, dias + horizon),
        confiabilidad_proveedor: s.conf,
      })
    }
  }
  return out
}

/** Cuerpo de ejemplo por dominio (editable en pantalla). */
function ejemplo(domain: AutoDomain): unknown {
  const rows = filasDemo()
  if (domain === 'sales') {
    return { schema: SCHEMA_DEMO, horizon: 7, granularity: 'day', rows, future: futureDemo() }
  }
  if (domain === 'inventory') {
    return { schema: SCHEMA_DEMO, high_demand_quantile: 0.75, rows, items: itemsDemo(false) }
  }
  return { schema: SCHEMA_DEMO, rows, items: itemsDemo(true) }
}

function filasResultado(domain: AutoDomain, data: AnyResponse): AutoRow[] {
  if (domain === 'sales') return (data as AutoSalesResponse).forecast
  if (domain === 'inventory') return (data as AutoInventoryResponse).alerts
  return (data as AutoPurchasesResponse).recommendation
}

export function AutoPage() {
  const [domain, setDomain] = useState<AutoDomain>('sales')
  const [texto, setTexto] = useState<string>(() => JSON.stringify(ejemplo('sales'), null, 2))
  const [data, setData] = useState<AnyResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Vista previa del esquema declarado (se intenta parsear en vivo, sin romper).
  const schemaPreview = useMemo<AutoSchemaSpec | null>(() => {
    try {
      const body = JSON.parse(texto) as { schema?: AutoSchemaSpec }
      return body.schema ?? null
    } catch {
      return null
    }
  }, [texto])

  const cambiarDominio = (d: AutoDomain) => {
    setDomain(d)
    setTexto(JSON.stringify(ejemplo(d), null, 2))
    setData(null)
    setError(null)
    setParseError(null)
  }

  const cargarEjemplo = () => {
    setTexto(JSON.stringify(ejemplo(domain), null, 2))
    setData(null)
    setError(null)
    setParseError(null)
  }

  const onArchivo = async (file: File) => {
    const t = await file.text()
    setTexto(t)
    setData(null)
    setError(null)
    setParseError(null)
  }

  const guardarBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  // Descarga el cuerpo actual como plantilla .json (columnas libres).
  const descargarPlantillaJson = () => guardarBlob(new Blob([texto], { type: 'application/json' }), `plantilla_auto_${domain}.json`)

  // Cuerpo actual parseado (esquema + config) para las acciones de Excel.
  const cuerpoActual = (): Record<string, unknown> | null => {
    try {
      return JSON.parse(texto) as Record<string, unknown>
    } catch {
      setParseError('El texto no es un JSON válido; corrígelo para usar el canal Excel.')
      return null
    }
  }

  // Descarga la plantilla EXCEL a la medida del esquema declarado (columnas exactas).
  const descargarPlantillaExcel = async () => {
    setParseError(null)
    const cuerpo = cuerpoActual()
    const schema = cuerpo?.schema as AutoSchemaSpec | undefined
    if (!schema?.target) {
      setParseError('Declara un esquema con al menos «target» para generar la plantilla Excel.')
      return
    }
    try {
      const { blob, filename } = await downloadAutoTemplate(domain, schema)
      guardarBlob(blob, filename)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
    }
  }

  // Sube un Excel (hoja «datos» [+ «items»]); el esquema/config salen del editor de pantalla.
  const cargarExcel = async (file: File) => {
    setError(null)
    setParseError(null)
    const cuerpo = cuerpoActual()
    const schema = cuerpo?.schema as AutoSchemaSpec | undefined
    if (!schema?.target) {
      setParseError('Declara un esquema en el editor antes de subir el Excel.')
      return
    }
    const fields: Record<string, string | number> = { schema: JSON.stringify(schema) }
    if (domain === 'sales') {
      fields.horizon = (cuerpo?.horizon as number) ?? 7
      fields.granularity = (cuerpo?.granularity as string) ?? 'day'
      if (cuerpo?.future) fields.future = JSON.stringify(cuerpo.future)
    } else {
      if (cuerpo?.items) fields.items = JSON.stringify(cuerpo.items)
      if (domain === 'inventory' && cuerpo?.high_demand_quantile != null) {
        fields.high_demand_quantile = cuerpo.high_demand_quantile as number
      }
    }
    setBusy(true)
    setData(null)
    try {
      const res = await uploadAutoExcel<AnyResponse>(domain, file, fields)
      setData(res)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
      else setParseError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const predecir = async () => {
    setError(null)
    setParseError(null)
    let body: unknown
    try {
      body = JSON.parse(texto)
    } catch {
      setParseError('El texto no es un JSON válido. Revisa las comas y las llaves.')
      return
    }
    setBusy(true)
    setData(null)
    try {
      const res =
        domain === 'sales'
          ? await postAutoSales(body as never)
          : domain === 'inventory'
            ? await postAutoInventory(body as never)
            : await postAutoPurchases(body as never)
      setData(res)
    } catch (e) {
      if (e instanceof ApiError) setError(e)
      else setParseError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <ModuleHeader view="auto" />

      {/* PASO 1 — Elige qué quieres y declara tu esquema + datos. */}
      <StepSection
        step={1}
        title="Tu pregunta y tus datos"
        accentChip={ACCENT.chip}
        description="Elige el tipo de análisis y declara tu esquema (qué predecir, fecha, series y columnas extra). Puedes descargar una plantilla Excel a la medida de tu esquema, llenarla y subirla, o editar el JSON aquí mismo."
      >
        <div className="flex flex-wrap gap-2">
          {(Object.keys(DOMAIN_LABEL) as AutoDomain[]).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => cambiarDominio(d)}
              className={`badge ${domain === d ? ACCENT.solid : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              {DOMAIN_LABEL[d]}
            </button>
          ))}
        </div>

        {schemaPreview && (
          <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-600">
            <p>
              Predecir <span className="font-semibold text-slate-800">{schemaPreview.target}</span>
              {schemaPreview.date && (
                <> · fecha <span className="font-mono">{schemaPreview.date}</span></>
              )}
              {schemaPreview.series_keys.length > 0 && (
                <> · por <span className="font-mono">{schemaPreview.series_keys.join(' × ')}</span></>
              )}
            </p>
            {schemaPreview.features.length > 0 && (
              <p className="mt-1 flex flex-wrap gap-1">
                {schemaPreview.features.map((f) => (
                  <span key={f.name} className={`badge ${ACCENT.badge}`}>
                    {f.name} · {f.type === 'numeric' ? 'núm.' : 'categ.'}
                    {f.type === 'numeric' && f.known_future === false ? ' (solo pasado)' : ''}
                  </span>
                ))}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={`btn ${ACCENT.solid}`} onClick={() => void descargarPlantillaExcel()} disabled={busy}>
            Descargar plantilla Excel
          </button>
          <label className={`badge cursor-pointer ${ACCENT.badge}`}>
            Cargar Excel
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void cargarExcel(f)
                e.target.value = ''
              }}
            />
          </label>
          <label className={`badge cursor-pointer ${ACCENT.badge}`}>
            Cargar JSON
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onArchivo(f)
                e.target.value = ''
              }}
            />
          </label>
          <button type="button" className="badge bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={cargarEjemplo}>
            Restaurar ejemplo
          </button>
          <button type="button" className="badge bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={descargarPlantillaJson}>
            Descargar JSON
          </button>
        </div>

        <textarea
          className="input min-h-[18rem] w-full font-mono text-xs"
          spellCheck={false}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          disabled={busy}
          aria-label="Cuerpo de la petición (JSON)"
        />
        {parseError && (
          <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
            {parseError}
          </p>
        )}
      </StepSection>

      {/* PASO 2 — Entrena al momento y predice. */}
      <StepSection
        step={2}
        title="Entrena el mejor modelo y predice"
        accentChip={ACCENT.chip}
        description="El sistema prueba varios algoritmos sobre tus datos, elige el ganador con validación honesta y predice — todo en una llamada."
      >
        <button type="button" className={`btn ${ACCENT.solid}`} onClick={predecir} disabled={busy}>
          {busy ? 'Entrenando y prediciendo…' : 'Entrenar y predecir'}
        </button>
      </StepSection>

      {error && <ErrorPanel error={error} />}

      {!data && !busy && !error && (
        <EmptyState
          icon={Wand2}
          title="Aún no hay resultado"
          message="Declara tu esquema y datos, y pulsa «Entrenar y predecir». El sistema entrenará el mejor modelo para tus columnas y te mostrará el resultado y qué tan exacto fue."
        />
      )}

      {data && <ResultSection domain={domain} data={data} />}
    </div>
  )
}

function ResultSection({ domain, data }: { domain: AutoDomain; data: AnyResponse }) {
  const rows = filasResultado(domain, data)
  const cols = useMemo(() => columnasDinamicas(rows), [rows])
  const candidatos = data.training.candidates

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
      <TrainingCard training={data.training} accentSolid={ACCENT.solid} accentBadge={ACCENT.badge} />

      {rows.length > 0 ? (
        <ResultTable columns={cols} rows={rows} />
      ) : (
        <p className="text-sm text-slate-500">El modelo no produjo filas para esta consulta.</p>
      )}

      <TechnicalDetails>
        <p>
          Firma del esquema: <span className="font-mono text-slate-700">{data.training.schema_signature}</span>
        </p>
        {Object.keys(data.training.honest_metrics).length > 0 && (
          <p>
            Métricas completas:{' '}
            {Object.entries(data.training.honest_metrics)
              .map(([k, v]) => `${k}=${fmtNum(v)}`)
              .join(' · ')}
          </p>
        )}
        {data.training.threshold_probability != null && (
          <p>Umbral de probabilidad: {fmtNum(data.training.threshold_probability)}</p>
        )}
        {candidatos && (
          <p>
            Candidatos (MAE de validación):{' '}
            {Object.entries(candidatos)
              .map(([k, v]) => `${k}=${fmtNum(v)}`)
              .join(' · ')}
          </p>
        )}
      </TechnicalDetails>
    </section>
  )
}
