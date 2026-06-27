/**
 * Endpoints SPC tipados. Una función por operación del contrato.
 *
 * Las predicciones devuelven `{ status, data }`: status 200 = resultado del
 * dominio; status 202 = `JobAccepted` (modo lote). El caller (usePrediction)
 * decide si hay que hacer polling.
 */
import { getBlob, getJson, postFile, postJson } from './client'
import type {
  CatalogResponse,
  Domain,
  InventoryRequest,
  InventoryResponse,
  JobAccepted,
  PurchasesRequest,
  PurchasesResponse,
  SalesRequest,
  SalesResponse,
  ServingStatus,
  TrainingAccepted,
  TrainingJobStatus,
  TrainingPhase,
  TrainingResult,
  TrainingSource,
} from './types'

// Una predicción puede volver como resultado (200) o como comprobante de lote (202).
export type PredictResult<T> =
  | { mode: 'online'; data: T }
  | { mode: 'batch'; job: JobAccepted }

async function predict<TReq, TRes>(
  path: string,
  body: TReq,
): Promise<PredictResult<TRes>> {
  const { status, data } = await postJson<TRes | JobAccepted>(path, body)
  if (status === 202) return { mode: 'batch', job: data as JobAccepted }
  return { mode: 'online', data: data as TRes }
}

export const postSales = (req: SalesRequest) =>
  predict<SalesRequest, SalesResponse>('/sales', req)

export const postPurchases = (req: PurchasesRequest) =>
  predict<PurchasesRequest, PurchasesResponse>('/purchases', req)

export const postInventory = (req: InventoryRequest) =>
  predict<InventoryRequest, InventoryResponse>('/inventory', req)

// --- Canal Excel ---
// `fields` lleva la configuración de pantalla cuando aplica: en Ventas, el archivo es
// solo datos (history) y `granularity`/`horizon` viajan como campos de formulario, única
// fuente de la configuración del pronóstico (ADR-0022).
export async function uploadExcel<TRes>(
  domain: Domain,
  file: File,
  fields?: Record<string, string | number>,
): Promise<PredictResult<TRes>> {
  const { status, data } = await postFile<TRes | JobAccepted>(`/${domain}/excel`, file, fields)
  if (status === 202) return { mode: 'batch', job: data as JobAccepted }
  return { mode: 'online', data: data as TRes }
}

export function downloadTemplate(domain: Domain) {
  return getBlob(`/${domain}/template`)
}

// --- Modo lote ---
/**
 * Pide el resultado de un job. Devuelve `pending: true` mientras el backend
 * responde 202 (aún en cola/corriendo); `done` con el cuerpo del dominio al
 * terminar. Un error de negocio (400/500) sale como `ApiError` desde el cliente.
 */
export async function getJobResult<T>(
  jobId: string,
): Promise<{ pending: true } | { pending: false; data: T }> {
  const { status, data } = await getJson<T>(`/jobs/${jobId}/result`)
  if (status === 202) return { pending: true }
  return { pending: false, data }
}

// --- Catálogo ---
export async function getCatalog(): Promise<CatalogResponse> {
  const { data } = await getJson<CatalogResponse>('/catalog')
  return data
}

// --- Entrenamiento por cliente bajo demanda (ADR-0013) ---
/** Sube el Excel de SALES y dispara un entrenamiento LOCAL (opt-in). Devuelve el job. */
export async function startSalesTraining(
  file: File,
  source: TrainingSource = 'merged',
): Promise<TrainingAccepted> {
  const { data } = await postFile<TrainingAccepted>(
    `/training/sales/excel?source=${source}`,
    file,
  )
  return data
}

/**
 * Pide el resultado del entrenamiento. Mientras el backend responde 202 devuelve
 * `pending: true` con la fase honesta; al terminar, `done` con la comparación.
 */
export async function getTrainingResult(
  jobId: string,
): Promise<
  | { pending: true; phase: TrainingPhase | null }
  | { pending: false; data: TrainingResult }
> {
  const { status, data } = await getJson<TrainingResult | TrainingJobStatus>(
    `/training/jobs/${jobId}/result`,
  )
  if (status === 202) {
    return { pending: true, phase: (data as TrainingJobStatus).phase ?? null }
  }
  return { pending: false, data: data as TrainingResult }
}

/** Estado de adopción/serving del modelo por cliente para el client_id actual. */
export async function getServingStatus(): Promise<ServingStatus> {
  const { data } = await getJson<ServingStatus>('/training/sales/status')
  return data
}

/** Activa/desactiva servir con el modelo por cliente (switch reversible). */
export async function setServing(enabled: boolean): Promise<ServingStatus> {
  const { data } = await postJson<ServingStatus>('/training/sales/serving', { enabled })
  return data
}
