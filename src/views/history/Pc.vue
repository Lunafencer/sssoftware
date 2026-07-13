<script setup lang="ts">
/**
 * 历史与收藏（FIX3 第 2 项）
 * - 列表来自 chatHistory store（按 userId 隔离）
 * - 列表项展示摘要预览（取前 4 条消息文本截断 60 字）
 * - 点击进入详情页，完整渲染 markdown + 来源
 * - 支持收藏 / 删除（二次确认）/ 全部清空
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { History, Star, Trash2, MessageCircle, ChevronRight, Search } from 'lucide-vue-next'
import { showConfirmDialog, showToast } from 'vant'
import { useDevice } from '@/composables/useDevice'
import { useChatHistoryStore, type ChatSession } from '@/stores/chatHistory'
import { formatTime, formatRelTime } from '@/utils/format'

const router = useRouter()
const { isPC } = useDevice()
const chat = useChatHistoryStore()

const tab = ref<'all' | 'starred'>('all')
const q = ref('')

const list = computed(() => {
  const base = tab.value === 'starred' ? chat.starredSessions : chat.sessions
  if (!q.value.trim()) return base
  const kw = q.value.trim().toLowerCase()
  return base.filter(s =>
    s.title.toLowerCase().includes(kw) ||
    s.messages.some(m => (m.content || '').toLowerCase().includes(kw))
  )
})

const open = (id: string) => router.push(`/history/${id}`)

const onToggleStar = (id: string, ev: MouseEvent) => {
  ev.stopPropagation()
  chat.toggleStar(id)
}

const onRemove = async (id: string, ev: MouseEvent) => {
  ev.stopPropagation()
  try {
    await showConfirmDialog({ title: '删除会话?', message: '删除后该会话的提问与 AI 回答都会一并清除。' })
  } catch { return }
  chat.removeSession(id)
  showToast({ type: 'success', message: '已删除' })
}

const onClearAll = async () => {
  if (!chat.sessions.length) return
  try {
    await showConfirmDialog({
      title: '清空全部历史?',
      message: `共 ${chat.sessions.length} 条会话将被清除（包括收藏），且无法恢复。`
    })
  } catch { return }
  chat.clearAll()
  showToast({ type: 'success', message: '已清空' })
}

// FIX12：历史列表中展示会话图片缩略图
const firstImages = (s: ChatSession) => {
  for (const m of s.messages) {
    if (m.role === 'user' && m.images && m.images.length) return m.images
  }
  return []
}
</script>

<template>
  <div :class="isPC ? 'p-6 max-w-5xl mx-auto' : 'p-3'">
    <header v-if="isPC" class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">历史与收藏</h1>
      <button v-if="chat.sessions.length" @click="onClearAll"
              class="h-9 px-3 rounded-btn border border-border text-sm flex items-center gap-1.5 hover:border-danger hover:text-danger">
        <Trash2 class="w-4 h-4" /> 清空全部
      </button>
    </header>

    <div class="flex gap-2 mb-3">
      <button v-for="t in [{k:'all',l:'全部',n:chat.sessions.length},{k:'starred',l:'收藏',n:chat.starredSessions.length}]"
              :key="t.k" @click="tab = t.k as any"
              :class="['h-10 rounded-btn text-sm flex items-center justify-center gap-1.5 px-4',
                       tab === t.k ? 'bg-accent text-white font-semibold' : 'bg-card border border-border text-text-2']">
        <component :is="t.k === 'starred' ? Star : History" class="w-4 h-4" />
        <span>{{ t.l }}</span>
        <span class="mono text-[10px] px-1 rounded" :class="tab === t.k ? 'bg-white/20' : 'bg-bg'">{{ t.n }}</span>
      </button>
      <div class="flex-1 relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
        <input v-model="q" placeholder="搜索会话标题或内容…"
               class="w-full h-10 pl-10 pr-3 rounded-btn border border-border bg-card text-sm outline-none focus:border-accent" />
      </div>
      <button v-if="!isPC && chat.sessions.length" @click="onClearAll"
              class="h-10 px-3 rounded-btn border border-border text-sm flex items-center justify-center text-text-2">
        <Trash2 class="w-4 h-4" />
      </button>
    </div>

    <div v-if="list.length" class="industrial-card overflow-hidden">
      <ul class="divide-y divide-border">
        <li v-for="s in list" :key="s.id"
            @click="open(s.id)"
            class="px-4 py-3 flex items-start gap-3 hover:bg-bg cursor-pointer active:bg-bg">
          <MessageCircle class="w-4 h-4 text-text-2 flex-shrink-0 mt-1" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <div class="text-sm font-semibold truncate flex-1">{{ s.title }}</div>
              <span class="text-[11px] text-text-2 mono flex-shrink-0">
                {{ isPC ? formatTime(new Date(s.updatedAt).toISOString()) : formatRelTime(new Date(s.updatedAt).toISOString()) }}
              </span>
            </div>
            <div class="text-xs text-text-2 mt-1 line-clamp-2 leading-relaxed">{{ chat.summaryOf(s) || '（暂无内容）' }}</div>
            <div v-if="firstImages(s).length" class="mt-2 flex items-center gap-2">
              <img v-for="(u, i) in firstImages(s).slice(0, 3)" :key="i" :src="u"
                   class="w-10 h-10 rounded-btn object-cover border border-border bg-bg flex-shrink-0" />
            </div>
            <div class="mt-1.5 flex items-center gap-2 text-[11px] text-text-2">
              <span class="mono">{{ s.messages.filter(m => m.role === 'user').length }} 条提问</span>
              <span class="mono">·</span>
              <span class="mono">{{ s.messages.filter(m => m.role === 'assistant').length }} 条回答</span>
            </div>
          </div>
          <button @click="onToggleStar(s.id, $event)"
                  class="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
                  :class="s.starred ? 'text-warning' : 'text-text-2 hover:text-warning'">
            <Star class="w-4 h-4" :fill="s.starred ? 'currentColor' : 'none'" />
          </button>
          <button @click="onRemove(s.id, $event)"
                  class="w-8 h-8 rounded flex items-center justify-center text-text-2 hover:text-danger flex-shrink-0">
            <Trash2 class="w-4 h-4" />
          </button>
          <ChevronRight class="w-4 h-4 text-text-2 mt-2 flex-shrink-0" />
        </li>
      </ul>
    </div>
    <div v-else class="industrial-card p-12 text-center text-text-2">
      <MessageCircle class="w-10 h-10 mx-auto opacity-40" />
      <div class="mt-3 text-sm">{{ tab === 'starred' ? '暂无收藏' : '暂无对话历史' }}</div>
      <div class="mt-1 text-xs">前往
        <button class="text-accent hover:underline" @click="router.push('/search')">知识检索</button>
        发起一次提问试试
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
