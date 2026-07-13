<script setup lang="ts">
/**
 * PC 端检索 · 对话式布局（FIX3 第 2/3/6 项）
 *
 * - 删除"试试这些问题"区块（FIX3 第 6 项）
 * - assistant 回复用 markdown-it 渲染（FIX3 第 3.1 项）
 * - 来源引用与本条消息绑定（FIX3 第 3.2 项）
 * - 整条会话落 chatHistory store，按 userId 隔离（FIX3 第 2.1/3.3 项）
 */
import { ref, nextTick, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Sparkles, Paperclip, Send, X, Image as ImageIcon, BookOpen, Bot, User as UserIcon, ChevronDown, ChevronUp, Loader, Trash2, Star, ListChecks, UserPlus, Check, Edit3 } from 'lucide-vue-next'
import * as searchApi from '@/api/search'
import { addTicketToMine } from '@/api/ticket'
import { useSearchStore } from '@/stores/search'
import { useChatHistoryStore, nanoid, type SourceItem } from '@/stores/chatHistory'
import { renderMarkdown } from '@/utils/markdown'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'

const route = useRoute()
const store = useSearchStore()
const chat = useChatHistoryStore()

const input = ref(typeof route.query.q === 'string' ? route.query.q : '')
const imageList = ref<{ url: string; name: string; file: File }[]>([])
const sending = ref(false)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()
const scrollEl = ref<HTMLDivElement>()
const expandedSources = ref<Record<string, boolean>>({})
// 最近一次上传的图片文件：用于“1和2是什么”这类连续追问自动带上同一张图
const lastImageFile = ref<File | null>(null)

/** 当前会话；首次发送时再创建，避免空会话被收藏 */
const sessionId = ref<string>('')
const messages = computed(() => sessionId.value ? (chat.getSession(sessionId.value)?.messages || []) : [])
const session = computed(() => sessionId.value ? chat.getSession(sessionId.value) : null)
const hasMessages = computed(() => messages.value.length > 0)

const ensureSession = () => {
  if (!sessionId.value) {
    const s = chat.createSession()
    sessionId.value = s.id
    store.setActiveSession(s.id)  // FIX6-resume M2：登记为活动会话
  }
  return sessionId.value
}

/** 推荐工单：一键添加到我的工单（FIX5 第 13 项） */
const addingTicket = ref<Record<number, boolean>>({})

/** 问答结果手动修正 */
const correctingId = ref<string>('')
const correctionText = ref<string>('')
const savingCorrection = ref(false)
const startCorrect = (m: any) => {
  correctingId.value = m.id
  correctionText.value = m.correctedAnswer || m.content
}
const cancelCorrect = () => {
  correctingId.value = ''
  correctionText.value = ''
}
const submitCorrect = async (m: any) => {
  if (!m.qaLogId) {
    showFailToast('当前回答缺少日志ID，请重新提问后再修正')
    return
  }
  const text = correctionText.value.trim()
  if (!text) return
  savingCorrection.value = true
  try {
    await searchApi.correctAnswer(m.qaLogId, text)
    chat.updateMessage(sessionId.value, m.id, { correctedAnswer: text })
    correctingId.value = ''
    showSuccessToast('修正已保存')
  } catch (e: any) {
    showFailToast(e?.message || '保存失败')
  } finally {
    savingCorrection.value = false
  }
}

const onAddTicket = async (msgId: string, ticketId: number) => {
  addingTicket.value[ticketId] = true
  try {
    await addTicketToMine(ticketId)
    showSuccessToast('已添加到我的工单')
    const msg = messages.value.find(m => m.id === msgId)
    const rt = msg?.recommendedTickets?.find(t => t.id === ticketId)
    if (rt) rt.added = true
  } catch (e: any) {
    showFailToast(e?.message || '添加失败')
  } finally {
    addingTicket.value[ticketId] = false
  }
}

const onPickFiles = (files: FileList | null) => {
  if (!files) return
  Array.from(files).forEach(f => imageList.value.push({ url: URL.createObjectURL(f), name: f.name, file: f }))
}
// FIX(内存)：移除/清空图片时释放 Blob URL，避免会话内累积泄漏
const removeImage = (i: number) => {
  const removed = imageList.value[i]
  imageList.value.splice(i, 1)
  if (removed?.url) URL.revokeObjectURL(removed.url)
}
const clearImages = () => {
  imageList.value.forEach(img => { if (img.url) URL.revokeObjectURL(img.url) })
  imageList.value = []
}
const onDrop = (e: DragEvent) => {
  e.preventDefault(); dragging.value = false
  onPickFiles(e.dataTransfer?.files || null)
}

const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

const scrollToBottom = async () => {
  await nextTick()
  scrollEl.value?.scrollTo({ top: scrollEl.value.scrollHeight, behavior: 'smooth' })
}

const onSend = async () => {
  const text = input.value.trim()
  if (!text && !imageList.value.length) return
  if (sending.value) return

  ensureSession()
  const sid = sessionId.value

  // 1) 投递用户消息（FIX12：将图片转为 base64 持久化，避免 blob URL 刷新/重登后失效）
  const userMsgId = nanoid()
  const userImages = imageList.value.length
    ? await Promise.all(imageList.value.map(i => fileToBase64(i.file)))
    : []
  chat.appendMessage(sid, {
    id: userMsgId,
    role: 'user',
    content: text,
    images: userImages,
    createdAt: Date.now()
  })

  // 2) 占位的 assistant 消息（loading）
  const aiId = nanoid()
  chat.appendMessage(sid, {
    id: aiId,
    role: 'assistant',
    content: '',
    sources: [],
    imageObservation: '',
    createdAt: Date.now()
  })

  // 3) 同步保留首张图发到后端，再清空输入区。
  // 连续追问时，如果本轮没上传图，则沿用上一轮图片，避免“1和2是什么”丢失图片上下文。
  const file = imageList.value[0]?.file || lastImageFile.value
  if (imageList.value[0]?.file) lastImageFile.value = imageList.value[0].file
  input.value = ''
  clearImages()
  if (text) store.push(text)
  store.clearDraft()  // FIX6 第 9 项：提交成功后清除草稿
  sending.value = true
  await scrollToBottom()

  // FIX6-resume M2：把异步流程包成 Promise 存到 store，切走时后台继续，切回时同步
  const job = (async () => {
    try {
      let acc = ''
      const res = await searchApi.multimodalSearchStream(
        { text, imageFile: file },
        { onToken: (delta) => { acc += delta; chat.updateMessage(sid, aiId, { content: acc }) } }
      )
      const sources: SourceItem[] = (res.hits || []).map((h, i) => ({
        id: h.id || `src-${i}`,
        docId: (h.meta as any)?.docId,
        title: h.title,
        snippet: h.snippet || '',
        hl: (h.meta as any)?.hl || h.snippet || '',
        similarity: h.similarity,
        page: (h.meta as any)?.page,
        images: (h.meta as any)?.images || []
      }))
      chat.updateMessage(sid, aiId, {
        content: res.summary || acc || '（后端未返回内容）',
        qaLogId: res.qaLogId,
        sources,
        imageObservation: res.imageObservation || '',
        recommendedTickets: res.recommendedTickets || []
      })
      expandedSources.value[aiId] = false
    } catch (e: any) {
      chat.updateMessage(sid, aiId, {
        error: e?.message || '检索失败，请稍后重试'
      })
    }
  })()
  store.setPending(aiId, job)
  try {
    await job
  } finally {
    // 仅当当前 pending 仍是这一条时清；否则可能已被另一条 onSend 覆盖
    if (store.pendingAssistantId === aiId) store.setPending('', null)
    sending.value = false
    await scrollToBottom()
  }
}

const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    onSend()
  }
}

const clearHistory = async () => {
  try {
    await showConfirmDialog({
      title: '清空当前对话?',
      message: '清空后将开始新会话，已保存的历史不受影响。'
    })
  } catch { return }
  sessionId.value = ''
  store.clearActiveSession()  // FIX6-resume M2：开启新对话时同时清掉活动会话
}

const toggleStar = () => { if (sessionId.value) chat.toggleStar(sessionId.value) }

// FIX7 续：跳转原文时把后端 snippet 的前后省略号剥掉，便于 Preview 页全文搜索定位
const stripDots = (s: string) => (s || '').replace(/^…+|…+$/g, '').trim()

// 监听 query.session 用于"打开历史"
watch(() => route.query.session, (v) => {
  if (typeof v === 'string' && chat.getSession(v)) {
    sessionId.value = v
  }
}, { immediate: true })

// 实时保存草稿：不能只依赖 onBeforeUnmount，KeepAlive/路由缓存场景可能不触发卸载
watch(input, (v) => {
  store.setDraft(v, imageList.value.map(i => i.file), imageList.value.map(i => i.url))
})

// FIX6-resume M2：跨路由保留检索表单草稿 + 活动会话
onMounted(() => {
  // 1) 优先 query.q（外部跳入）→ 自动发送一次
  if (input.value) {
    onSend()
  } else if (store.activeSessionId && chat.getSession(store.activeSessionId)) {
    sessionId.value = store.activeSessionId
    // 若有 pending 任务（切走时仍在进行），等待其完成以同步 UI
    if (store.pendingAssistantId && store.pendingPromise) {
      sending.value = true
      store.pendingPromise.finally(() => {
        sending.value = false
        scrollToBottom()
      })
    }
    scrollToBottom()
  }

  // 2) 始终恢复输入草稿（无论是否有活动会话）
  const d = store.draft
  if (!input.value && d.question) input.value = d.question
})
onBeforeUnmount(() => {
  if (input.value || imageList.value.length) {
    store.setDraft(
      input.value,
      imageList.value.map(i => i.file),
      imageList.value.map(i => i.url)
    )
  }
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!--
      共用的隐藏文件输入：放在 v-if/v-else 两个分支之外，避免会话开启后
      空态分支被销毁、fileInput.value 变成 undefined，导致底部输入条的
      Paperclip 按钮点击无效（用户反馈"打开对话后无法再上传新图片"）。
    -->
    <input ref="fileInput" type="file" accept="image/*" multiple class="hidden"
           @change="e => onPickFiles((e.target as HTMLInputElement).files)" />

    <!-- ─────────────── 初始空态：居中大输入（FIX3 第 6 项：去掉示例提示） ─────────────── -->
    <div v-if="!hasMessages" class="flex-1 flex items-center justify-center px-6 overflow-auto">
      <div class="w-full max-w-[720px] py-12">
        <div class="text-center mb-10">
          <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-accent to-accent-2 text-white mb-4">
            <Sparkles class="w-8 h-8" />
          </div>
          <h1 class="text-3xl font-bold text-primary">设备检修智能检索</h1>
          <div class="mt-2 text-sm text-text-2">基于多模态大模型 · 描述故障或上传现场照片，AI 会从知识库中给出答案</div>
        </div>

        <!-- 输入卡 -->
        <div
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop="onDrop"
          class="industrial-card p-3 shadow-float transition"
          :class="dragging ? 'border-accent ring-2 ring-accent/30' : ''">
          <textarea v-model="input" rows="3" @keydown="onKey"
                    placeholder="输入设备故障描述或检修问题…（Enter 发送，Shift+Enter 换行）"
                    class="w-full resize-none bg-transparent outline-none px-2 py-1 text-base leading-relaxed"></textarea>

          <!-- 图片缩略图 -->
          <div v-if="imageList.length" class="px-1 pb-2 flex flex-wrap gap-2">
            <div v-for="(img, i) in imageList" :key="i" class="relative w-14 h-14 rounded-btn overflow-hidden bg-bg group">
              <img :src="img.url" class="w-full h-full object-cover" />
              <button class="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-black/60 text-white flex items-center justify-center opacity-80"
                      @click="removeImage(i)">
                <X class="w-3 h-3" />
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between border-t border-border pt-2 mt-1">
            <button @click="fileInput?.click()"
                    class="h-9 w-9 rounded-full hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent" title="上传图片">
              <Paperclip class="w-4 h-4" />
            </button>
            <button @click="onSend" :disabled="sending || (!input.trim() && !imageList.length)"
                    class="h-9 px-4 rounded-btn bg-accent hover:bg-accent-2 text-white text-sm font-semibold flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed ai-shine">
              <Send class="w-4 h-4" />
              <span>发送</span>
            </button>
          </div>
        </div>

        <div class="mt-8 text-center text-xs text-text-2">
          数据来源：本地向量知识库（/api/chat/query）· 多模态支持图片输入
        </div>
      </div>
    </div>

    <!-- ─────────────── 对话状态：消息流 + 底部输入 ─────────────── -->
    <template v-else>
      <!-- 顶部：标题 + 收藏 + 清空 -->
      <header class="flex-shrink-0 px-6 py-3 border-b border-border bg-card flex items-center gap-3">
        <Sparkles class="w-4 h-4 text-accent" />
        <h2 class="text-sm font-semibold truncate max-w-md" :title="session?.title">{{ session?.title || '新对话' }}</h2>
        <span class="text-xs text-text-2 mono">{{ messages.filter(m => m.role === 'user').length }} 条提问</span>
        <button @click="toggleStar"
                class="ml-auto h-8 px-3 rounded-btn text-xs flex items-center gap-1"
                :class="session?.starred ? 'text-warning' : 'text-text-2 hover:bg-bg hover:text-warning'">
          <Star class="w-3.5 h-3.5" :fill="session?.starred ? 'currentColor' : 'none'" />
          {{ session?.starred ? '已收藏' : '收藏' }}
        </button>
        <button @click="clearHistory" class="h-8 px-3 rounded-btn text-xs text-text-2 hover:bg-bg hover:text-danger flex items-center gap-1">
          <Trash2 class="w-3.5 h-3.5" /> 新建对话
        </button>
      </header>

      <!-- 消息区 -->
      <div ref="scrollEl" class="flex-1 overflow-auto px-6 py-6">
        <div class="max-w-[860px] mx-auto space-y-6">
          <template v-for="m in messages" :key="m.id">
            <!-- 用户消息 -->
            <div v-if="m.role === 'user'" class="flex justify-end">
              <div class="flex items-start gap-3 max-w-[75%]">
                <div class="bg-accent text-white px-4 py-3 rounded-2xl rounded-tr-sm shadow-card">
                  <div v-if="m.images && m.images.length" class="grid grid-cols-3 gap-1.5 mb-2">
                    <img v-for="(u, j) in m.images" :key="j" :src="u" class="w-full aspect-square object-cover rounded-btn" />
                  </div>
                  <p v-if="m.content" class="text-sm leading-relaxed whitespace-pre-wrap break-words">{{ m.content }}</p>
                </div>
                <div class="w-8 h-8 rounded-full bg-bg border border-border flex items-center justify-center flex-shrink-0 text-text-2">
                  <UserIcon class="w-4 h-4" />
                </div>
              </div>
            </div>

            <!-- AI 回复 -->
            <div v-else class="flex justify-start">
              <div class="flex items-start gap-3 max-w-[85%]">
                <div class="w-8 h-8 rounded-full bg-ai/10 text-ai flex items-center justify-center flex-shrink-0">
                  <Bot class="w-4 h-4" />
                </div>
                <div class="flex-1 min-w-0">
                  <!-- 加载态 -->
                  <div v-if="!m.content && !m.error" class="industrial-card p-4 border-l-2 border-l-ai bg-ai/5">
                    <div class="flex items-center gap-2 text-text-2 text-sm">
                      <Loader class="w-4 h-4 animate-spin text-ai" />
                      正在检索知识库 · 大模型推理中…
                    </div>
                  </div>

                  <!-- 错误态 -->
                  <div v-else-if="m.error" class="industrial-card p-4 border-l-2 border-l-danger">
                    <div class="text-danger text-sm">⚠️ {{ m.error }}</div>
                  </div>

                  <!-- 正常回复 -->
                  <div v-else class="industrial-card p-4 border-l-2 border-l-ai">
                    <div class="text-xs text-text-2 mb-2 flex items-center gap-2">
                      <span class="px-1.5 py-0.5 rounded bg-ai/10 text-ai mono text-[10px]">multimodal-v2.4</span>
                      <span v-if="m.imageObservation">· 已分析图片</span>
                    </div>

                    <div v-if="m.imageObservation"
                         class="mb-3 px-3 py-2 rounded-btn bg-bg text-xs text-text-2 italic">
                      <ImageIcon class="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
                      图像观察：{{ m.imageObservation }}
                    </div>

                    <!-- markdown 渲染 -->
                    <div class="md-body" v-html="renderMarkdown(m.content)"></div>

                    <!-- 问答结果手动修正（赛题要求：支持手动标注与修正大模型输出） -->
                    <div v-if="m.correctedAnswer" class="mt-3 p-3 rounded-btn bg-warning/10 border border-warning/30">
                      <div class="text-xs text-warning font-semibold mb-1 flex items-center gap-1">
                        <Edit3 class="w-3.5 h-3.5" /> 已修正（用户标注）
                      </div>
                      <div class="md-body" v-html="renderMarkdown(m.correctedAnswer)"></div>
                    </div>
                    <div v-if="correctingId === m.id" class="mt-3 p-3 rounded-btn bg-bg border border-accent">
                      <div class="text-xs text-accent font-semibold mb-2">修正 AI 回答</div>
                      <textarea v-model="correctionText" rows="5"
                                class="w-full resize-y bg-card border border-border rounded-btn px-3 py-2 text-sm leading-relaxed outline-none"></textarea>
                      <div class="mt-2 flex justify-end gap-2">
                        <button @click="cancelCorrect" class="h-8 px-3 rounded-btn text-xs border border-border hover:bg-bg">取消</button>
                        <button @click="submitCorrect(m)" :disabled="savingCorrection"
                                class="h-8 px-3 rounded-btn bg-accent text-white text-xs flex items-center gap-1 disabled:opacity-40">
                          <Check class="w-3.5 h-3.5" /> 保存修正
                        </button>
                      </div>
                    </div>
                    <div v-if="!m.correctedAnswer && correctingId !== m.id" class="mt-3 pt-3 border-t border-border">
                      <button @click="startCorrect(m)" class="text-xs text-text-2 hover:text-accent flex items-center gap-1">
                        <Edit3 class="w-3.5 h-3.5" /> 修正回答
                      </button>
                    </div>

                    <!-- 推荐工单（FIX5 第 13 项：有则自动展示） -->
                    <div v-if="m.recommendedTickets && m.recommendedTickets.length"
                         class="mt-4 pt-3 border-t border-border">
                      <div class="text-xs font-semibold text-ai flex items-center gap-1.5 mb-2">
                        <ListChecks class="w-3.5 h-3.5" /> 相关作业工单
                      </div>
                      <div class="grid sm:grid-cols-2 gap-2">
                        <div v-for="rt in m.recommendedTickets" :key="rt.id"
                             class="px-3 py-2 rounded-btn bg-bg border border-border">
                          <div class="text-sm font-medium text-text truncate">{{ rt.fault || ('工单 #' + rt.id) }}</div>
                          <div class="text-[11px] text-text-2 mono mt-0.5 truncate">{{ rt.device }}</div>
                          <button v-if="!rt.added" @click="onAddTicket(m.id, rt.id)" :disabled="addingTicket[rt.id]"
                                  class="mt-2 h-7 px-3 rounded-btn border border-accent/40 text-accent text-xs font-semibold flex items-center gap-1 hover:bg-accent/10 disabled:opacity-60">
                            <Loader v-if="addingTicket[rt.id]" class="w-3 h-3 animate-spin" />
                            <UserPlus v-else class="w-3 h-3" /> 添加到我的工单
                          </button>
                          <div v-else class="mt-2 text-xs text-success flex items-center gap-1">
                            <Check class="w-3 h-3" /> 已在我的工单
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- 来源引用（FIX7 第 1 项：与本条消息强绑定 + 跳转原文） -->
                    <div v-if="m.sources && m.sources.length" class="mt-4 pt-3 border-t border-border">
                      <button @click="expandedSources[m.id] = !expandedSources[m.id]"
                              class="text-xs text-text-2 hover:text-accent flex items-center gap-1">
                        <BookOpen class="w-3.5 h-3.5" />
                        查看 {{ m.sources.length }} 条引用
                        <ChevronDown v-if="!expandedSources[m.id]" class="w-3.5 h-3.5" />
                        <ChevronUp v-else class="w-3.5 h-3.5" />
                      </button>
                      <ol v-if="expandedSources[m.id]" class="mt-2 space-y-1.5">
                        <li v-for="(h, hi) in m.sources" :key="h.id"
                            class="text-xs px-3 py-2 rounded-btn bg-bg border border-border">
                          <div class="flex items-start gap-2">
                            <span class="mono text-text-2">[{{ hi + 1 }}]</span>
                            <div class="flex-1 min-w-0">
                              <div class="font-medium text-text">{{ h.title }}</div>
                              <div v-if="h.snippet" class="mt-0.5 ref-snippet leading-relaxed line-clamp-3">{{ h.snippet }}</div>
                              <div v-if="h.images && h.images.length" class="mt-2 flex gap-2 flex-wrap">
                                <a v-for="img in h.images" :key="img.url" :href="img.url" target="_blank" class="block">
                                  <img :src="img.url" :alt="img.name || h.title" class="w-28 h-20 object-cover rounded border border-border bg-white" />
                                </a>
                              </div>
                              <div class="mt-1 flex items-center gap-3 flex-wrap">
                                <span v-if="h.page" class="mono text-text-2 text-[10px]">页码 {{ h.page }}</span>
                                <router-link v-if="h.docId"
                                             :to="{
                                               path: `/kb/preview/${h.docId}`,
                                               query: {
                                                 chunk: h.id,
                                                 hl: stripDots(h.hl || h.snippet),
                                                 page: h.page || undefined
                                               }
                                             }"
                                             class="ref-link text-[11px]">
                                  查看原文 →
                                </router-link>
                              </div>
                            </div>
                            <span v-if="typeof h.similarity === 'number'" class="mono text-text-2 flex-shrink-0">{{ Math.round(h.similarity * 100) }}%</span>
                          </div>
                        </li>
                      </ol>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 底部固定输入条 -->
      <div class="flex-shrink-0 border-t border-border bg-card px-6 py-3">
        <div class="max-w-[860px] mx-auto">
          <div
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop="onDrop"
            class="rounded-card border bg-card transition"
            :class="dragging ? 'border-accent ring-2 ring-accent/30' : 'border-border'">
            <div v-if="imageList.length" class="px-3 pt-2 flex flex-wrap gap-2">
              <div v-for="(img, i) in imageList" :key="i" class="relative w-12 h-12 rounded-btn overflow-hidden bg-bg group">
                <img :src="img.url" class="w-full h-full object-cover" />
                <button class="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-black/60 text-white flex items-center justify-center"
                        @click="removeImage(i)">
                  <X class="w-3 h-3" />
                </button>
              </div>
            </div>
            <div class="flex items-end gap-2 px-2 py-2">
              <button @click="fileInput?.click()"
                      class="h-9 w-9 rounded-full hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent flex-shrink-0" title="上传图片">
                <Paperclip class="w-4 h-4" />
              </button>
              <textarea v-model="input" rows="1" @keydown="onKey"
                        placeholder="继续追问…"
                        class="flex-1 resize-none bg-transparent outline-none px-1 py-2 text-sm leading-relaxed max-h-32"></textarea>
              <button @click="onSend" :disabled="sending || (!input.trim() && !imageList.length)"
                      class="h-9 w-9 rounded-full bg-accent hover:bg-accent-2 text-white flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0">
                <Send class="w-4 h-4" />
              </button>
            </div>
          </div>
          <div class="mt-1.5 text-[11px] text-text-2 text-center">
            AI 输出仅供参考，关键检修动作请以现场实测和官方手册为准
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
/* FIX7 第 1 项：引用面板样式 */
.ref-snippet {
  font-size: 12px;
  color: var(--color-text-2, #6B7280);
}
.ref-link {
  color: var(--color-ai, #00B7C2);
  text-decoration: underline;
}
.ref-link:hover {
  color: var(--color-accent-2, #FF7E36);
}
</style>

<style>
/* markdown 渲染基础样式（全局生效以便嵌套 v-html） */
.md-body { font-size: 15px; line-height: 1.7; color: var(--color-text, #1F2937); word-break: break-word; }
/* 深色模式下主输出文本提亮，避免灰字和卡片背景分不清 */
[data-theme='dark'] .md-body { color: #F1F5F9; }
[data-theme='dark'] .md-body p,
[data-theme='dark'] .md-body li,
[data-theme='dark'] .md-body td,
[data-theme='dark'] .md-body th { color: #F1F5F9; }
[data-theme='dark'] .md-body blockquote { color: #E5E7EB; background: rgba(255,255,255,0.06); }
[data-theme='dark'] .md-body code { color: #F1F5F9; background: rgba(255,255,255,0.14); }
[data-theme='dark'] .md-body th { background: rgba(255,255,255,0.06); }
[data-theme='dark'] .md-body th,
[data-theme='dark'] .md-body td { border-color: var(--color-border, #234373); }
[data-theme='dark'] .md-body hr { border-top-color: var(--color-border, #234373); }
.md-body h1, .md-body h2, .md-body h3, .md-body h4 { font-weight: 700; margin: 0.85em 0 0.35em; line-height: 1.35; }
.md-body h1 { font-size: 1.4em; }
.md-body h2 { font-size: 1.25em; }
.md-body h3 { font-size: 1.12em; }
.md-body h4 { font-size: 1em; }
.md-body p { margin: 0.4em 0; }
.md-body ul, .md-body ol { padding-left: 1.4em; margin: 0.4em 0; }
.md-body ul { list-style: disc; }
.md-body ol { list-style: decimal; }
.md-body li { margin: 0.2em 0; }
.md-body blockquote {
  margin: 0.6em 0; padding: 0.4em 0.9em;
  border-left: 3px solid var(--color-accent, #F26B1F);
  background: rgba(242, 107, 31, 0.05);
  color: var(--color-text-2, #6B7280);
}
.md-body code {
  background: rgba(0, 0, 0, 0.06);
  padding: 0.1em 0.35em; border-radius: 4px;
  font-family: 'Menlo', 'Consolas', monospace; font-size: 0.92em;
}
.md-body pre {
  background: #0B2545; color: #F5F7FA;
  padding: 0.85em 1em; border-radius: 8px; overflow-x: auto;
  margin: 0.6em 0; font-size: 0.9em; line-height: 1.55;
}
.md-body pre code { background: transparent; padding: 0; color: inherit; }
.md-body table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 0.95em; }
.md-body th, .md-body td { border: 1px solid var(--color-border, #E4E7ED); padding: 0.45em 0.7em; text-align: left; }
.md-body th { background: #F3F4F6; font-weight: 600; }
.md-body a { color: var(--color-ai, #00B7C2); text-decoration: underline; }
.md-body hr { border: 0; border-top: 1px solid var(--color-border, #E4E7ED); margin: 1em 0; }
</style>
