<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listUsers, backendRoleToFrontend, type SysUser } from '@/api/admin'
import { Lock, Users, Loader, AlertTriangle } from 'lucide-vue-next'
import { ROLE_LABEL } from '@/utils/permission'
import { formatTime } from '@/utils/format'

const users = ref<SysUser[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    users.value = await listUsers()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="p-3 space-y-3">
    <div class="industrial-card p-4 border-l-4 border-l-warning bg-warning/5 flex items-start gap-3">
      <Lock class="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
      <div>
        <div class="font-semibold text-text">移动端只读模式</div>
        <div class="text-xs text-text-2 mt-1">出于安全考虑，管理操作请前往 PC 端；此处仅展示用户列表。</div>
      </div>
    </div>

    <div class="industrial-card overflow-hidden">
      <div class="px-4 h-11 flex items-center gap-2 border-b border-border font-semibold text-sm">
        <Users class="w-4 h-4 text-accent" /> 用户列表（只读）
      </div>

      <div v-if="loading" class="py-8 text-center text-text-2">
        <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
        <div class="mt-2 text-xs">加载中…</div>
      </div>
      <div v-else-if="error && !users.length" class="py-8 text-center text-warning">
        <AlertTriangle class="w-6 h-6 mx-auto" />
        <div class="mt-2 text-xs">{{ error }}</div>
      </div>
      <div v-else-if="!users.length" class="py-8 text-center text-text-2 text-xs">
        暂无用户
      </div>
      <ul v-else class="divide-y divide-border">
        <li v-for="u in users" :key="u.id" class="px-4 py-3 flex items-center gap-3">
          <div class="w-8 h-8 rounded-full bg-bg flex items-center justify-center text-sm font-semibold">
            {{ (u.username || '?').slice(0, 1) }}
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-sm truncate flex items-center gap-1.5">
              {{ u.username }}
              <span v-if="u.isDefaultAdmin"
                    class="text-[10px] px-1 py-0.5 rounded bg-warning/10 text-warning flex items-center gap-0.5 flex-shrink-0">
                <Lock class="w-2.5 h-2.5" /> 默认管理员
              </span>
            </div>
            <div class="text-xs text-text-2 truncate">
              {{ ROLE_LABEL[backendRoleToFrontend(u.role)] }}
              <span v-if="u.createdAt" class="ml-1">· {{ formatTime(u.createdAt) }}</span>
            </div>
          </div>
          <span class="text-[10px] px-1.5 py-0.5 rounded mono"
                :class="u.role === 'admin' ? 'bg-accent/10 text-accent'
                       : u.role === 'auditor' ? 'bg-success/10 text-success'
                       : 'bg-text-2/10 text-text-2'">
            {{ u.role }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>
