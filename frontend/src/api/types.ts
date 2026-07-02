/**
 * Tipos TypeScript espejo del contrato SPC v1.0.1.
 *
 * Los nombres son los del contrato (en inglés), tal como los exponen los esquemas
 * Pydantic del backend (`src/spc/api/schemas/`). No se traducen: el contrato es la
 * frontera. La UI muestra etiquetas en español, pero los datos viajan con estos
 * nombres.
 */

export type Domain = 'sales' | 'purchases' | 'inventory'

export type Granularity = 'day' | 'week' | 'month'

// --- Bloque `history` compartido (comunes.py: HistoricoItem) ---
export interface HistoryItem {
  date: string // ISO YYYY-MM-DD
  store_id: string
  product_id: string
  units_sold: number // >= 0
  on_promotion?: number // int >= 0, def 0
  transactions?: number | null // >= 0
  event_active?: boolean | null
}

// --- SALES ---
export interface SalesRequest {
  granularity?: Granularity // def "day"
  horizon: number // 1..365
  history: HistoryItem[]
}

export interface ForecastItem {
  date: string
  store_id: string
  product_id: string
  forecast_demand: number
  interval_80?: [number, number] | null // diferido: la API lo omite hoy
}

export interface SalesMetadata {
  scale: string
  internal_transform: string
}

export interface SalesResponse {
  field: 'sales'
  model: string
  forecast: ForecastItem[]
  metadata: SalesMetadata
}

// --- PURCHASES ---
export interface ReplenishmentParam {
  store_id: string
  product_id: string
  current_stock: number // >= 0
  lead_time_days: number // > 0
  target_coverage_days: number // > 0
}

export interface PurchasesRequest {
  history: HistoryItem[]
  replenishment_params: ReplenishmentParam[]
}

export interface RecommendationItem {
  store_id: string
  product_id: string
  expected_demand_horizon: number
  reorder_point: number
  replenishment_quantity: number
  justification: string
}

export interface PurchasesMetadata {
  assumption: string
  policy?: string
}

export interface PurchasesResponse {
  field: 'purchases'
  recommendation: RecommendationItem[]
  metadata: PurchasesMetadata
}

// --- INVENTORY ---
export interface InventoryStatusItem {
  store_id: string
  product_id: string
  current_stock: number // >= 0
  lead_time_days?: number | null // > 0, opcional
}

export interface InventoryRequest {
  history: HistoryItem[]
  inventory_status: InventoryStatusItem[]
}

export interface AlertItem {
  store_id: string
  product_id: string
  demand_class: 'high' | 'low'
  high_demand_probability: number // 0..1
  stockout_risk: boolean
  recommended_stock: number
  safety_stock: number
  store_segment: number
}

export interface InventoryMetadata {
  threshold: string
  probability_threshold?: number | null
}

export interface InventoryResponse {
  field: 'inventory'
  alerts: AlertItem[]
  metadata: InventoryMetadata
}

// Mapas dominio -> request/response, útiles para genéricos.
export interface DomainRequest {
  sales: SalesRequest
  purchases: PurchasesRequest
  inventory: InventoryRequest
}
export interface DomainResponse {
  sales: SalesResponse
  purchases: PurchasesResponse
  inventory: InventoryResponse
}

// --- Predicción agnóstica auto-entrenada (agnostico.py, ADR-0023) ---
// El cliente declara su propio esquema y trae columnas arbitrarias; el sistema entrena el
// algoritmo ganador al vuelo. Las filas/salidas son registros de columnas libres.
export type AutoFeatureType = 'numeric' | 'categorical'

export interface AutoFeatureSpec {
  name: string
  type: AutoFeatureType
  known_future?: boolean // def true
}

export interface AutoSchemaSpec {
  target: string
  date?: string | null
  series_keys: string[]
  features: AutoFeatureSpec[]
}

/** Veredicto «quédate-con-el-mejor»: candidato recién entrenado vs campeón persistido. */
export interface SeleccionModelo {
  comparado: boolean
  metrica: string // p. ej. "WAPE" | "ROC_AUC"
  mejor_es: 'mayor' | 'menor'
  candidato: number | null
  campeon: number | null
  adoptado: 'candidato' | 'campeon'
}

/** Resumen honesto del modelo entrenado al vuelo (común a las tres respuestas). */
export interface AutoTrainingInfo {
  winner_algorithm: string
  trained_rows: number
  honest_metrics: Record<string, number>
  candidates?: Record<string, number> | null
  reused_cached_model: boolean
  schema_signature: string
  threshold_probability?: number | null
  seleccion?: SeleccionModelo | null
}

export type AutoRow = Record<string, string | number | boolean | null>

export interface AutoSalesRequest {
  schema: AutoSchemaSpec
  horizon: number
  granularity?: Granularity
  rows: AutoRow[]
  future?: AutoRow[] | null
}
export interface AutoSalesResponse {
  field: 'sales'
  training: AutoTrainingInfo
  forecast: AutoRow[]
  metadata: Record<string, unknown>
}

export interface AutoInventoryRequest {
  schema: AutoSchemaSpec
  rows: AutoRow[]
  items: AutoRow[]
  high_demand_quantile?: number
}
export interface AutoInventoryResponse {
  field: 'inventory'
  training: AutoTrainingInfo
  alerts: AutoRow[]
  metadata: Record<string, unknown>
}

export interface AutoPurchasesRequest {
  schema: AutoSchemaSpec
  rows: AutoRow[]
  items: AutoRow[]
}
export interface AutoPurchasesResponse {
  field: 'purchases'
  training: AutoTrainingInfo
  recommendation: AutoRow[]
  metadata: Record<string, unknown>
}

// --- Tablas de entrada (carga manual / plantilla), con etiquetas en español ---
// Derivadas de los esquemas nested del contrato (ADR-0020): la UI arma la tabla editable
// y los encabezados a partir de esto, sin hardcodear columnas ni etiquetas.
export interface CatalogColumn {
  name: string // nombre canónico (en inglés), igual que la API
  label: string // etiqueta en español
  type: string // tipo legible (int | float | str | date | bool …)
  required: boolean
  help?: string | null
  default?: number | string | null // prefill editable (sale de la política, ADR-0010); ausente si no aplica
}

export interface InputTable {
  name: string // contenedor en la petición: "history" | "replenishment_params" | "inventory_status"
  label: string // etiqueta en español
  description?: string | null
  columns: CatalogColumn[]
}

// --- Opciones de consulta de la UI (query_options): R1 tipologías, R2 dimensiones ---
// Derivadas del contrato y de las agregaciones del servicio (no del motor de ML). La UI
// las consume para no hardcodear ninguna opción (ADR-0018).
export interface ForecastTypology {
  name: string // p. ej. "time_series" | "by_dimension"
  label: string // etiqueta en español
  requires_dimension: boolean // R1 → ¿activa el selector de dimensión (R2)?
  description: string
}

export interface ForecastDimension {
  name: string // columna del contrato: "store_id" | "product_id"
  label: string // etiqueta en español
  description?: string | null
}

export interface GranularityOption {
  name: Granularity // "day" | "week" | "month"
  label: string // "Día" | "Semana" | "Mes"
}

export interface HorizonRange {
  min: number
  max: number
  default: number
  unit: string // "periods"
}

export interface QueryOptions {
  typologies: ForecastTypology[]
  dimensions: ForecastDimension[]
  granularities: GranularityOption[]
  horizon: HorizonRange
}

// --- 3×3 por dominio (motor_3x3.py, ADR-0024/0025) ---
// Un formato fijo por dominio que alimenta los tres modelos, entrenados en el momento.
// La respuesta combina los tres bloques (regresión, clasificación, clustering).
export type V2Domain = 'ventas' | 'compras' | 'almacen'

/** Fila de pronóstico: claves de serie (id_tienda/sku o id_proveedor/sku) + fecha + valor. */
export type V2PrediccionItem = Record<string, string | number>

export interface V2Regresion {
  objetivo: string
  modelo_ganador: string
  n_filas_entrenamiento: number
  metricas_honestas: Record<string, number>
  candidatos: Record<string, number> | string[]
  horizonte: number
  prediccion: V2PrediccionItem[]
}

/** Alerta por serie: claves de serie + clase (0/1) + probabilidad. */
export type V2Alerta = Record<string, string | number>

export interface V2Clasificacion {
  etiqueta: string
  definicion: string
  modelo_ganador: string
  umbral: number
  prevalencia: number
  metricas_honestas: Record<string, number>
  alertas: V2Alerta[]
}

/** Segmento de una entidad: su clave + número de segmento + etiqueta narrativa. */
export type V2Segmento = Record<string, string | number>

/** Un grupo del clustering con sus características promedio (centroides). */
export interface V2Grupo {
  segmento: number
  etiqueta: string
  n: number
  caracteristicas: Record<string, number>
}

export interface V2Clustering {
  algoritmo: string
  entidad?: string
  k: number
  silueta: number | null
  curva_silueta?: Record<string, number>
  segmentos: V2Segmento[]
  grupos?: V2Grupo[]
}

/** KPIs de inventario derivados del pronóstico de demanda (solo ALMACÉN). */
export interface V2IndicadorInventario {
  id_tienda: string
  sku: string
  demanda_diaria_prevista: number
  stock_actual: number
  stock_seguridad: number
  punto_reposicion: number
  dias_cobertura_proyectada: number | null
  alerta_reposicion: boolean
}

export interface V2Response {
  dominio: string
  formato: string
  n_filas: number
  regresion: V2Regresion
  clasificacion: V2Clasificacion
  clustering: V2Clustering
  indicadores_inventario?: V2IndicadorInventario[]
  nota: string
}

/** Resultado del reentrenamiento con histórico + nuevos (POST /v2/{dominio}/entrenar, ADR-0027). */
export interface V2VersionEntrenada {
  task: string
  version: number
  algorithm: string | null
  metrics: Record<string, number | null> | null
  is_serving: boolean
  storage_uri: string | null
}

export interface V2Reentrenamiento {
  dominio: string
  corpus_filas: number
  versiones: V2VersionEntrenada[]
  training_run_id: number
}

/** Una versión del registro de modelos (GET /v2/{dominio}/modelos, ADR-0027). */
export interface V2Modelo {
  id: number
  task: string
  version: number
  algorithm: string | null
  metrics: Record<string, number | null> | null
  status: string
  is_serving: boolean
  trained_rows: number
  trained_at: string
}

export interface V2ListaModelos {
  dominio: string
  modelos: V2Modelo[]
}

/** Diccionario de variables del dominio (GET /v2/{dominio}/esquema). */
export interface V2Columna {
  nombre: string
  tipo: string
  rol: string
  descripcion: string
  uso: string
  formula: string
  obligatoria: boolean
  se_calcula_sola: boolean
  ejemplo: string | number | boolean | null
}

export interface V2Esquema {
  dominio: string
  formato: string
  columnas: V2Columna[]
  que_se_predice: {
    regresion: { objetivo: string; explicacion: string }
    clasificacion: { alerta: string; cuando: string; explicacion: string }
    clustering: { agrupa: string; grupos_fijos: number | null; explicacion: string }
  }
}

// --- Error uniforme (comunes.py: ErrorResponse) ---
export interface ErrorDetail {
  field: string
  problem: string
}

export interface ErrorBody {
  type: string
  message: string
  details?: ErrorDetail[] | null
}

export interface ErrorEnvelope {
  error: ErrorBody
}
