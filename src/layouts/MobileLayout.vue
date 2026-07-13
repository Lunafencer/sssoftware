<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import MobileAppBar from '@/components/mobile/MobileAppBar.vue'
import BottomTabBar from '@/components/mobile/BottomTabBar.vue'
import MobileSideDrawer from '@/components/mobile/MobileSideDrawer.vue'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const ui = useUiStore()

const title = computed(() => route.meta?.title as string || '设备检修助手')
</script>

<template>
  <div class="h-screen flex flex-col bg-bg">
    <MobileAppBar :title="title" @menu="ui.sideDrawerOpen = true" />
    <main class="flex-1 overflow-auto">
      <slot />
    </main>
    <BottomTabBar />
    <MobileSideDrawer v-model:open="ui.sideDrawerOpen" />
  </div>
</template>
