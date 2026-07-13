<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps<{ title?: string; desc?: string; actionLabel?: string }>()
defineEmits<{ (e: 'action'): void }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-12 text-center">
    <div class="w-20 h-20 rounded-full bg-border/50 flex items-center justify-center mb-4">
      <Inbox class="w-10 h-10 text-text-2" />
    </div>
    <div class="font-medium text-text">{{ title || '暂无数据' }}</div>
    <div class="text-text-2 text-sm mt-1 max-w-xs">{{ desc || '该模块占位中,接入后端后将自动填充内容' }}</div>
    <button v-if="actionLabel"
            class="mt-4 px-4 h-9 rounded-btn bg-accent text-white text-sm font-medium hover:bg-accent-2 transition"
            @click="$emit('action')">
      {{ actionLabel }}
    </button>
  </div>
</template>
