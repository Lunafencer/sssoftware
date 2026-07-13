/**
 * 检索会话持久化（FIX3 第 2 / 3 项）
 *
 * - 整条会话（含 markdown 原文 + sources）落 localStorage
 * - 按用户隔离：key = `chat:sessions:<userId>`
 * - 切换用户自动重新加载
 * - logout 仅清当前内存缓存，不删别人的本地数据
 */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { storage } from '@/utils/storage'

export interface SourceImageItem {
  url: string
  name?: string
  path?: string
}

export interface SourceItem {
  id: string
  docId?: string
  title: string
  snippet: string
  /** 跳转定位专用：原文关键短语，未经格式化处理，在 Preview 页 locateInMarkdown 中可直接搜到 */
  hl?: string
  page?: number
  similarity?: number
  images?: SourceImageItem[]
}

/** 检索结果中推荐的工单（FIX5 第 13 项） */
export interface RecommendedTicketRef {
  id: number
  device: string
  fault: string
  summary: string
  added: boolean
  score: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  /** assistant 保留 markdown 原文；user 是纯文本 */
  content: string
  /** 用户消息附带的图片预览（base64 或 blob url） */
  images?: string[]
  /** 仅 assistant：后端 QA 日志 ID，用于手动修正功能 */
  qaLogId?: number
  /** 仅 assistant：用户修正后的回答（赛题要求：支持手动标注与修正大模型输出） */
  correctedAnswer?: string
  /** 仅 assistant：本次回答携带的来源引用（与本条消息强绑定） */
  sources?: SourceItem[]
  /** 仅 assistant：图像观察文本 */
  imageObservation?: string
  /** 仅 assistant：推荐工单（FIX5 第 13 项） */
  recommendedTickets?: RecommendedTicketRef[]
  /** 错误态 */
  error?: string
  createdAt: number
}

export interface ChatSession {
  id: string
  userId: string
  title: string
  createdAt: number
  updatedAt: number
  starred: boolean
  messages: ChatMessage[]
}

const sessionStorageKey = (uid: string) => `chat:sessions:${uid || 'anonymous'}`

const nano = () => Math.random().toString(36).slice(2) + Date.now().toString(36)

export const useChatHistoryStore = defineStore('chatHistory', () => {
  const userStore = useUserStore()

  const userId = computed(() => userStore.info?.id || 'anonymous')
  const storageKey = computed(() => sessionStorageKey(userId.value))

  const sessions = ref<ChatSession[]>(loadFromKey(storageKey.value))

  function loadFromKey(key: string): ChatSession[] {
    return storage.get<ChatSession[]>(key) || []
  }

  let saveTimer: number | null = null
  const persist = () => {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => {
      storage.set(storageKey.value, sessions.value)
    }, 250)
  }

  watch(sessions, persist, { deep: true })
  watch(userId, () => {
    sessions.value = loadFromKey(storageKey.value)
  })

  /** 新建一个会话；title 取首条 user 消息前 30 字（在 push 时回填） */
  const createSession = (initialTitle = '新对话'): ChatSession => {
    const s: ChatSession = {
      id: nano(),
      userId: userId.value,
      title: initialTitle,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      starred: false,
      messages: []
    }
    sessions.value.unshift(s)
    return s
  }

  const getSession = (id: string) => sessions.value.find(s => s.id === id)

  const appendMessage = (sessionId: string, msg: ChatMessage) => {
    const s = getSession(sessionId)
    if (!s) return
    s.messages.push(msg)
    s.updatedAt = Date.now()
    if (msg.role === 'user' && (!s.title || s.title === '新对话')) {
      s.title = (msg.content || '新对话').slice(0, 30)
    }
  }

  const updateMessage = (sessionId: string, messageId: string, patch: Partial<ChatMessage>) => {
    const s = getSession(sessionId)
    if (!s) return
    const m = s.messages.find(x => x.id === messageId)
    if (m) Object.assign(m, patch)
    s.updatedAt = Date.now()
  }

  const toggleStar = (sessionId: string) => {
    const s = getSession(sessionId)
    if (!s) return
    s.starred = !s.starred
    s.updatedAt = Date.now()
  }

  const removeSession = (sessionId: string) => {
    const i = sessions.value.findIndex(s => s.id === sessionId)
    if (i >= 0) sessions.value.splice(i, 1)
  }

  const clearAll = () => { sessions.value = [] }

  /** logout 调用：仅清空内存缓存，本地存储保留以便用户再次登录时离线读取 */
  const reset = () => { sessions.value = [] }

  /** 切换 / 登录后强制重新加载 */
  const reload = () => { sessions.value = loadFromKey(storageKey.value) }

  /** 摘要：取前两条 user + assistant 文本，截断到 60 字 */
  const summaryOf = (s: ChatSession): string => {
    const txt = s.messages.slice(0, 4).map(m => {
      const c = (m.content || '').replace(/[#*`>\-]/g, '').replace(/\n+/g, ' ').trim()
      return c
    }).filter(Boolean).join(' / ')
    return txt.slice(0, 60)
  }

  const starredSessions = computed(() => sessions.value.filter(s => s.starred))

  return {
    sessions, userId,
    createSession, getSession, appendMessage, updateMessage,
    toggleStar, removeSession, clearAll, reset, reload,
    summaryOf, starredSessions
  }
})

export { nano as nanoid }
