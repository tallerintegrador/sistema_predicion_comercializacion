/**
 * Tipos y endpoints del **control de acceso por roles** (ADR-0014).
 *
 * Espejo de `src/spc/api/schemas/auth.py`. Igual que el resto del contrato, los nombres
 * de campos/claves van en inglés; la UI muestra etiquetas en español.
 */
import { getJson, patchJson, postJson, putJson } from './client'

export type PermissionGroup = 'module' | 'action'

export interface SessionUser {
  user_id: string
  role_id: number
  role: string
  permissions: string[]
  client_id: string
  onboarding_done: boolean
}

export interface LoginResponse {
  token: string
  token_type: 'bearer'
  expires_in: number
  user: SessionUser
}

export interface PermissionOut {
  key: string
  label: string
  group: PermissionGroup
}

export interface PermissionCatalog {
  permissions: PermissionOut[]
}

export interface RoleOut {
  id: number
  name: string
  description?: string | null
  permissions: string[]
}

export interface UserOut {
  user_id: string
  role_id: number
  role: string
  client_id: string
  is_active: boolean
  onboarding_done: boolean
  created_at: string
}

export interface ProfileOut {
  client_id: string
  business_name: string
  sector: string
  size: string
  region: string
  currency: string
}

export interface ProfileOptions {
  sectors: string[]
  sizes: string[]
  regions: string[]
  currencies: string[]
}

export interface ProfileInput {
  business_name: string
  sector: string
  size: string
  region: string
  currency: string
}

// --- Sesión ---
export async function login(userId: string, password: string): Promise<LoginResponse> {
  const { data } = await postJson<LoginResponse>('/auth/login', {
    user_id: userId,
    password,
  })
  return data
}

export async function getMe(): Promise<SessionUser> {
  const { data } = await getJson<SessionUser>('/auth/me')
  return data
}

// --- Permisos / Roles ---
export async function getPermissions(): Promise<PermissionOut[]> {
  const { data } = await getJson<PermissionCatalog>('/permissions')
  return data.permissions
}

export async function getRoles(): Promise<RoleOut[]> {
  const { data } = await getJson<RoleOut[]>('/roles')
  return data
}

export async function createRole(body: {
  name: string
  description?: string | null
  permissions: string[]
}): Promise<RoleOut> {
  const { data } = await postJson<RoleOut>('/roles', body)
  return data
}

export async function updateRole(
  roleId: number,
  body: { description?: string | null; permissions?: string[] },
): Promise<RoleOut> {
  const { data } = await patchJson<RoleOut>(`/roles/${roleId}`, body)
  return data
}

// --- Usuarios ---
export async function getUsers(): Promise<UserOut[]> {
  const { data } = await getJson<UserOut[]>('/users')
  return data
}

export async function createUser(body: {
  user_id: string
  password: string
  role_id: number
}): Promise<UserOut> {
  const { data } = await postJson<UserOut>('/users', body)
  return data
}

export async function updateUser(
  userId: string,
  body: { role_id?: number; password?: string; is_active?: boolean },
): Promise<UserOut> {
  const { data } = await patchJson<UserOut>(`/users/${userId}`, body)
  return data
}

// --- Perfil / Onboarding ---
export async function getProfileOptions(): Promise<ProfileOptions> {
  const { data } = await getJson<ProfileOptions>('/profile/options')
  return data
}

export async function getProfile(): Promise<ProfileOut> {
  const { data } = await getJson<ProfileOut>('/profile')
  return data
}

export async function saveProfile(body: ProfileInput): Promise<ProfileOut> {
  const { data } = await putJson<ProfileOut>('/profile', body)
  return data
}
