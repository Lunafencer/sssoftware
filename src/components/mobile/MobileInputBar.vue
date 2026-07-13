<script setup lang="ts">
/**
 * 移动端检索输入栏
 * - 仅保留：拍照/相册附件 + 文本输入 + 发送
 * - 不再渲染语音输入按钮（按用户要求移除）
 *
 * 对外契约（保持与原版兼容，方便其他地方继续调用）：
 *   props.modelValue / props.images        v-model 双绑
 *   emit('update:modelValue', text)
 *   emit('update:images', urls)            预览缩略图（Blob URL）
 *   emit('pick', files: File[])            传给父组件用作真实上传（multimodalSearch 需要 File）
 *   emit('send')                           点击发送按钮
 */
import { ref } from 'vue'
import { Camera, Send, X } from 'lucide-vue-next'

const props = defineProps<{ modelValue: string; images: string[] }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'update:images', v: string[]): void
  (e: 'pick', files: File[]): void
  (e: 'send'): void
}>()

const fileInput = ref<HTMLInputElement>()

const onPick = (ev: Event) => {
  const target = ev.target as HTMLInputElement
  const files = target.files
  if (!files || !files.length) return
  const picked = Array.from(files)
  // 缩略图预览 URL
  const next = [...props.images]
  for (const f of picked) next.push(URL.createObjectURL(f))
  emit('update:images', next)
  // 真实 File 对象交给父组件（搜索调用需要 File 而不是 Blob URL）
  emit('pick', picked)
  // 清空 input 让连续选择同一张图也能触发 change
  target.value = ''
}

const removeImg = (i: number) => {
  const removed = props.images[i]
  const n = [...props.images]
  n.splice(i, 1)
  // FIX(内存)：释放被移除图片的 Blob URL，避免长会话累积内存
  if (removed) URL.revokeObjectURL(removed)
  emit('update:images', n)
}
</script>

<template>
  <div class="flex-shrink-0 bg-card border-t border-border safe-bottom">
    <!-- 缩略图横滑条 -->
    <div v-if="images.length" class="flex gap-2 overflow-x-auto px-3 pt-2 hide-scrollbar">
      <div v-for="(url, i) in images" :key="i"
           class="relative w-16 h-16 flex-shrink-0 rounded-btn overflow-hidden bg-bg">
        <img :src="url" class="w-full h-full object-cover" />
        <button class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center"
                @click="removeImg(i)">
          <X class="w-3 h-3" />
        </button>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="h-20 flex items-center px-3 gap-2">
      <!-- 附件上传（拍照 / 相册） -->
      <button @click="fileInput?.click()"
              class="w-14 h-14 rounded-full bg-primary text-white flex items-center justify-center flex-shrink-0 active:scale-95 transition">
        <Camera class="w-6 h-6" />
      </button>
      <!--
        注意：不能用 class="hidden" (display:none) ——
        在部分移动 WebView（旧版 Android WebView、iOS WKWebView）里，display:none
        的 <input type=file> 会无法响应 .click()；尤其在父组件重新挂载之后只能触发一次。
        改用 "可视化隐藏" 写法：保留在布局流中但不可见、不可点。
      -->
      <input ref="fileInput" type="file" accept="image/*" multiple
             class="visually-hidden" @change="onPick" />

      <!-- 文本输入 -->
      <div class="flex-1 h-12 px-4 rounded-pill bg-bg flex items-center">
        <input :value="modelValue"
               @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
               @keydown.enter="emit('send')"
               placeholder="描述故障…"
               class="flex-1 bg-transparent outline-none text-base" />
      </div>

      <!-- 发送 -->
      <button @click="emit('send')"
              class="w-12 h-12 rounded-full bg-accent text-white flex items-center justify-center flex-shrink-0 active:scale-95 transition shadow-card">
        <Send class="w-5 h-5" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.hide-scrollbar::-webkit-scrollbar { display: none; }
.hide-scrollbar { scrollbar-width: none; }
/* 可访问性友好的"隐藏"：保留在布局流，避免 display:none 的 file input
   在移动 WebView 上 .click() 失效。 */
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
  opacity: 0;
  pointer-events: none;
}
</style>
