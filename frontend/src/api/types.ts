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

// --- Modo lote (jobs.py) ---
export type JobStatusValue = 'queued' | 'running' | 'done' | 'error'

export interface JobAccepted {
  job_id: string
  status: JobStatusValue
  mode: 'batch'
  domain: Domain
  rows: number
  status_url: string
  result_url: string
}

// --- Entrenamiento por cliente bajo demanda (training.py, ADR-0013) ---
export type TrainingPhase = 'validating' | 'training' | 'evaluating'
export type TrainingOutcome = 'adopted' | 'not_adopted' | 'insufficient_data' | 'inconclusive'
export type TrainingSource = 'merged' | 'excel' | 'corpus'

export interface TrainingAccepted {
  job_id: string
  status: JobStatusValue
  domain: 'sales'
  client_id: string
  source: string
  status_url: string
  result_url: string
}

export interface TrainingJobStatus {
  job_id: string
  status: JobStatusValue
  phase?: TrainingPhase | null
  domain: string
  client_id: string
  source: string
  created_at: string
  finished_at?: string | null
  result_url: string
}

export interface MetricTriple {
  WAPE: number
  MAE: number
  RMSE: number
}

export interface BaselineMetric extends MetricTriple {
  name: string
}

/** Resultado del experimento medido (comparación honesta + veredicto de adopción). */
export interface TrainingResult {
  domain: 'sales'
  outcome: TrainingOutcome
  message: string
  metric?: string
  window_days?: number
  candidate?: MetricTriple
  frozen?: MetricTriple
  baseline?: BaselineMetric | null
  improvement_wape_points?: number
  beats_frozen?: boolean
  beats_baseline?: boolean
  model_version?: string
  missing?: string[]
}

export interface ServingStatus {
  domain: 'sales'
  client_id: string
  has_client_model: boolean
  serving_client_model: boolean
  adopted_version?: number | null
  model_version?: string | null
  trained_versions: number[]
  last_comparison?: TrainingResult | null
}

// --- Catálogo (catalog.py) ---
export type AvailabilityStatus = 'available' | 'planned'

export interface Availability {
  name: string
  status: AvailabilityStatus
  description: string
}

export interface CatalogField {
  name: string
  type: string
  required: boolean
  description?: string | null
}

export interface CatalogInput {
  name: string
  type: string
  required: boolean
  description?: string | null
}

export interface OutputGroup {
  group: 'root' | 'items' | 'metadata'
  container: string | null
  fields: CatalogField[]
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

export interface DomainCatalog {
  domain: Domain
  endpoint: string
  has_model: boolean
  summary: string
  description: string
  contract_reference: string
  inputs: CatalogInput[]
  input_tables: InputTable[] // tablas de entrada con etiquetas en español (ADR-0020)
  outputs: OutputGroup[]
  query_options?: QueryOptions | null // presente solo en dominios que lo exponen (hoy sales)
  notes: string[]
  pending_policy: string[]
}

export interface CatalogResponse {
  contract_version: string
  channels: Availability[]
  modes: Availability[]
  domains: DomainCatalog[]
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
