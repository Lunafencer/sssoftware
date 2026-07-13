import { defineStore } from 'pinia'
import { ref } from 'vue'
import { storage } from '@/utils/storage'

/**
 * 检索建议词存储（FIX3 第 2/3 项后）
 * 仅用于输入框的简单"上次提过的词"补全；真实历史已迁移到 stores/chatHistory.ts
 * FIX6 第 9 项：新增 draft 草稿状态，跨页面保留检索表单 / 上传表单内容。
 */
export interface SearchHistoryItem {
  id: string
  text: string
  device?: string
  at: string
}

/** 检索页表单草稿（File 不可序列化，因此只在内存中保留 imageUrls 预览） */
export interface SearchDraft {
  question: string
  imageUrls: string[]
}

/** 经验上传表单草稿 */
export interface UploadDraft {
  title: string
  content: string
  tags: string[]
}

export const useSearchStore = defineStore('search', () => {
  const history = ref<SearchHistoryItem[]>(storage.get<SearchHistoryItem[]>('search:history') || [])

  const push = (q: string, device?: string) => {
    if (!q?.trim()) return
    history.value.unshift({ id: 's' + Date.now(), text: q.trim(), device, at: new Date().toISOString() })
    if (history.value.length > 30) history.value.length = 30
    storage.set('search:history', history.value)
  }

  // FIX6 第 9 项：检索页草稿
  const draft = ref<SearchDraft>(
    storage.get<SearchDraft>('search:draft') || { question: '', imageUrls: [] }
  )
  // 保留对 File 对象的引用（不持久化，路由切换时仍可用）
  const draftImages = ref<File[]>([])
  const setDraft = (question: string, files?: File[] | null, urls?: string[]) => {
    draft.value = { question, imageUrls: urls || draft.value.imageUrls }
    if (files !== undefined) draftImages.value = files || []
    storage.set('search:draft', { question, imageUrls: draft.value.imageUrls })
  }
  const clearDraft = () => {
    draft.value = { question: '', imageUrls: [] }
    draftImages.value = []
    storage.set('search:draft', draft.value)
  }

  // FIX6 第 9 项：经验上传页草稿
  const uploadDraft = ref<UploadDraft>(
    storage.get<UploadDraft>('upload:draft') || { title: '', content: '', tags: [] }
  )
  const setUploadDraft = (title: string, content: string, tags: string[] = []) => {
    uploadDraft.value = { title, content, tags }
    storage.set('upload:draft', uploadDraft.value)
  }
  const clearUploadDraft = () => {
    uploadDraft.value = { title: '', content: '', tags: [] }
    storage.set('upload:draft', uploadDraft.value)
  }

  // FIX6-resume M2：检索"活动会话"——跨路由保留对话进度
  // sessionId：chatHistory store 中正在进行的会话 id
  // pendingMsgId / pendingPromise：切走时不中断后端请求，切回时同步进度
  const activeSessionId = ref<string>(storage.get<string>('search:activeSession') || '')
  const pendingAssistantId = ref<string>('')
  const pendingPromise = ref<Promise<void> | null>(null)

  const setActiveSession = (sid: string) => {
    activeSessionId.value = sid
    storage.set('search:activeSession', sid)
  }
  const clearActiveSession = () => {
    activeSessionId.value = ''
    pendingAssistantId.value = ''
    pendingPromise.value = null
    storage.set('search:activeSession', '')
  }
  const setPending = (msgId: string, p: Promise<void> | null) => {
    pendingAssistantId.value = msgId
    pendingPromise.value = p
  }

  return {
    history, push,
    draft, draftImages, setDraft, clearDraft,
    uploadDraft, setUploadDraft, clearUploadDraft,
    activeSessionId, pendingAssistantId, pendingPromise,
    setActiveSession, clearActiveSession, setPending
  }
})
