import { AxiosError } from 'axios'
import { request } from './request'
import type { Role } from '@/constants/roles'
import { mapBackendRole } from '@/constants/roles'

export interface LoginPayload { username: string; password: string; remember?: boolean }
export interface LoginResult {
  token: string
  user: { id: string; name: string; role: Role }
}

/** 后端 access_token / role 响应体 */
interface BackendTokenOut {
  access_token: string
  role: string  // worker / leader / auditor / admin
  username: string
}

/**
 * 错误归一化：
 * - 网络错误 / 后端不可达：isNetwork=true，UI 提示"服务不可用"
 * - HTTP 业务错误（401 / 400）：抛后端 detail 文本，UI 直接展示
 */
class ApiError extends Error {
  isNetwork: boolean
  status?: number
  constructor(msg: string, isNetwork: boolean, status?: number) {
    super(msg)
    this.isNetwork = isNetwork
    this.status = status
  }
}

function normalizeError(e: unknown): ApiError {
  if (e instanceof AxiosError) {
    if (!e.response) return new ApiError('服务不可用，请检查后端连接', true)
    const data = e.response.data as any
    const detail = (data && (data.detail || data.message)) || `请求失败（${e.response.status}）`
    return new ApiError(String(detail), false, e.response.status)
  }
  return new ApiError((e as Error)?.message || '未知错误', false)
}

/** 登录：失败时抛出明确错误，不再降级 mock（FIX5 第 16 项） */
export const login = async (p: LoginPayload): Promise<LoginResult> => {
  try {
    const { data } = await request.post<BackendTokenOut>('/auth/login', {
      username: p.username, password: p.password
    })
    return {
      token: data.access_token,
      user: { id: data.username, name: data.username, role: mapBackendRole(data.role) }
    }
  } catch (e) {
    throw normalizeError(e)
  }
}

/** 注册：后端固定创建员工账户（worker），失败抛出明确错误 */
export const register = async (p: LoginPayload): Promise<LoginResult> => {
  try {
    const { data } = await request.post<BackendTokenOut>('/auth/register', {
      username: p.username, password: p.password
    })
    return {
      token: data.access_token,
      user: { id: data.username, name: data.username, role: mapBackendRole(data.role) }
    }
  } catch (e) {
    throw normalizeError(e)
  }
}

interface MeOut { id: number; username: string; role: string; isDefaultAdmin?: boolean }

/** 用 token 回填当前用户信息（前端不再把用户资料写入 localStorage） */
export const fetchMe = async (): Promise<LoginResult['user'] & { isDefaultAdmin: boolean }> => {
  const { data } = await request.get<MeOut>('/auth/me')
  return {
    id: data.username,
    name: data.username,
    role: mapBackendRole(data.role),
    isDefaultAdmin: !!data.isDefaultAdmin,
  }
}

/** 修改自己的密码 */
export const changePassword = async (oldPassword: string, newPassword: string): Promise<{ ok: boolean }> => {
  try {
    const { data } = await request.put<{ ok: boolean }>('/auth/change-password', {
      old_password: oldPassword, new_password: newPassword
    })
    return data ?? { ok: true }
  } catch (e) {
    throw normalizeError(e)
  }
}

/** 后端没有登出接口，纯前端清 token 即可（store 已经处理） */
export const logout = async () => ({ ok: true })

export { ApiError }
