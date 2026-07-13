import { request, rawCall, readActiveToken, clearActiveToken } from './request'

export type SearchMode = 'precise' | 'smart' | 'explore'
export type SourceType = 'manual' | 'case' | 'graph'

export interface SearchPayload {
  text?: string
  /** 缩略图 URL，仅前端展示用 */
  images?: string[]
  /** 真正发给后端的图片文件（多模态时必传一张，会取第一个） */
  imageFile?: File | null
  deviceModel?: string
  mode?: SearchMode
  filters?: Record<string, unknown>
}

export interface SearchHit {
  id: string
  type: SourceType
  title: string
  snippet: string
  similarity: number          // 0~1
  source: string
  highlights?: string[]
  meta?: Record<string, unknown>
}

export interface RecommendedTicket {
  id: number
  device: string
  fault: string
  summary: string
  added: boolean
  score: number
}

export interface SearchResult {
  summary: string
  /** 后端 QA 日志 ID，用于手动修正功能 */
  qaLogId?: number
  /** 后端目前不返回原因 Top3，前端根据问题展示空数组或保留默认 */
  causes: { name: string; confidence: number }[]
  hits: SearchHit[]
  /** 多模态场景下后端返回的图片观察文本（无图为空） */
  imageObservation?: string
  /** FIX5 第 13 项：检索结果中的推荐工单 */
  recommendedTickets: RecommendedTicket[]
}

/** 后端 /api/chat/query 返回结构 */
interface BackendChatResp {
  answer: string
  qa_log_id?: number
  image_observation: string
  sources: { id?: string; doc_id?: string | number; index?: number; title: string; snippet: string; hl?: string; page?: number; score?: number; images?: { url: string; name?: string; path?: string }[] }[]
  recommended_tickets?: RecommendedTicket[]
}

/**
 * 多模态检索：实际调用 /api/chat/query。
 * - question 取自 text + deviceModel 拼接
 * - image 字段取 imageFile（前端图片管理保留 File 引用，URL 只用于预览）
 * - sources → hits（带 docId/page 元数据，确保和回答强绑定）
 *
 * FIX3 第 2.4 项：后端不可达时**抛错**，由 UI 展示失败态、不写入历史。
 */
export const multimodalSearch = async (p: SearchPayload): Promise<SearchResult> => {
  const question = [p.text || '', p.deviceModel ? `设备型号：${p.deviceModel}` : '']
    .filter(Boolean)
    .join('\n')
    .trim()

  if (!question && !p.imageFile) {
    throw new Error('请输入问题或上传图片')
  }

  // 多模态问题修复：纯图片查询不再使用"请描述设备图片中的故障"作为默认 question
  // 该占位符会污染 embedding 向量空间，导致检索不到相关文档
  // 纯图片时传空字符串，由后端 chat.py 检测到后用 VL document 模式输出作为主查询
  const form = new FormData()
  form.append('question', question || '')
  if (p.imageFile) form.append('image', p.imageFile)

  const data = await rawCall<BackendChatResp>(() =>
    request.post<BackendChatResp>('/chat/query', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 90_000
    })
  )
  const hits: SearchHit[] = (data.sources || []).map((s, i) => ({
    id: String(s.id ?? 'src-' + i),
    type: 'manual',
    title: s.title || `引用 ${i + 1}`,
    snippet: s.snippet || '',
    similarity: typeof s.score === 'number' ? Math.max(0, Math.min(1, s.score)) : Math.max(0.55, 0.92 - i * 0.07),
    source: '知识库 · ' + (s.title || ''),
    highlights: [],
    meta: { docId: s.doc_id != null ? String(s.doc_id) : undefined, page: s.page, hl: s.hl, images: s.images || [] }
  }))
  return {
    summary: data.answer || '',
    qaLogId: data.qa_log_id,
    causes: [],
    hits,
    imageObservation: data.image_observation || '',
    recommendedTickets: data.recommended_tickets || []
  }
}

export const correctAnswer = (qaLogId: number, correctedAnswer: string) => {
  const form = new FormData()
  form.append('qa_log_id', String(qaLogId))
  form.append('corrected_answer', correctedAnswer)
  return request.post('/chat/correct', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}

/**
 * 流式多模态检索（FIX NEEDS「打字机流式」）：消费后端 /chat/query 的 SSE 流，
 * 逐 token 回调 onToken，最终 resolve 出与 multimodalSearch 相同结构的 SearchResult。
 *
 * 不用 EventSource（不支持 POST/multipart），改用 fetch + ReadableStream 手动解析 SSE。
 * 401 时复用 request.ts 的清 token + 跳登录 语义。
 */
export interface StreamCallbacks {
  onToken?: (delta: string) => void
}

export async function multimodalSearchStream(
  p: SearchPayload,
  cb: StreamCallbacks = {}
): Promise<SearchResult> {
  const question = [p.text || '', p.deviceModel ? `设备型号：${p.deviceModel}` : '']
    .filter(Boolean)
    .join('\n')
    .trim()

  if (!question && !p.imageFile) {
    throw new Error('请输入问题或上传图片')
  }

  const form = new FormData()
  form.append('question', question || '')
  if (p.imageFile) form.append('image', p.imageFile)

  const base = (import.meta as any).env?.VITE_API_BASE || '/api'
  const headers: Record<string, string> = {}
  const token = readActiveToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(`${base}/chat/query`, { method: 'POST', headers, body: form })

  if (resp.status === 401) {
    clearActiveToken()
    if (typeof location !== 'undefined' && !location.hash.startsWith('#/login')) {
      location.hash = '#/login'
    }
    throw new Error('登录已过期，请重新登录')
  }
  if (!resp.ok || !resp.body) {
    let detail = ''
    try { detail = await resp.text() } catch { /* ignore */ }
    // 尝试从 FastAPI 错误体取 detail 字段
    try {
      const j = JSON.parse(detail)
      if (j?.detail) detail = String(j.detail)
    } catch { /* ignore */ }
    throw new Error(detail || `检索失败 (${resp.status})`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let summary = ''
  let meta: any = null

  const parseBlock = (raw: string): { event: string; data: any } | null => {
    let event = 'message'
    let dataStr = ''
    for (const line of raw.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataStr += line.slice(5).trim()
    }
    if (!dataStr) return { event, data: null }
    try { return { event, data: JSON.parse(dataStr) } } catch { return { event, data: null } }
  }

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const ev = parseBlock(raw)
      if (!ev) continue
      if (ev.event === 'token') {
        const delta = ev.data?.delta || ''
        if (delta) { summary += delta; cb.onToken?.(delta) }
      } else if (ev.event === 'meta') {
        meta = ev.data
      } else if (ev.event === 'error') {
        throw new Error(ev.data?.message || 'AI 生成失败')
      }
    }
  }

  const hits: SearchHit[] = (meta?.sources || []).map((s: any, i: number) => ({
    id: String(s.id ?? 'src-' + i),
    type: 'manual' as SourceType,
    title: s.title || `引用 ${i + 1}`,
    snippet: s.snippet || '',
    similarity: typeof s.score === 'number' ? Math.max(0, Math.min(1, s.score)) : Math.max(0.55, 0.92 - i * 0.07),
    source: '知识库 · ' + (s.title || ''),
    highlights: [],
    meta: { docId: s.doc_id != null ? String(s.doc_id) : undefined, page: s.page, hl: s.hl, images: s.images || [] }
  }))
  return {
    summary: meta?.answer || summary || '',
    qaLogId: meta?.qa_log_id ?? undefined,
    causes: [],
    hits,
    imageObservation: meta?.image_observation || '',
    recommendedTickets: meta?.recommended_tickets || []
  }
}
