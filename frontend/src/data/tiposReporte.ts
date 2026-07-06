/**
 * Fuente ÚNICA del orden y vocabulario de los tipos de reporte (A1).
 * Usada por el Paso 1 (listado de análisis) y por las secciones de resultados, para que
 * el orden sea idéntico: Predicción → Alerta → Segmento.
 */
import type { ReportType } from '../api/types'

export interface TipoReporteInfo {
  type: ReportType
  chip: string // etiqueta corta en la vista
  titulo: string // título de la sección de resultados
  icono: string
  descripcion: string // subtítulo de la sección
  explicacion: string // qué es, para el Paso 1 (cliente no técnico)
}

export const TIPOS_REPORTE: TipoReporteInfo[] = [
  {
    type: 'regression',
    chip: 'Predicción',
    titulo: 'Predicciones',
    icono: '📊',
    descripcion: 'Números: qué esperar según los factores de tu negocio',
    explicacion: 'Estiman un número (unidades, ingreso, días de entrega…) a partir de los factores de tu negocio.',
  },
  {
    type: 'classification',
    chip: 'Alerta',
    titulo: 'Alertas',
    icono: '🔔',
    descripcion: 'Sí/No o categoría: qué requiere tu atención',
    explicacion: 'Responden sí/no (¿riesgo de quiebre?) o eligen una categoría (¿por qué canal se venderá?).',
  },
  {
    type: 'clustering',
    chip: 'Segmento',
    titulo: 'Grupos',
    icono: '🧩',
    descripcion: 'Segmentación: cómo agrupar tus datos para gestionarlos mejor',
    explicacion: 'Agrupan productos, tiendas o proveedores parecidos para poder gestionarlos de forma distinta.',
  },
]

/** Rango de orden por tipo (para ordenar el listado del Paso 1 igual que los resultados). */
export const ORDEN_TIPO: Record<ReportType, number> = {
  regression: 0,
  classification: 1,
  clustering: 2,
}

export const INFO_POR_TIPO: Record<ReportType, TipoReporteInfo> = Object.fromEntries(
  TIPOS_REPORTE.map((t) => [t.type, t]),
) as Record<ReportType, TipoReporteInfo>
