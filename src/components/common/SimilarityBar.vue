<script setup lang="ts">
import { computed } from 'vue'
defineProps<{ value: number; size?: 'sm' | 'md' }>()
</script>

<template>
  <div class="flex items-center gap-2 w-full">
    <div class="flex-1 bg-border rounded-full overflow-hidden" :class="size === 'sm' ? 'h-1.5' : 'h-2'">
      <div class="h-full bg-accent transition-[width] duration-500"
           :style="{ width: (Math.max(0, Math.min(1, value)) * 100) + '%' }"></div>
    </div>
    <span class="mono text-xs tabular-nums w-10 text-right" :class="value >= 0.8 ? 'text-accent font-semibold' : 'text-text-2'">
      {{ Math.round(Math.max(0, Math.min(1, value)) * 100) }}%
    </span>
  </div>
</template>
