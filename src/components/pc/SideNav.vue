<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Search, ListChecks, BookOpen, ShieldCheck, Network, History, User,
  ChevronRight, FileCheck2, Library, Users
} from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { getVisibleMenuItems } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

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

const isActive = (p: string) => route.path === p || route.path.startsWith(p + '/')
</script>

<template>
  <aside class="w-[220px] flex-shrink-0 bg-card border-r border-border flex flex-col">
    <nav class="p-3 space-y-0.5 flex-1 overflow-auto">
      <button v-for="it in items" :key="it.path"
              @click="router.push(it.path)"
              :class="[
                'w-full h-10 px-3 rounded-btn flex items-center gap-3 text-sm transition group',
                isActive(it.path)
                  ? 'bg-accent/10 text-accent font-semibold'
                  : 'text-text hover:bg-bg'
              ]">
        <component :is="it.icon" class="w-4 h-4" :class="isActive(it.path) ? '' : 'text-text-2 group-hover:text-text'" />
        <span class="flex-1 text-left">{{ it.label }}</span>
        <span v-if="it.badge"
              class="px-1.5 h-5 min-w-5 rounded-full bg-accent text-white text-xs font-semibold flex items-center justify-center mono">
          {{ it.badge }}
        </span>
        <ChevronRight v-if="isActive(it.path)" class="w-3.5 h-3.5" />
      </button>
    </nav>
  </aside>
</template>
