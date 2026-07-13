import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const aiAssistantOpen = ref(false)
  const sideDrawerOpen = ref(false)
  const settingsDrawerOpen = ref(false)

  return { aiAssistantOpen, sideDrawerOpen, settingsDrawerOpen }
})
