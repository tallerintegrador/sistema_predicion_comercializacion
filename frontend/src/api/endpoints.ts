/**
 * Endpoints SPC tipados. Una función por operación.
 *
 * Dos motores, ambos entrenados en el momento (sin artefactos):
 * - **3×3** (`/v2/*`): un formato fijo por dominio (ventas/compras/almacén) que devuelve
 *   los tres modelos (regresión, clasificación, clustering) en una sola respuesta.
 * - **Agnóstico** (`/auto/*`): el cliente declara su esquema y trae columnas libres.
 */
import { getJson, postFile, postJson, postJsonBlob } from './client'
import type {
  AutoInventoryRequest,
  AutoInventoryResponse,
  AutoPurchasesRequest,
  AutoPurchasesResponse,
  AutoSalesRequest,
  AutoSalesResponse,
  AutoSchemaSpec,
  AutoRow,
  V2Domain,
  V2Response,
} from './types'

// --- 3×3 por dominio (ADR-0024/0025) ---
// Una sola llamada por dominio: envía las filas en el formato fijo y recibe los tres
// modelos entrenados al vuelo. Es síncrono (no hay modo lote).
export const postV2 = (dominio: V2Domain, rows: AutoRow[], horizon = 14) =>
  postJson<V2Response>(`/v2/${dominio}`, { rows, horizon }).then((r) => r.data)

/** Corre el análisis 3×3 sobre los datos sintéticos del propio sistema (sin aportar datos). */
export const getV2Demo = (dominio: V2Domain, horizon = 14) =>
  getJson<V2Response>(`/v2/${dominio}/demo?horizon=${horizon}`).then((r) => r.data)

// --- Predicción agnóstica auto-entrenada (ADR-0023) ---
// El cliente declara su esquema (`schema`) y trae columnas arbitrarias (`rows`). El backend
// entrena el ganador al vuelo y responde 200 (no hay modo lote: el entrenamiento es síncrono).
export const postAutoSales = (req: AutoSalesRequest) =>
  postJson<AutoSalesResponse>('/auto/sales', req).then((r) => r.data)

export const postAutoInventory = (req: AutoInventoryRequest) =>
  postJson<AutoInventoryResponse>('/auto/inventory', req).then((r) => r.data)

export const postAutoPurchases = (req: AutoPurchasesRequest) =>
  postJson<AutoPurchasesResponse>('/auto/purchases', req).then((r) => r.data)

export type AutoDomain = 'sales' | 'inventory' | 'purchases'

/** Descarga la plantilla Excel generada a la medida del esquema declarado. */
export const downloadAutoTemplate = (domain: AutoDomain, schema: AutoSchemaSpec) =>
  postJsonBlob(`/auto/${domain}/template`, { schema })

/** Sube un Excel (hoja `datos` [+ `items`]) y devuelve el resultado auto-entrenado. */
export async function uploadAutoExcel<TRes>(
  domain: AutoDomain,
  file: File,
  fields: Record<string, string | number>,
): Promise<TRes> {
  const { data } = await postFile<TRes>(`/auto/${domain}/excel`, file, fields)
  return data
}
