/**
 * Registro central de SECCIONES (ADR-0020). Una sola fuente para: etiqueta en español,
 * ícono, permisos requeridos, explicación de "qué hace / para qué sirve" y el acento de
 * color por módulo. Lo consumen el sidebar (Layout), la pantalla de Inicio y los
 * encabezados de cada módulo, de modo que la identidad visual queda consistente.
 *
 * Nota Tailwind v4: las clases de acento se escriben como literales completos (no se
 * construyen dinámicamente) para que el escáner de Tailwind las genere.
 */
import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard,
  BarChart3,
  ShoppingCart,
  Package,
  Sparkles,
  Wand2,
  Users,
  BookOpenText,
  Info,
} from 'lucide-react'

export type View =
  | 'home'
  | 'catalog'
  | 'sales'
  | 'purchases'
  | 'inventory'
  | 'auto'
  | 'training'
  | 'users'
  | 'about'

/** Acento de color de una sección, en clases utilitarias completas (literales). */
export interface Accent {
  /** Cuadro del ícono (tinte claro + texto del acento). */
  chip: string
  /** Ítem de navegación activo. */
  navActive: string
  /** Etiqueta/realce sutil (badge). */
  badge: string
  /** Botón sólido de acción principal del módulo. */
  solid: string
  /** Color de la serie principal en gráficos (hex). */
  hex: string
}

const ACCENTS: Record<string, Accent> = {
  brand: {
    chip: 'bg-brand-100 text-brand-700',
    navActive: 'bg-brand-50 text-brand-700',
    badge: 'bg-brand-50 text-brand-700',
    solid: 'bg-brand-600 text-white hover:bg-brand-700',
    hex: '#4f46e5',
  },
  sales: {
    chip: 'bg-sales-100 text-sales-700',
    navActive: 'bg-sales-50 text-sales-700',
    badge: 'bg-sales-50 text-sales-700',
    solid: 'bg-sales-600 text-white hover:bg-sales-700',
    hex: '#4f46e5',
  },
  purchases: {
    chip: 'bg-purchases-100 text-purchases-700',
    navActive: 'bg-purchases-50 text-purchases-700',
    badge: 'bg-purchases-50 text-purchases-700',
    solid: 'bg-purchases-600 text-white hover:bg-purchases-700',
    hex: '#ea580c',
  },
  inventory: {
    chip: 'bg-inventory-100 text-inventory-700',
    navActive: 'bg-inventory-50 text-inventory-700',
    badge: 'bg-inventory-50 text-inventory-700',
    solid: 'bg-inventory-600 text-white hover:bg-inventory-700',
    hex: '#0d9488',
  },
  training: {
    chip: 'bg-training-100 text-training-700',
    navActive: 'bg-training-50 text-training-700',
    badge: 'bg-training-50 text-training-700',
    solid: 'bg-training-600 text-white hover:bg-training-700',
    hex: '#7c3aed',
  },
  slate: {
    chip: 'bg-slate-100 text-slate-600',
    navActive: 'bg-slate-100 text-slate-800',
    badge: 'bg-slate-100 text-slate-600',
    solid: 'bg-slate-700 text-white hover:bg-slate-800',
    hex: '#475569',
  },
}

export interface SectionDef {
  id: View
  /** Etiqueta del sidebar. */
  label: string
  /** Frase corta de "qué hace y para qué sirve" (lenguaje claro, sin tecnicismos). */
  blurb: string
  icon: LucideIcon
  /** Permisos requeridos (todos). Vacío = visible para cualquier sesión. */
  perms: string[]
  accent: Accent
}

export const SECTIONS: SectionDef[] = [
  {
    id: 'home',
    label: 'Inicio',
    blurb: 'Tu punto de partida: qué puede hacer el sistema y cómo empezar.',
    icon: LayoutDashboard,
    perms: [],
    accent: ACCENTS.brand,
  },
  {
    id: 'catalog',
    label: '¿Qué hace el sistema?',
    blurb: 'Conoce los tres módulos, qué datos piden y qué resultado entregan.',
    icon: BookOpenText,
    perms: ['action:catalog'],
    accent: ACCENTS.brand,
  },
  {
    id: 'sales',
    label: 'Ventas',
    blurb:
      'Calcula cuánto vas a vender en los próximos días, semanas o meses, por tienda y producto, para que planifiques tu demanda.',
    icon: BarChart3,
    perms: ['module:sales'],
    accent: ACCENTS.sales,
  },
  {
    id: 'purchases',
    label: 'Compras',
    blurb:
      'Te dice cuánto y cuándo reponer cada producto para no quedarte sin existencias ni comprar de más.',
    icon: ShoppingCart,
    perms: ['module:purchases'],
    accent: ACCENTS.purchases,
  },
  {
    id: 'inventory',
    label: 'Almacén',
    blurb:
      'Señala qué productos tienen riesgo de agotarse y te sugiere un nivel de existencias objetivo.',
    icon: Package,
    perms: ['module:inventory'],
    accent: ACCENTS.inventory,
  },
  {
    id: 'auto',
    label: 'Predicción a tu medida',
    blurb:
      'Trae tus propias columnas (de cualquier rubro): declaras qué predecir y con qué datos, y el sistema entrena el mejor modelo al momento y predice.',
    icon: Wand2,
    perms: ['module:sales'],
    accent: ACCENTS.brand,
  },
  {
    id: 'training',
    label: 'Mejorar las predicciones',
    blurb:
      'Mejora las predicciones usando tu propia historia — solo si tienes suficientes datos y solo si de verdad mejora.',
    icon: Sparkles,
    perms: ['action:training'],
    accent: ACCENTS.training,
  },
  {
    id: 'users',
    label: 'Usuarios y permisos',
    blurb: 'Administra las cuentas que pueden entrar y qué puede hacer cada una.',
    icon: Users,
    perms: ['action:users_manage'],
    accent: ACCENTS.slate,
  },
  {
    id: 'about',
    label: 'Acerca del sistema',
    blurb: 'Cómo funciona el sistema, en qué datos se entrenó y qué tan exactas son sus estimaciones.',
    icon: Info,
    perms: [],
    accent: ACCENTS.slate,
  },
]

export const SECTION_BY_ID: Record<View, SectionDef> = Object.fromEntries(
  SECTIONS.map((s) => [s.id, s]),
) as Record<View, SectionDef>
