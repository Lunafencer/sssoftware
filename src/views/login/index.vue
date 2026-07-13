<script setup lang="ts">
import { useDevice } from '@/composables/useDevice'
import Pc from './Pc.vue'
import Mobile from './Mobile.vue'
const { isPC } = useDevice()
</script>
<template>
  <component :is="isPC ? Pc : Mobile" />
</template>
