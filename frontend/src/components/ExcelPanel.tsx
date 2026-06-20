import { useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { downloadTemplate } from '../api/endpoints'
import type { Domain } from '../api/types'

/**
 * Canal Excel: descarga la plantilla del dominio y sube un .xlsx. La subida usa
 * el mismo contrato y validación que el JSON (resultado idéntico por construcción).
 */
export function ExcelPanel({
  domain,
  onUpload,
  busy,
}: {
  domain: Domain
  onUpload: (file: File) => void
  busy: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [downloading, setDownloading] = useState(false)
  const [dlError, setDlError] = useState<string | null>(null)

  const handleTemplate = async () => {
    setDlError(null)
    setDownloading(true)
    try {
      const { blob, filename } = await downloadTemplate(domain)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setDlError(e instanceof ApiError ? e.message : 'No se pudo descargar la plantilla.')
    } finally {
      setDownloading(false)
    }
  }

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onUpload(file)
    e.target.value = '' // permite re-subir el mismo archivo
  }

  return (
    <div className="card">
      <h3 className="mb-1 text-sm font-semibold text-slate-700">Canal Excel</h3>
      <p className="mb-3 text-xs text-slate-500">
        Descarga la plantilla, complétala y súbela. Pasa por la misma validación y predicción que el JSON.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-ghost" onClick={handleTemplate} disabled={downloading}>
          {downloading ? 'Descargando…' : '⬇ Descargar plantilla'}
        </button>
        <button type="button" className="btn-primary" onClick={() => inputRef.current?.click()} disabled={busy}>
          ⬆ Subir Excel (.xlsx)
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={handleFile}
        />
      </div>
      {dlError && <p className="mt-2 text-xs text-red-600">{dlError}</p>}
    </div>
  )
}
