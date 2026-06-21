import { useRef, useState } from 'react'
import { FileSpreadsheet, FileJson, Download } from 'lucide-react'
import { ApiError } from '../api/client'
import { downloadTemplate } from '../api/endpoints'
import type { Domain } from '../api/types'

/**
 * Panel de carga de datos (ADR-0020). Tres formas honestas de aportar datos, sin
 * "Cargar ejemplo": (1) subir Excel, (2) subir JSON, (3) descargar la plantilla. El
 * Excel se procesa en el servidor; el JSON se lee aquí y se entrega ya parseado a la
 * página, que lo envía con la misma validación del contrato.
 */
export function DataSourcePanel({
  domain,
  onExcel,
  onJson,
  busy,
  accentSolid = 'bg-brand-600 text-white hover:bg-brand-700',
}: {
  domain: Domain
  onExcel: (file: File) => void
  onJson: (data: unknown) => void
  busy: boolean
  accentSolid?: string
}) {
  const excelRef = useRef<HTMLInputElement>(null)
  const jsonRef = useRef<HTMLInputElement>(null)
  const [downloading, setDownloading] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const handleTemplate = async () => {
    setMsg(null)
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
      setMsg(e instanceof ApiError ? e.message : 'No se pudo descargar la plantilla.')
    } finally {
      setDownloading(false)
    }
  }

  const handleExcel = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onExcel(file)
    e.target.value = ''
  }

  const handleJson = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setMsg(null)
    try {
      const data = JSON.parse(await file.text())
      onJson(data)
    } catch {
      setMsg('El archivo no es un JSON válido. Revisa el formato o usa la plantilla.')
    }
  }

  return (
    <section className="card" aria-label="Cargar datos">
      <h3 className="text-sm font-semibold text-slate-700">Cargar tus datos</h3>
      <p className="mt-1 text-xs text-slate-500">
        Sube tu archivo o descarga la plantilla, complétala y vuelve a subirla. Tus datos pasan
        por la misma validación, los subas como Excel o como JSON.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={`btn ${accentSolid}`}
          onClick={() => excelRef.current?.click()}
          disabled={busy}
        >
          <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
          Subir Excel
        </button>
        <button type="button" className="btn-ghost" onClick={() => jsonRef.current?.click()} disabled={busy}>
          <FileJson className="h-4 w-4" aria-hidden="true" />
          Subir JSON
        </button>
        <button type="button" className="btn-ghost" onClick={handleTemplate} disabled={downloading}>
          <Download className="h-4 w-4" aria-hidden="true" />
          {downloading ? 'Descargando…' : 'Descargar plantilla'}
        </button>
        <input ref={excelRef} type="file" accept=".xlsx" className="hidden" onChange={handleExcel} />
        <input ref={jsonRef} type="file" accept=".json,application/json" className="hidden" onChange={handleJson} />
      </div>
      {msg && (
        <p className="mt-2 text-xs text-red-600" role="alert">
          {msg}
        </p>
      )}
    </section>
  )
}
