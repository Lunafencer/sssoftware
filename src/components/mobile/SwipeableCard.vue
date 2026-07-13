<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  leftLabel?: string
  rightLabel?: string
  leftColor?: string
  rightColor?: string
}>()
const emit = defineEmits<{ (e: 'swipeLeft'): void; (e: 'swipeRight'): void }>()

const dx = ref(0)
const startX = ref(0)
const dragging = ref(false)

const onStart = (e: PointerEvent) => { startX.value = e.clientX; dragging.value = true }
const onMove = (e: PointerEvent) => {
  if (!dragging.value) return
  dx.value = e.clientX - startX.value
}
const onEnd = () => {
  dragging.value = false
  if (dx.value < -90) { if ('vibrate' in navigator) navigator.vibrate(40); emit('swipeLeft') }
  else if (dx.value > 90) { if ('vibrate' in navigator) navigator.vibrate(40); emit('swipeRight') }
  dx.value = 0
}
</script>

<template>
  <div class="relative overflow-hidden rounded-card">
    <!-- 背景操作 -->
    <div v-if="dx > 0" class="absolute inset-y-0 left-0 flex items-center px-4 font-semibold text-white"
         :style="{ background: leftColor || 'var(--color-success)' }">
      {{ leftLabel || '通过' }}
    </div>
    <div v-if="dx < 0" class="absolute inset-y-0 right-0 flex items-center px-4 font-semibold text-white"
         :style="{ background: rightColor || 'var(--color-danger)' }">
      {{ rightLabel || '驳回' }}
    </div>
    <div class="industrial-card relative bg-card transition-transform"
         :class="dragging ? '' : 'duration-200'"
         :style="{ transform: `translateX(${dx}px)` }"
         @pointerdown="onStart" @pointermove="onMove" @pointerup="onEnd" @pointercancel="onEnd">
      <slot />
    </div>
  </div>
</template>
