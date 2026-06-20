/**
 * Cliente HTTP del frontend SPC.
 *
 * Envuelve `fetch` para: (1) resolver la base URL de la API, (2) enviar el header
 * `X-Client-Id` (corpus de la Fase A), y (3) traducir el error uniforme del
 * backend ({error:{type,message,details}}) a una excepción tipada `ApiError`.
 */
import type { ErrorEnvelope, ErrorDetail } from './types'

const BASE_URL: string = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8010'
).replace(/\/$/, '')

const CLIENT_ID: string = import.meta.env.VITE_CLIENT_ID ?? 'frontend-demo'

/** Error de la API con el cuerpo uniforme del contrato ya parseado. */
export class ApiError extends Error {
  status: number
  type: string
  details: ErrorDetail[]

  constructor(status: number, type: string, message: string, details: ErrorDetail[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.type = type
    this.details = details
  }
}

function headersBase(extra?: HeadersInit): Headers {
  const h = new Headers(extra)
  h.set('X-Client-Id', CLIENT_ID)
  return h
}

async function parseError(res: Response): Promise<ApiError> {
  let type = 'http_error'
  let message = `Error HTTP ${res.status}`
  let details: ErrorDetail[] = []
  try {
    const body = (await res.json()) as Partial<ErrorEnvelope>
    if (body?.error) {
      type = body.error.type ?? type
      message = body.error.message ?? message
      details = body.error.details ?? []
    }
  } catch {
    // Respuesta sin JSON: nos quedamos con el mensaje genérico.
  }
  return new ApiError(res.status, type, message, details)
}

/** POST JSON. Lanza `ApiError` si la respuesta no es 2xx ni 202. */
export async function postJson<T>(path: string, body: unknown): Promise<{ status: number; data: T }> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: headersBase({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok && res.status !== 202) throw await parseError(res)
  return { status: res.status, data: (await res.json()) as T }
}

/** GET JSON. */
export async function getJson<T>(path: string): Promise<{ status: number; data: T }> {
  const res = await fetch(`${BASE_URL}${path}`, { headers: headersBase() })
  if (!res.ok && res.status !== 202) throw await parseError(res)
  return { status: res.status, data: (await res.json()) as T }
}

/** Sube un archivo (campo form `file`). Lanza `ApiError` salvo 2xx/202. */
export async function postFile<T>(path: string, file: File): Promise<{ status: number; data: T }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: headersBase(), // no fijar Content-Type: el navegador pone el boundary
    body: form,
  })
  if (!res.ok && res.status !== 202) throw await parseError(res)
  return { status: res.status, data: (await res.json()) as T }
}

/** Descarga un blob (plantilla Excel). */
export async function getBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${BASE_URL}${path}`, { headers: headersBase() })
  if (!res.ok) throw await parseError(res)
  const disp = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disp)
  const filename = match?.[1] ?? path.split('/').pop() ?? 'descarga.xlsx'
  return { blob: await res.blob(), filename }
}

export const apiBaseUrl = BASE_URL
