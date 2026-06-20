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
export async function uploadExcel<TRes>(
  domain: Domain,
  file: File,
): Promise<PredictResult<TRes>> {
  const { status, data } = await postFile<TRes | JobAccepted>(`/${domain}/excel`, file)
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
