import { ArrowRight, Download, FileCheck2, Upload, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useSeccionesVisibles } from '../hooks/useSeccionesVisibles'

/**
 * Pantalla de **Inicio / Bienvenida** (ADR-0020). Da la bienvenida, resume qué puede hacer
 * el sistema y ofrece accesos directos a los módulos del usuario, con una guía de 4 pasos
 * para quien aún no cargó datos. Lenguaje claro, sin tecnicismos.
 */
export function HomePage() {
  const { user } = useAuth()
  const visibles = useSeccionesVisibles()
  // Solo los módulos "de trabajo" como accesos directos (no Inicio/Acerca/Usuarios).
  const modulos = visibles.filter((s) => ['sales', 'purchases', 'inventory', 'auto'].includes(s.id))

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="overflow-hidden rounded-2xl bg-gradient-to-br from-brand-600 to-brand-700 px-6 py-8 text-white shadow-sm sm:px-8">
        <p className="text-sm font-medium text-brand-100">Hola{user?.user_id ? `, ${user.user_id}` : ''} 👋</p>
        <h2 className="mt-1 max-w-2xl text-2xl font-bold leading-tight sm:text-3xl">
          Anticipa tu demanda y planifica con confianza
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-brand-100">
          SPC estima cuánto venderás, cuánto reponer y qué productos podrían agotarse. Solo necesitas
          tu historial de ventas: súbelo y obtén un pronóstico claro en segundos.
        </p>
      </section>

      {/* Accesos directos a los módulos */}
      {modulos.length > 0 && (
        <section>
          <h3 className="mb-3 text-base font-semibold text-slate-800">¿Qué quieres hacer hoy?</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {modulos.map((s) => {
              const Icon = s.icon
              return (
                <Link
                  key={s.id}
                  to={s.path}
                  className="group flex items-start gap-4 rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-all hover:border-slate-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200"
                >
                  <span aria-hidden="true" className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${s.accent.chip}`}>
                    <Icon className="h-6 w-6" />
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1 font-semibold text-slate-800">
                      {s.label}
                      <ArrowRight className="h-4 w-4 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-500" />
                    </span>
                    <span className="mt-0.5 block text-sm leading-relaxed text-slate-500">{s.blurb}</span>
                  </span>
                </Link>
              )
            })}
          </div>
        </section>
      )}

      {/* Guía de 4 pasos */}
      <section className="card">
        <h3 className="text-base font-semibold text-slate-800">¿Primera vez? Empieza en 4 pasos</h3>
        <p className="mt-1 text-sm text-slate-500">
          No necesitas saber de tecnología. Si tienes tus ventas en una hoja de cálculo, ya puedes empezar.
        </p>
        <ol className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Paso n={1} icon={Download} titulo="Descarga la plantilla" texto="Una hoja con las columnas que el sistema necesita." />
          <Paso n={2} icon={FileCheck2} titulo="Complétala" texto="Pega tus ventas pasadas: fecha, tienda, producto y cantidad." />
          <Paso n={3} icon={Upload} titulo="Súbela" texto="En Excel o JSON. El sistema revisa que todo esté en orden." />
          <Paso n={4} icon={Sparkles} titulo="Pronostica" texto="Obtén tu estimación con un resumen claro y un gráfico." />
        </ol>
      </section>
    </div>
  )
}

function Paso({
  n,
  icon: Icon,
  titulo,
  texto,
}: {
  n: number
  icon: typeof Download
  titulo: string
  texto: string
}) {
  return (
    <li className="relative rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
          {n}
        </span>
        <Icon className="h-5 w-5 text-slate-400" aria-hidden="true" />
      </div>
      <p className="mt-2 text-sm font-semibold text-slate-800">{titulo}</p>
      <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{texto}</p>
    </li>
  )
}
