import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { showFailToast } from 'vant'
import { storage } from '@/utils/storage'

export interface ApiResponse<T = unknown> {
  code: number
  msg: string
  data: T
}

/**
 * FIX6 第 11 项：用户端 / 管理端 token 隔离
 * - 旧 key `app:token` 仅做迁移兼容
 * - 用户端：`user_token`；管理端：`admin_token`
 * - 通过当前 hash 路由前缀（#/admin*）区分活动端
 */
const LEGACY_TOKEN_KEY = 'app:token'
const USER_TOKEN_KEY = 'user_token'
const ADMIN_TOKEN_KEY = 'admin_token'

/** 判断当前是否处于管理端入口 */
function isAdminContext(): boolean {
  // hash 模式：#/admin/...
  if (typeof location !== 'undefined') {
    const h = location.hash || ''
    if (h.startsWith('#/admin')) return true
    // 兼容兜底（虽然项目使用 hash 模式）
    if ((location.pathname || '').startsWith('/admin')) return true
  }
  return false
}

/** 返回当前上下文对应的 token storage key */
export function activeTokenKey(): string {
  return isAdminContext() ? ADMIN_TOKEN_KEY : USER_TOKEN_KEY
}

/** 读取当前上下文的 token；自动迁移旧 `app:token` */
export function readActiveToken(): string {
  // 优先读取当前上下文 key
  const cur = storage.get<string>(activeTokenKey())
  if (cur) return cur
  // 兼容旧版：把 app:token 迁移到 user_token（默认普通用户）
  const legacy = storage.get<string>(LEGACY_TOKEN_KEY)
  if (legacy) {
    storage.set(USER_TOKEN_KEY, legacy)
    storage.remove(LEGACY_TOKEN_KEY)
    return isAdminContext() ? '' : legacy
  }
  return ''
}

/**
 * 写入 token。
 * - role='admin'：同时写入 user_token + admin_token（admin 既能用用户端检索，又能用管理端）
 * - 其它角色：仅写当前上下文 key（默认 user_token）
 * 这样 admin 从 #/login 登录后切到 #/admin/* 不会因为读取 admin_token 为空而被踢出。
 * FIX6-resume：解决"点击用户管理直接退回登录"问题
 */
export function writeActiveToken(t: string, role?: string) {
  if (role === 'admin') {
    storage.set(USER_TOKEN_KEY, t)
    storage.set(ADMIN_TOKEN_KEY, t)
  } else {
    storage.set(activeTokenKey(), t)
  }
}

/** 清除两端 token（登出场景：避免另一端 token 残留导致下次登录串号） */
export function clearActiveToken() {
  storage.remove(USER_TOKEN_KEY)
  storage.remove(ADMIN_TOKEN_KEY)
  storage.remove(LEGACY_TOKEN_KEY)
}

export const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 15000
})

request.interceptors.request.use(cfg => {
  const t = readActiveToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

request.interceptors.response.use(
  res => res,
  err => {
    const status = err?.response?.status
    const url = String(err?.config?.url || '')
    const detail = String(err?.response?.data?.detail || '')
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register')
    if (status === 401 && !isAuthEndpoint) {
      clearActiveToken()
      // FIX6 第 10 项：区分"过期"与"其他设备登录"两种 401
      if (detail.includes('其他设备')) {
        try { showFailToast({ message: '账号已在其他设备登录', duration: 2200 }) } catch {}
      }
      // 注意：路由是 hash 模式，必须改 hash 而不是 pathname
      const onLogin = location.hash.startsWith('#/login')
      if (!onLogin) location.hash = '#/login'
    }
    // 仅在网络错误时静默；业务错误由调用方处理
    if (!err?.response) {
      console.warn('[api] network or backend unavailable, returning silently')
    }
    return Promise.reject(err)
  }
)

/**
 * 包装：返回 {code,msg,data} 信封中的 data；失败抛出错误（FIX5 第 16 项：不再 mock 兜底）。
 * 注意：本项目后端多数接口直接返回 JSON 体，请优先使用 rawCall。
 */
export async function safeCall<T>(
  fn: () => Promise<{ data: ApiResponse<T> }>
): Promise<T> {
  const { data } = await fn()
  if (data?.code === 0) return data.data
  throw new Error(data?.msg || '请求失败')
}

/**
 * 真实后端调用：FastAPI 直接返回 JSON 体本身（不裹 {code,msg,data}）。
 * 失败时抛错，由调用方 try/catch 并展示错误状态（FIX5 第 16 项：不再 mock 兜底）。
 */
export async function rawCall<T>(
  fn: () => Promise<{ data: T }>
): Promise<T> {
  const { data } = await fn()
  return data as T
}

export function get<T = unknown>(url: string, params?: object, cfg?: AxiosRequestConfig) {
  return request.get<ApiResponse<T>>(url, { params, ...cfg })
}
export function post<T = unknown>(url: string, body?: unknown, cfg?: AxiosRequestConfig) {
  return request.post<ApiResponse<T>>(url, body, cfg)
}
export function put<T = unknown>(url: string, body?: unknown) {
  return request.put<ApiResponse<T>>(url, body)
}
export function del<T = unknown>(url: string) {
  return request.delete<ApiResponse<T>>(url)
}

// FIX6 第 11 项：保留旧导出名称以兼容现有调用方；返回当前上下文的实际 key
export const TOKEN_STORAGE_KEY = USER_TOKEN_KEY
export { USER_TOKEN_KEY, ADMIN_TOKEN_KEY, LEGACY_TOKEN_KEY }

void showFailToast // 防 tree shake
