<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useTheme } from '@/composables/useTheme'
import { ROLE_LABEL, getVisibleMenuItems } from '@/utils/permission'
import {
  Search, ListChecks, BookOpen, ShieldCheck, Network, History, User,
  Moon, Sun, LogOut, Type, Minus, Plus, RotateCcw, HardHat, Sparkles,
  FileCheck2, Library, Users
} from 'lucide-vue-next'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const {
  theme, fontSize, glove,
  toggleDark, toggleContrast, toggleGlove,
  increaseFontSize, decreaseFontSize, resetFontSize,
  fontSizeLabel
} = useTheme()

// 图标按 MENU_ITEMS 当前真实路径配置；旧映射（/audit、/audit/knowledge、/admin/knowledge）
// 已不在菜单里，移除以免误以为生效
const ICONS: Record<string, any> = {
  '/search':            Search,        // 多模态检索
  '/workflow':          ListChecks,    // 作业指引
  '/kg':                Network,       // 知识图谱
  '/knowledge/browse':  Library,       // 知识库
  '/knowledge/upload':  BookOpen,      // 知识上传
  '/auditor/review':    ShieldCheck,   // 待审核
  '/auditor/knowledge': FileCheck2,    // 知识库管理
  '/admin/user':        Users,         // 用户管理
  '/history':           History,       // 历史与收藏
  '/profile':           User,          // 个人中心
}

const items = computed(() =>
  getVisibleMenuItems(user.role).map(it => ({ ...it, icon: ICONS[it.path] }))
)

const go = (p: string) => { router.push(p); emit('update:open', false) }
const onLogout = async () => { await user.logout(); router.push('/login') }
</script>

<template>
  <transition name="drawer">
    <div v-if="open" class="fixed inset-0 z-50 flex" @click.self="emit('update:open', false)">
      <div class="absolute inset-0 bg-black/45"></div>
      <div class="relative w-[80%] max-w-xs h-full bg-card flex flex-col shadow-float">
        <!-- 用户头 -->
        <div class="bg-primary text-on-dark p-4 safe-top">
          <div class="flex items-center gap-3 mt-2">
            <div class="w-12 h-12 rounded-full bg-accent flex items-center justify-center text-lg font-bold">
              {{ (user.info?.name || '游').slice(0, 1) }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-semibold truncate">{{ user.info?.name || '访客' }}</div>
              <div class="text-xs opacity-70 truncate">{{ ROLE_LABEL[user.role] }}</div>
            </div>
          </div>
        </div>

        <nav class="flex-1 overflow-auto p-2">
          <button v-for="it in items" :key="it.path"
                  @click="go(it.path)"
                  class="w-full h-12 px-3 rounded-btn flex items-center gap-3 text-base"
                  :class="route.path.startsWith(it.path) ? 'bg-accent/10 text-accent font-semibold' : 'text-text'">
            <component :is="it.icon" class="w-5 h-5" />
            <span class="flex-1 text-left">{{ it.label }}</span>
            <span v-if="it.badge"
                  class="px-1.5 h-5 min-w-5 rounded-full bg-accent text-white text-[11px] font-semibold flex items-center justify-center mono">
              {{ it.badge }}
            </span>
          </button>

          <!-- ======= 显示设置 ======= -->
          <div class="mt-3 px-3 pt-3 border-t border-border">
            <div class="text-xs text-text-2 mb-2 px-1">显示设置</div>

            <!-- 字号调节 -->
            <div class="flex items-center justify-between p-3 rounded-btn bg-bg mb-2">
              <div class="flex items-center gap-2 text-sm">
                <Type class="w-4 h-4 text-text-2" />
                <span>字号</span>
                <span class="text-xs text-text-2 mono">{{ fontSizeLabel }}</span>
              </div>
              <div class="flex items-center gap-1">
                <button class="w-8 h-8 rounded-btn border border-border flex items-center justify-center active:bg-bg" @click="decreaseFontSize">
                  <Minus class="w-4 h-4" />
                </button>
                <button class="w-8 h-8 rounded-btn border border-border flex items-center justify-center active:bg-bg" @click="resetFontSize" title="重置">
                  <RotateCcw class="w-3.5 h-3.5" />
                </button>
                <button class="w-8 h-8 rounded-btn border border-border flex items-center justify-center active:bg-bg" @click="increaseFontSize">
                  <Plus class="w-4 h-4" />
                </button>
              </div>
            </div>

            <button class="w-full h-12 px-3 flex items-center gap-3 rounded-btn hover:bg-bg" @click="toggleDark">
              <Moon v-if="theme === 'light'" class="w-5 h-5" />
              <Sun v-else class="w-5 h-5" />
              <span class="flex-1 text-left text-sm">深色模式</span>
              <span class="text-xs text-text-2">{{ theme === 'dark' ? '已开启' : '关闭' }}</span>
            </button>

            <button class="w-full h-12 px-3 flex items-center gap-3 rounded-btn hover:bg-bg" @click="toggleContrast">
              <Sparkles class="w-5 h-5" />
              <span class="flex-1 text-left text-sm">高对比度</span>
              <span class="text-xs text-text-2">{{ theme === 'contrast' ? '已开启' : '关闭' }}</span>
            </button>

            <button class="w-full h-12 px-3 flex items-center gap-3 rounded-btn hover:bg-bg" @click="toggleGlove">
              <HardHat class="w-5 h-5" />
              <span class="flex-1 text-left text-sm">手套模式</span>
              <span class="text-xs text-text-2">{{ glove === 'on' ? '已开启' : '关闭' }}</span>
            </button>
          </div>
        </nav>

        <div class="border-t border-border p-2 safe-bottom">
          <button class="w-full h-12 px-3 flex items-center gap-3 rounded-btn hover:bg-bg text-danger" @click="onLogout">
            <LogOut class="w-5 h-5" /> 退出登录
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.drawer-enter-active, .drawer-leave-active { transition: opacity .25s; }
.drawer-enter-active .relative, .drawer-leave-active .relative { transition: transform .28s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .relative, .drawer-leave-to .relative { transform: translateX(-100%); }
</style>
