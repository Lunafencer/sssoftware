import { request, rawCall } from './request'
import type { FrontendRole, BackendRole } from '@/constants/roles'
import { mapFrontendRole, mapBackendRole } from '@/constants/roles'

export interface SysUser {
  id: number
  username: string
  role: BackendRole
  isDefaultAdmin: boolean
  createdAt: string | null
}

// 兼容旧引用名（统一来源在 src/constants/roles.ts）
export const frontendRoleToBackend = (r: FrontendRole): BackendRole => mapFrontendRole(r)
export const backendRoleToFrontend = (r: string): FrontendRole => mapBackendRole(r)
export type { BackendRole }

/** GET /api/admin/users（仅 admin） */
export const listUsers = (): Promise<SysUser[]> =>
  rawCall<SysUser[]>(() => request.get<SysUser[]>('/admin/users'))

/** 创建账户（员工/审查员/管理员） */
export const createUser = (body: { username: string; password?: string; role: BackendRole }) =>
  rawCall<SysUser>(() => request.post<SysUser>('/admin/users', body))

/** 修改用户名 / 角色 */
export const updateUser = (userId: number, body: { username?: string; role?: BackendRole }) =>
  rawCall<SysUser>(() => request.put<SysUser>(`/admin/users/${userId}`, body))

/** 仅改角色（兼容旧调用） */
export const updateUserRole = (userId: number, role: BackendRole) =>
  rawCall<SysUser>(() => request.put<SysUser>(`/admin/users/${userId}/role`, { role }))

/** 重置密码为 123456 */
export const resetPassword = (userId: number) =>
  rawCall<{ ok: boolean; password: string }>(() =>
    request.put<{ ok: boolean; password: string }>(`/admin/users/${userId}/reset-password`, {}))

/** 删除账户（默认 admin 不可删） */
export const deleteUser = (userId: number) =>
  rawCall<{ ok: boolean }>(() => request.delete<{ ok: boolean }>(`/admin/users/${userId}`))
