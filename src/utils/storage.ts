/** localStorage 简易封装 + JSON */
export const storage = {
  get<T = unknown>(key: string, fallback?: T): T | undefined {
    try {
      const raw = localStorage.getItem(key)
      if (!raw) return fallback
      return JSON.parse(raw) as T
    } catch {
      return fallback
    }
  },
  set(key: string, val: unknown) {
    try { localStorage.setItem(key, JSON.stringify(val)) } catch { /* quota */ }
  },
  remove(key: string) { localStorage.removeItem(key) }
}
