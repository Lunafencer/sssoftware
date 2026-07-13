<script setup lang="ts">
/**
 * AI 助手浮动按钮 + 抽屉。检索页右下角悬浮使用。
 */
import { ref } from 'vue'
import { Sparkles, X, Send } from 'lucide-vue-next'
import { useStreamText } from '@/composables/useStreamText'

const open = ref(false)
const input = ref('')
const messages = ref<{ role: 'user' | 'ai'; text: string }[]>([
  { role: 'ai', text: '你好,我是检修助手 AI。可以追问刚才的检索结果,或描述新现象。' }
])
const { display, run, done } = useStreamText(20)

const send = () => {
  if (!input.value.trim()) return
  messages.value.push({ role: 'user', text: input.value })
  const reply = `根据您描述的现象「${input.value}」,结合知识库:可能与轴承润滑或对中偏差有关。建议先按 SOP §4.3 流程停机检查,并在驱动端进行温度与振动复测。`
  input.value = ''
  messages.value.push({ role: 'ai', text: '' })
  run(reply)
}
</script>

<template>
  <button class="fixed bottom-12 right-8 z-40 w-14 h-14 rounded-full bg-ai text-white flex items-center justify-center shadow-float hover:scale-105 transition ai-shine"
          @click="open = !open" title="AI 助手">
    <Sparkles class="w-6 h-6" />
  </button>

  <transition name="slide">
    <div v-if="open"
         class="fixed bottom-28 right-8 z-40 w-96 h-[520px] industrial-card flex flex-col shadow-float overflow-hidden">
      <header class="h-12 px-4 flex items-center justify-between bg-primary text-on-dark">
        <div class="flex items-center gap-2">
          <Sparkles class="w-4 h-4 text-ai" />
          <span class="font-semibold">检修助手 AI</span>
        </div>
        <button @click="open = false" class="opacity-70 hover:opacity-100">
          <X class="w-4 h-4" />
        </button>
      </header>
      <div class="flex-1 p-4 overflow-auto space-y-3">
        <div v-for="(m, i) in messages" :key="i" class="flex" :class="m.role === 'user' ? 'justify-end' : 'justify-start'">
          <div class="max-w-[80%] px-3 py-2 rounded-card text-sm leading-relaxed"
               :class="m.role === 'user' ? 'bg-accent text-white' : 'bg-bg'">
            <template v-if="m.role === 'ai' && i === messages.length - 1 && !done">
              <span :class="!done ? 'typing-cursor' : ''">{{ display }}</span>
            </template>
            <template v-else>{{ m.role === 'ai' && i === messages.length - 1 ? display : m.text }}</template>
          </div>
        </div>
      </div>
      <div class="p-3 border-t border-border flex gap-2">
        <input v-model="input" @keydown.enter="send"
               placeholder="继续向 AI 提问…"
               class="flex-1 h-9 px-3 rounded-btn bg-bg border border-border text-sm outline-none focus:border-accent" />
        <button @click="send" class="w-9 h-9 rounded-btn bg-accent text-white flex items-center justify-center hover:bg-accent-2">
          <Send class="w-4 h-4" />
        </button>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: all .25s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(10px); }
</style>
