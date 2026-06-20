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

export interface DomainCatalog {
  domain: Domain
  endpoint: string
  has_model: boolean
  summary: string
  description: string
  contract_reference: string
  inputs: CatalogInput[]
  outputs: OutputGroup[]
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
