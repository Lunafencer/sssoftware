<script setup lang="ts">
import TopBar from '@/components/pc/TopBar.vue'
import SideNav from '@/components/pc/SideNav.vue'
</script>

<template>
  <div class="h-screen flex flex-col bg-bg overflow-hidden">
    <TopBar />
    <div class="flex-1 flex overflow-hidden">
      <SideNav />
      <main class="flex-1 overflow-auto">
        <slot />
      </main>
    </div>
    <footer class="h-8 px-4 flex items-center justify-between bg-primary text-on-dark text-xs flex-shrink-0">
      <span class="opacity-70">© 2026 设备检修知识检索与作业系统</span>
      <span class="opacity-70 mono">Asia/Shanghai · v0.1.0</span>
    </footer>
  </div>
</template>
