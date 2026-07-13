<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Sun, Moon, Settings, LogOut, User,
  Type, Minus, Plus, RotateCcw, HardHat, Sparkles, Check
} from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { useTheme } from '@/composables/useTheme'
import { ROLE_LABEL } from '@/utils/permission'

const router = useRouter()
const user = useUserStore()
const {
  theme, fontSize, glove, fontSizeLabel,
  toggleDark, toggleContrast, toggleGlove,
  increaseFontSize, decreaseFontSize, resetFontSize
} = useTheme()

const showUser = ref(false)
const showSettings = ref(false)

const onLogout = async () => {
  await user.logout()
  router.push('/login')
}

const closeAll = () => { showUser.value = false; showSettings.value = false }
const toggleSettings = () => {
  showUser.value = false
  showSettings.value = !showSettings.value
}
const toggleUser = () => {
  showSettings.value = false
  showUser.value = !showUser.value
}
</script>

<template>
  <header class="h-14 flex-shrink-0 bg-primary text-on-dark flex items-center px-4 gap-4 shadow-card relative z-30"
          @click="closeAll">
    <!-- Logo -->
    <div class="flex items-center gap-3" @click.stop>
      <div class="w-8 h-8 rounded bg-gradient-to-br from-accent to-accent-2 flex items-center justify-center">
        <svg viewBox="0 0 24 24" class="w-5 h-5 text-white"><path fill="currentColor" d="M12 4l8 4.5v7L12 20l-8-4.5v-7L12 4zm0 2.3L6 9.7v4.6l6 3.4l6-3.4V9.7L12 6.3z"/></svg>
      </div>
      <div class="font-semibold tracking-wide">检修助手</div>
    </div>

    <!-- 工具区 -->
    <div class="flex items-center gap-2 ml-auto" @click.stop>
      <!-- 显示设置统一入口 -->
      <div class="relative">
        <button class="w-9 h-9 rounded-btn hover:bg-white/10 flex items-center justify-center"
                :class="showSettings ? 'bg-white/15' : ''"
                @click="toggleSettings" title="显示设置">
          <Settings class="w-4 h-4" />
        </button>
        <transition name="fade">
          <div v-if="showSettings"
               class="absolute right-0 top-full mt-2 w-72 industrial-card text-text shadow-float overflow-hidden">
            <div class="p-3 border-b border-border">
              <div class="font-semibold text-sm">显示设置</div>
              <div class="text-xs text-text-2 mt-0.5">设置自动保存到本地</div>
            </div>

            <!-- 字号 -->
            <div class="p-3 border-b border-border">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2 text-sm font-medium">
                  <Type class="w-4 h-4 text-text-2" />
                  字号档位
                </div>
                <span class="text-xs text-text-2 mono">{{ fontSizeLabel }}({{ fontSize }})</span>
              </div>
              <div class="flex items-center gap-2">
                <button class="flex-1 h-9 rounded-btn border border-border hover:bg-bg flex items-center justify-center gap-1 text-sm"
                        @click="decreaseFontSize">
                  <Minus class="w-3.5 h-3.5" /> A-
                </button>
                <button class="flex-1 h-9 rounded-btn border border-border hover:bg-bg flex items-center justify-center gap-1 text-sm"
                        @click="resetFontSize">
                  <RotateCcw class="w-3.5 h-3.5" /> 重置
                </button>
                <button class="flex-1 h-9 rounded-btn border border-border hover:bg-bg flex items-center justify-center gap-1 text-sm"
                        @click="increaseFontSize">
                  A+ <Plus class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <!-- 主题 -->
            <button class="w-full h-11 px-3 flex items-center gap-2 hover:bg-bg text-sm"
                    @click="toggleDark">
              <Moon v-if="theme !== 'dark'" class="w-4 h-4" />
              <Sun  v-else class="w-4 h-4 text-warning" />
              <span class="flex-1 text-left">深色模式</span>
              <Check v-if="theme === 'dark'" class="w-4 h-4 text-accent" />
            </button>

            <button class="w-full h-11 px-3 flex items-center gap-2 hover:bg-bg text-sm"
                    @click="toggleContrast">
              <Sparkles class="w-4 h-4" />
              <span class="flex-1 text-left">高对比度(车间户外)</span>
              <Check v-if="theme === 'contrast'" class="w-4 h-4 text-accent" />
            </button>

            <button class="w-full h-11 px-3 flex items-center gap-2 hover:bg-bg text-sm border-t border-border"
                    @click="toggleGlove">
              <HardHat class="w-4 h-4" />
              <span class="flex-1 text-left">手套模式(按钮放大 1.3×)</span>
              <Check v-if="glove === 'on'" class="w-4 h-4 text-accent" />
            </button>
          </div>
        </transition>
      </div>

      <div class="relative">
        <button class="flex items-center gap-2 h-9 px-2 rounded-btn hover:bg-white/10"
                :class="showUser ? 'bg-white/15' : ''"
                @click="toggleUser">
          <div class="w-7 h-7 rounded-full bg-accent flex items-center justify-center text-white text-xs font-semibold">
            {{ (user.info?.name || '游').slice(0, 1) }}
          </div>
          <span class="text-sm">{{ user.info?.name || '访客' }}</span>
        </button>
        <transition name="fade">
          <div v-if="showUser"
               class="absolute right-0 top-full mt-2 w-56 industrial-card text-text shadow-float overflow-hidden">
            <div class="p-3 border-b border-border">
              <div class="font-semibold">{{ user.info?.name }}</div>
              <div class="text-xs text-text-2 mt-0.5">{{ ROLE_LABEL[user.role] }}</div>
            </div>
            <button @click="router.push('/profile'); showUser = false"
                    class="w-full text-left px-3 h-10 hover:bg-bg flex items-center gap-2 text-sm">
              <User class="w-4 h-4" /> 个人中心
            </button>
            <button @click="onLogout"
                    class="w-full text-left px-3 h-10 hover:bg-bg flex items-center gap-2 text-sm text-danger">
              <LogOut class="w-4 h-4" /> 退出登录
            </button>
          </div>
        </transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .15s, transform .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
