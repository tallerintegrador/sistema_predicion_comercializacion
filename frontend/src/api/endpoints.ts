/**
 * Endpoints SPC tipados. Una función por operación.
 *
 * Motor **3×3** (`/v2/*`), entrenado en el momento (sin artefactos): un formato fijo por
 * dominio (ventas/compras/almacén) que devuelve los tres modelos (regresión, clasificación,
 * clustering) en una sola respuesta.
 *
 * Motor **Catálogo v3** (`/v3/*`, ADR-0028): 30 consultas predefinidas, 10 por dominio,
 * ejecutadas automáticamente (4 regresión + 3 clasificación + 3 clustering).
 */
import { getBlob, getJson, postFile, postJson } from './client'
import type {
  AutoRow,
  V2Domain,
  V2Esquema,
  V2Response,
  V3Domain,
  CatalogResponse,
  ModuleResponse,
  HistorialResponse,
  HistorialDetalle,
} from './types'

// --- 3×3 por dominio (ADR-0024/0025) ---
// Una sola llamada por dominio: envía las filas en el formato fijo y recibe los tres
// modelos entrenados al vuelo. Es síncrono (no hay modo lote).
export const postV2 = (dominio: V2Domain, rows: AutoRow[], horizon = 14) =>
  postJson<V2Response>(`/v2/${dominio}`, { rows, horizon }).then((r) => r.data)

/** Corre el análisis 3×3 sobre los datos sintéticos del propio sistema (sin aportar datos). */
export const getV2Demo = (dominio: V2Domain, horizon = 14) =>
  getJson<V2Response>(`/v2/${dominio}/demo?horizon=${horizon}`).then((r) => r.data)

/** Diccionario de variables del dominio (qué columnas pedir y qué se predice, en simple). */
export const getV2Esquema = (dominio: V2Domain) =>
  getJson<V2Esquema>(`/v2/${dominio}/esquema`).then((r) => r.data)

/** Descarga la plantilla/ejemplo del dominio en Excel (blob con nombre de archivo). */
export const downloadV2Plantilla = (
  dominio: V2Domain,
  contenido: 'basica' | 'rica' = 'basica',
) => getBlob(`/v2/${dominio}/plantilla?formato=excel&contenido=${contenido}`)

/** Obtiene la plantilla/ejemplo del dominio en JSON ({rows, horizon}). */
export const getV2PlantillaJson = (
  dominio: V2Domain,
  contenido: 'basica' | 'rica' = 'basica',
) =>
  getJson<{ rows: AutoRow[]; horizon: number }>(
    `/v2/${dominio}/plantilla?formato=json&contenido=${contenido}`,
  ).then((r) => r.data)

/** Sube un Excel con el formato del dominio y devuelve el análisis 3×3. */
export const postV2Excel = (dominio: V2Domain, file: File, horizon = 14) =>
  postFile<V2Response>(`/v2/${dominio}/excel?horizon=${horizon}`, file, {}, 'archivo').then(
    (r) => r.data,
  )

// --- Catálogo v3: 30 consultas predefinidas (ADR-0028) ---

/** Lista el catálogo completo de 30 consultas. */
export const getV3Catalogo = () =>
  getJson<CatalogResponse>('/v3/catalogo').then((r) => r.data)

/** Descarga la plantilla Excel del módulo (UNA por módulo, todas sus columnas). */
export const getV3Plantilla = (modulo: V3Domain) =>
  getBlob(`/v3/${modulo}/plantilla`)

/** Descarga la plantilla JSON del módulo (mismas columnas, con filas de ejemplo). */
export const getV3PlantillaJson = (modulo: V3Domain) =>
  getBlob(`/v3/${modulo}/plantilla?formato=json`)

/** Analiza los datos: ejecuta las 10 consultas automáticamente (4R+3C+3K). */
export const postV3Analisis = (modulo: V3Domain, rows: AutoRow[]) =>
  postJson<ModuleResponse>(`/v3/${modulo}`, { rows }).then((r) => r.data)

/** Obtiene datos de ejemplo del módulo para demostración. */
export const getV3Demo = (modulo: V3Domain) =>
  getJson<ModuleResponse>(`/v3/${modulo}/demo`).then((r) => r.data)

/** Historial de análisis del cliente para el módulo (más recientes primero). */
export const getV3Historial = (modulo: V3Domain, limite = 50) =>
  getJson<HistorialResponse>(`/v3/${modulo}/historial?limite=${limite}`).then((r) => r.data)

/** Detalle de un análisis pasado, con sus valores predichos. */
export const getV3Prediccion = (id: number) =>
  getJson<HistorialDetalle>(`/v3/historial/${id}`).then((r) => r.data)
