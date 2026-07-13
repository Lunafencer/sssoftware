<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDevice } from '@/composables/useDevice'
import PCLayout from '@/layouts/PCLayout.vue'
import MobileLayout from '@/layouts/MobileLayout.vue'

const route = useRoute()
const { isPC } = useDevice()

const layout = computed(() => route.meta?.layout || 'blank')
</script>

<template>
  <template v-if="layout === 'blank'">
    <router-view />
  </template>
  <template v-else>
    <PCLayout v-if="isPC">
      <router-view />
    </PCLayout>
    <MobileLayout v-else>
      <router-view />
    </MobileLayout>
  </template>
</template>
