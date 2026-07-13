<script setup lang="ts">
/**
 * 历史详情页（FIX3 第 2.2 项）
 * - 完整渲染原消息流（markdown + 来源）
 * - 收藏切换 / 删除会话
 * - 点击"以此继续提问" → 跳到检索页并恢复同一会话
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatHistoryStore } from '@/stores/chatHistory'
import { renderMarkdown } from '@/utils/markdown'
import {
  ChevronLeft, Star, Trash2, MessageCircle, Bot, User as UserIcon, Image as ImageIcon,
  BookOpen, ChevronDown, ChevronUp
} from 'lucide-vue-next'
import { showConfirmDialog, showToast } from 'vant'
import { formatTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const chat = useChatHistoryStore()

const id = computed(() => String(route.params.id || ''))
const session = computed(() => chat.getSession(id.value))
const expanded = ref<Record<string, boolean>>({})

const back = () => router.push('/history')

const toggleStar = () => { if (session.value) chat.toggleStar(session.value.id) }

const remove = async () => {
  if (!session.value) return
  try {
    await showConfirmDialog({ title: '删除会话?', message: '删除后无法恢复。' })
  } catch { return }
  chat.removeSession(session.value.id)
  showToast({ type: 'success', message: '已删除' })
  back()
}

const continueChat = () => {
  if (!session.value) return
  router.push({ path: '/search', query: { session: session.value.id } })
}
</script>

<template>
  <div v-if="session" class="h-full flex flex-col bg-bg">
    <header class="flex-shrink-0 px-4 py-3 border-b border-border bg-card flex items-center gap-2">
      <button @click="back" class="w-9 h-9 rounded-btn hover:bg-bg flex items-center justify-center">
        <ChevronLeft class="w-5 h-5" />
      </button>
      <div class="flex-1 min-w-0">
        <div class="text-sm font-semibold truncate">{{ session.title }}</div>
        <div class="text-[11px] text-text-2 mono">
          {{ formatTime(new Date(session.createdAt).toISOString()) }}
          · {{ session.messages.filter(m => m.role === 'user').length }} 条提问
        </div>
      </div>
      <button @click="toggleStar"
              class="h-9 px-3 rounded-btn flex items-center gap-1 text-sm"
              :class="session.starred ? 'text-warning' : 'text-text-2 hover:bg-bg'">
        <Star class="w-4 h-4" :fill="session.starred ? 'currentColor' : 'none'" />
        {{ session.starred ? '已收藏' : '收藏' }}
      </button>
      <button @click="remove"
              class="h-9 px-3 rounded-btn text-text-2 hover:bg-bg hover:text-danger flex items-center gap-1 text-sm">
        <Trash2 class="w-4 h-4" />
      </button>
    </header>

    <div class="flex-1 overflow-auto px-4 py-5">
      <div class="max-w-[860px] mx-auto space-y-5">
        <template v-for="m in session.messages" :key="m.id">
          <div v-if="m.role === 'user'" class="flex justify-end">
            <div class="flex items-start gap-3 max-w-[80%]">
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

          <div v-else class="flex justify-start">
            <div class="flex items-start gap-3 max-w-[88%]">
              <div class="w-8 h-8 rounded-full bg-ai/10 text-ai flex items-center justify-center flex-shrink-0">
                <Bot class="w-4 h-4" />
              </div>
              <div class="flex-1 min-w-0">
                <div v-if="m.error" class="industrial-card p-4 border-l-2 border-l-danger">
                  <div class="text-danger text-sm">⚠️ {{ m.error }}</div>
                </div>
                <div v-else class="industrial-card p-4 border-l-2 border-l-ai">
                  <div v-if="m.imageObservation"
                       class="mb-3 px-3 py-2 rounded-btn bg-bg text-xs text-text-2 italic">
                    <ImageIcon class="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
                    图像观察：{{ m.imageObservation }}
                  </div>
                  <div class="md-body" v-html="renderMarkdown(m.content || '（无内容）')"></div>

                  <div v-if="m.sources && m.sources.length" class="mt-4 pt-3 border-t border-border">
                    <button @click="expanded[m.id] = !expanded[m.id]"
                            class="text-xs text-text-2 hover:text-accent flex items-center gap-1">
                      <BookOpen class="w-3.5 h-3.5" />
                      查看 {{ m.sources.length }} 条引用
                      <ChevronDown v-if="!expanded[m.id]" class="w-3.5 h-3.5" />
                      <ChevronUp v-else class="w-3.5 h-3.5" />
                    </button>
                    <ol v-if="expanded[m.id]" class="mt-2 space-y-1.5">
                      <li v-for="(h, hi) in m.sources" :key="h.id"
                          class="text-xs px-3 py-2 rounded-btn bg-bg border border-border">
                        <div class="flex items-start gap-2">
                          <span class="mono text-text-2">[{{ hi + 1 }}]</span>
                          <div class="flex-1 min-w-0">
                            <div class="font-medium">{{ h.title }}</div>
                            <div v-if="h.snippet" class="mt-0.5 text-text-2 leading-relaxed">{{ h.snippet }}</div>
                          </div>
                          <span v-if="typeof h.similarity === 'number'" class="mono text-text-2 flex-shrink-0">
                            {{ Math.round(h.similarity * 100) }}%
                          </span>
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

    <footer class="flex-shrink-0 border-t border-border bg-card px-4 py-3 flex justify-end gap-2">
      <button @click="back"
              class="h-10 px-4 rounded-btn border border-border text-sm flex items-center gap-1">
        返回列表
      </button>
      <button @click="continueChat"
              class="h-10 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 text-sm">
        <MessageCircle class="w-4 h-4" /> 以此继续提问
      </button>
    </footer>
  </div>
  <div v-else class="p-12 text-center text-text-2">
    会话不存在或已被删除。
    <button @click="back" class="text-accent hover:underline ml-2">返回列表</button>
  </div>
</template>
