<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ value: number; label?: string; size?: number }>()
const size = computed(() => props.size ?? 56)
const pct = computed(() => Math.round(Math.max(0, Math.min(1, props.value)) * 100))
</script>

<template>
  <div class="inline-flex items-center gap-2">
    <div class="gauge-ring flex items-center justify-center"
         :style="{ width: size + 'px', height: size + 'px', '--p': pct }">
      <div class="bg-card rounded-full flex items-center justify-center mono text-xs font-semibold"
           :style="{ width: (size - 12) + 'px', height: (size - 12) + 'px' }">
        {{ pct }}%
      </div>
    </div>
    <span v-if="label" class="text-text-2 text-xs">{{ label }}</span>
  </div>
</template>
