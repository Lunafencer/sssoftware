<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, ListChecks, ShieldCheck, Cog, User, BookOpen } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { hasPermission } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

/**
 * 移动端底部导航 —— FIX3 第 1 项：删除"工作台"入口；保留检索/指引/审核（仅审核员/管理员）/我的。
 */
const tabs = computed(() => {
  const role = user.role
  const all = [
    { path: '/search',          icon: Search,      label: '检索',  roles: undefined },
    { path: '/workflow',        icon: ListChecks,  label: '指引',  roles: undefined },
    { path: '/knowledge/upload', icon: BookOpen,   label: '上传',  roles: undefined },
    { path: '/audit/knowledge', icon: ShieldCheck, label: '审查',  roles: ['auditor', 'admin'] as const },
    { path: '/admin',           icon: Cog,         label: '系统',  roles: ['admin'] as const },
    { path: '/profile',         icon: User,        label: '我的',  roles: undefined }
  ]
  // 过滤可见
  const visible = all.filter(t => hasPermission(role, t.roles as any))
  // 仅取前 5 个,保证最后一项是"我的"
  if (visible.length <= 5) return visible
  return [...visible.filter(t => t.path !== '/profile').slice(0, 4),
          visible.find(t => t.path === '/profile')!]
})

const active = computed(() => tabs.value.findIndex(t => route.path.startsWith(t.path)))
</script>

<template>
  <nav class="h-14 flex-shrink-0 bg-card border-t border-border flex items-stretch safe-bottom z-30">
    <button v-for="(t, i) in tabs" :key="t.path"
            @click="router.push(t.path)"
            class="flex-1 flex flex-col items-center justify-center gap-0.5 relative transition active:scale-95"
            :class="active === i ? 'text-accent' : 'text-text-2'">
      <component :is="t.icon" class="w-5 h-5" :stroke-width="active === i ? 2.4 : 1.8" />
      <span class="text-[11px]" :class="active === i ? 'font-semibold' : ''">{{ t.label }}</span>
    </button>
  </nav>
</template>
