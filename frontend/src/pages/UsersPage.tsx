import { useEffect, useState } from 'react'
import {
  createRole,
  createUser,
  getPermissions,
  getRoles,
  getUsers,
  updateUser,
} from '../api/auth'
import type { PermissionOut, RoleOut, UserOut } from '../api/auth'
import { ApiError } from '../api/client'
import { ModuleHeader } from '../components/ui/ModuleHeader'

/**
 * Administración de usuarios y roles (solo para roles con `action:users_manage`). Permite
 * crear/editar roles (con permisos del catálogo del backend) y crear/editar cuentas. La
 * autorización real la aplica el backend; aquí solo se opera contra esos endpoints.
 */
export function UsersPage() {
  const [permisos, setPermisos] = useState<PermissionOut[]>([])
  const [roles, setRoles] = useState<RoleOut[]>([])
  const [usuarios, setUsuarios] = useState<UserOut[]>([])
  const [error, setError] = useState<string | null>(null)

  const recargar = async () => {
    const [r, u] = await Promise.all([getRoles(), getUsers()])
    setRoles(r)
    setUsuarios(u)
  }

  useEffect(() => {
    getPermissions().then(setPermisos).catch(() => setError('No se pudo cargar el catálogo de permisos.'))
    recargar().catch(() => setError('No se pudieron cargar usuarios y roles.'))
  }, [])

  const manejar = (fn: () => Promise<void>) => async () => {
    setError(null)
    try {
      await fn()
      await recargar()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ocurrió un error.')
    }
  }

  return (
    <div className="space-y-6">
      <ModuleHeader view="users" />

      {error && (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>
      )}

      <RolesCard permisos={permisos} roles={roles} onChange={manejar} />
      <UsuariosCard roles={roles} usuarios={usuarios} onChange={manejar} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------
function RolesCard({
  permisos,
  roles,
  onChange,
}: {
  permisos: PermissionOut[]
  roles: RoleOut[]
  onChange: (fn: () => Promise<void>) => () => Promise<void>
}) {
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set())

  const toggle = (key: string) => {
    const s = new Set(seleccion)
    if (s.has(key)) s.delete(key)
    else s.add(key)
    setSeleccion(s)
  }

  const crear = onChange(async () => {
    await createRole({ name: nombre.trim(), description: descripcion || null, permissions: [...seleccion] })
    setNombre('')
    setDescripcion('')
    setSeleccion(new Set())
  })

  const modulos = permisos.filter((p) => p.group === 'module')
  const acciones = permisos.filter((p) => p.group === 'action')
  // Mapa clave técnica → etiqueta legible (para mostrar permisos sin tecnicismos).
  const labelOf = (key: string) => permisos.find((p) => p.key === key)?.label ?? key

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Roles</h3>

      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="th">Rol</th>
              <th className="th">Permisos</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="td font-medium">{r.name}</td>
                <td className="td">
                  {r.permissions.length === 0 ? (
                    <span className="text-xs text-slate-400">—</span>
                  ) : (
                    <span className="flex flex-wrap gap-1">
                      {r.permissions.map((key) => (
                        <span key={key} className="badge bg-slate-100 text-slate-600">
                          {labelOf(key)}
                        </span>
                      ))}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="rounded-lg border border-slate-200 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">Crear un rol</summary>
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <input className="input" placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            <input className="input" placeholder="Descripción (opcional)" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </div>

          <fieldset>
            <legend className="label">Módulos</legend>
            <div className="flex flex-wrap gap-3">
              {modulos.map((p) => (
                <Casilla key={p.key} p={p} checked={seleccion.has(p.key)} onToggle={() => toggle(p.key)} />
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="label">Acciones</legend>
            <div className="flex flex-wrap gap-3">
              {acciones.map((p) => (
                <Casilla key={p.key} p={p} checked={seleccion.has(p.key)} onToggle={() => toggle(p.key)} />
              ))}
            </div>
          </fieldset>

          <button className="btn-primary" onClick={crear} disabled={!nombre.trim()}>Crear rol</button>
        </div>
      </details>
    </section>
  )
}

function Casilla({ p, checked, onToggle }: { p: PermissionOut; checked: boolean; onToggle: () => void }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-slate-700">
      <input type="checkbox" checked={checked} onChange={onToggle} />
      {p.label}
    </label>
  )
}

// ---------------------------------------------------------------------------
// Usuarios
// ---------------------------------------------------------------------------
function UsuariosCard({
  roles,
  usuarios,
  onChange,
}: {
  roles: RoleOut[]
  usuarios: UserOut[]
  onChange: (fn: () => Promise<void>) => () => Promise<void>
}) {
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [roleId, setRoleId] = useState<number | ''>('')

  const crear = onChange(async () => {
    if (roleId === '') return
    await createUser({ user_id: userId.trim(), password, role_id: roleId })
    setUserId('')
    setPassword('')
    setRoleId('')
  })

  return (
    <section className="card space-y-4">
      <h3 className="text-base font-semibold text-slate-800">Usuarios</h3>

      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="th">Id</th>
              <th className="th">Rol</th>
              <th className="th">Estado</th>
              <th className="th">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.user_id} className="border-t border-slate-100">
                <td className="td font-medium">{u.user_id}</td>
                <td className="td">
                  <select
                    className="input py-1"
                    value={u.role_id}
                    onChange={(e) =>
                      onChange(async () => {
                        await updateUser(u.user_id, { role_id: Number(e.target.value) })
                      })()
                    }
                  >
                    {roles.map((r) => (
                      <option key={r.id} value={r.id}>{r.name}</option>
                    ))}
                  </select>
                </td>
                <td className="td">
                  <span className={`badge ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-600'}`}>
                    {u.is_active ? 'Activo' : 'Inactivo'}
                  </span>
                </td>
                <td className="td">
                  <button
                    className="btn-ghost text-xs"
                    onClick={onChange(async () => {
                      await updateUser(u.user_id, { is_active: !u.is_active })
                    })}
                  >
                    {u.is_active ? 'Desactivar' : 'Activar'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="rounded-lg border border-slate-200 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">Crear un usuario</summary>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <input className="input" placeholder="Id" value={userId} onChange={(e) => setUserId(e.target.value)} />
          <input
            className="input"
            type="password"
            placeholder="Contraseña inicial"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select className="input" value={roleId} onChange={(e) => setRoleId(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">Rol…</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
          <button className="btn-primary" onClick={crear} disabled={!userId.trim() || password.length < 4 || roleId === ''}>
            Crear
          </button>
        </div>
      </details>
    </section>
  )
}
