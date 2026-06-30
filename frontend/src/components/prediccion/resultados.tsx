/**
 * Componentes de **resultado** de la predicción guiada, uno por dominio. Se separan de
 * `configs.tsx` para que cada archivo cumpla la regla de fast-refresh (solo componentes).
 * El acento de color llega por prop, así sirven tanto a la sección dedicada como al modo
 * «Otro rubro» (acento de marca).
 */
import { useMemo } from 'react'
import type { AutoInventoryResponse, AutoPurchasesResponse, AutoSalesResponse } from '../../api/types'
import { ResultTable } from '../ResultTable'
import { SerieChart } from '../charts/SerieChart'
import { TrainingCard } from '../auto/TrainingCard'
import { ResultSummary } from '../ui/ResultSummary'
import { TechnicalDetails } from '../ui/TechnicalDetails'
import type { Accent } from '../../theme/modules'
import { fmtNum } from '../../utils/format'
import { columnasDinamicas } from '../../utils/autoColumns'
import type { ResultadoArgs } from './PrediccionGuiada'
import { PORQUE, granularidadDe, resumenAlmacen, resumenCompras, resumenVentas } from './resumen'

function MetricasCompletas({ metrics }: { metrics: Record<string, number> }) {
  if (Object.keys(metrics).length === 0) return null
  return (
    <p>
      Métricas completas:{' '}
      {Object.entries(metrics).map(([k, v]) => `${k}=${fmtNum(v)}`).join(' · ')}
    </p>
  )
}

export function VentasResult({ data, rows, effDate, effTarget, extra, options, accent }: ResultadoArgs<AutoSalesResponse> & { accent: Accent }) {
  const forecast = data.forecast
  const cols = useMemo(() => columnasDinamicas(forecast), [forecast])
  const granularity = granularidadDe(extra, options)
  const histPoints = useMemo(
    () =>
      rows
        .map((r) => ({ date: String(r[effDate]), value: Number(r[effTarget]) || 0 }))
        .filter((p) => p.date && p.date !== 'undefined'),
    [rows, effDate, effTarget],
  )
  const forePoints = useMemo(
    () => forecast.map((r) => ({ date: String(r.date), value: Number(r.forecast_demand) || 0 })),
    [forecast],
  )

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Resultado</h3>
      <TrainingCard training={data.training} accentSolid={accent.solid} accentBadge={accent.badge} />
      <ResultSummary text={resumenVentas(forecast, granularity, effTarget)} tone="bg-sales-50 text-sales-700" />
      <SerieChart history={histPoints} forecast={forePoints} histLabel={`Histórico (${effTarget})`} foreLabel="Pronóstico" hex={accent.hex} />

      {forecast.length > 0 ? (
        <ResultTable columns={cols} rows={forecast} />
      ) : (
        <p className="text-sm text-slate-500">El modelo no produjo filas para esta consulta.</p>
      )}

      <TechnicalDetails>
        <p>Objetivo pronosticado: <span className="font-mono text-slate-700">{effTarget}</span></p>
        <p>Firma del esquema: <span className="font-mono text-slate-700">{data.training.schema_signature}</span></p>
        <MetricasCompletas metrics={data.training.honest_metrics} />
        <p>interval_80 (rango estimado al 80%): no disponible aún — el modelo todavía no produce intervalos.</p>
      </TechnicalDetails>
    </section>
  )
}

export function ComprasResult({ data, accent }: ResultadoArgs<AutoPurchasesResponse> & { accent: Accent }) {
  const recs = data.recommendation
  const cols = useMemo(() => columnasDinamicas(recs).filter((c) => c.header !== 'Cálculo'), [recs])

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Recomendación de reposición</h3>
      <TrainingCard training={data.training} accentSolid={accent.solid} accentBadge={accent.badge} />
      <ResultSummary text={resumenCompras(recs)} tone="bg-purchases-50 text-purchases-700" />

      {recs.length > 0 ? (
        <>
          <ResultTable columns={cols} rows={recs} />
          <p className="text-xs text-slate-500"><span className="font-medium">Cómo se calcula:</span> {PORQUE}</p>
        </>
      ) : (
        <p className="text-sm text-slate-500">El modelo no produjo recomendaciones para esta consulta.</p>
      )}

      <TechnicalDetails>
        <p>Firma del esquema: <span className="font-mono text-slate-700">{data.training.schema_signature}</span></p>
        <MetricasCompletas metrics={data.training.honest_metrics} />
      </TechnicalDetails>
    </section>
  )
}

export function AlmacenResult({ data, accent }: ResultadoArgs<AutoInventoryResponse> & { accent: Accent }) {
  const alerts = data.alerts
  const cols = useMemo(() => columnasDinamicas(alerts), [alerts])

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Estado del inventario</h3>
      <TrainingCard training={data.training} accentSolid={accent.solid} accentBadge={accent.badge} />
      <ResultSummary text={resumenAlmacen(alerts)} tone="bg-inventory-50 text-inventory-700" />

      {alerts.length > 0 ? (
        <ResultTable columns={cols} rows={alerts} />
      ) : (
        <p className="text-sm text-slate-500">El modelo no produjo alertas para esta consulta.</p>
      )}

      <TechnicalDetails>
        <p>Firma del esquema: <span className="font-mono text-slate-700">{data.training.schema_signature}</span></p>
        {typeof data.metadata.threshold === 'string' && <p>Definición de demanda alta: {data.metadata.threshold}</p>}
        {data.training.threshold_probability != null && (
          <p>Umbral de probabilidad: {fmtNum(data.training.threshold_probability)}</p>
        )}
        <MetricasCompletas metrics={data.training.honest_metrics} />
      </TechnicalDetails>
    </section>
  )
}
