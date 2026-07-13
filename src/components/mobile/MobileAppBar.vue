<script setup lang="ts">
import { Menu } from 'lucide-vue-next'
defineProps<{ title: string }>()
defineEmits<{ (e: 'menu'): void }>()
</script>

<template>
  <header class="h-12 flex-shrink-0 bg-primary text-on-dark flex items-center px-3 gap-2 safe-top relative z-30">
    <button @click="$emit('menu')" class="w-10 h-10 -ml-2 flex items-center justify-center" aria-label="菜单">
      <Menu class="w-5 h-5" />
    </button>
    <div class="flex-1 text-center font-semibold text-base truncate">{{ title }}</div>
    <div class="w-10 h-10 flex-shrink-0"></div>
  </header>
</template>
