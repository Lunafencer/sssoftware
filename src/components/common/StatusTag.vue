<script setup lang="ts">
import type { SourceType } from '@/api/search'
import { Book, FileText, Network, Tag } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ type?: SourceType; label?: string }>()

const meta = computed(() => {
  switch (props.type) {
    case 'manual': return { icon: Book,    label: '手册', cls: 'bg-primary/10 text-primary' }
    case 'case':   return { icon: FileText, label: '案例', cls: 'bg-accent/10 text-accent' }
    case 'graph':  return { icon: Network, label: '图谱', cls: 'bg-ai/10 text-ai' }
    default:       return { icon: Tag,     label: props.label || '标签', cls: 'bg-text-2/10 text-text-2' }
  }
})
</script>

<template>
  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium" :class="meta.cls">
    <component :is="meta.icon" class="w-3 h-3" />
    {{ props.label || meta.label }}
  </span>
</template>
