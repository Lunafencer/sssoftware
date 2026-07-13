<script setup lang="ts">
/**
 * 系统管理 —— 仅用户管理（真实数据，零假数据）
 *  - 列表：GET /api/admin/users
 *  - 创建：POST /api/admin/users
 *  - 改用户名 / 角色：PUT /api/admin/users/{id}
 *  - 重置密码：PUT /api/admin/users/{id}/reset-password（统一为 123456）
 *  - 删除：DELETE /api/admin/users/{id}
 *  默认管理员（isDefaultAdmin）禁止改角色 / 删除。
 */
import { ref, onMounted, computed } from 'vue'
import {
  listUsers, createUser, updateUser, resetPassword, deleteUser,
  backendRoleToFrontend, type SysUser, type BackendRole
} from '@/api/admin'
import {
  Users, Cog, Plus, Loader, AlertTriangle, RefreshCcw,
  Trash2, KeyRound, Lock, Check, X
} from 'lucide-vue-next'
import { ROLE_LABEL, ASSIGNABLE_ROLES, mapFrontendRole, type FrontendRole } from '@/utils/permission'
import { formatTime } from '@/utils/format'
import { useUserStore } from '@/stores/user'
import { showToast, showSuccessToast, showFailToast, showConfirmDialog } from 'vant'
import EmptyState from '@/components/common/EmptyState.vue'

const me = useUserStore()

const users = ref<SysUser[]>([])
const usersLoading = ref(false)
const usersError = ref<string | null>(null)
const filterRole = ref<'all' | BackendRole>('all')
const search = ref('')

const filteredUsers = computed(() => {
  let list = users.value
  if (filterRole.value !== 'all') list = list.filter(u => u.role === filterRole.value)
  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter(u => u.username.toLowerCase().includes(q) || String(u.id).includes(q))
  return list
})

const refreshUsers = async () => {
  usersLoading.value = true
  usersError.value = null
  try {
    users.value = await listUsers()
  } catch (e: any) {
    users.value = []
    usersError.value = e?.message || '加载失败'
  } finally {
    usersLoading.value = false
  }
}

onMounted(refreshUsers)

/* ----------- 修改角色（行内下拉） ----------- */
const onChangeRole = async (u: SysUser, ev: Event) => {
  const sel = (ev.target as HTMLSelectElement)
  const nextFront = sel.value as FrontendRole
  const nextBackend = mapFrontendRole(nextFront)
  if (nextBackend === u.role) return
  try {
    await updateUser(u.id, { role: nextBackend })
    showSuccessToast('角色已更新')
    await refreshUsers()
  } catch (e: any) {
    sel.value = backendRoleToFrontend(u.role)
    showFailToast(e?.response?.data?.detail || e?.message || '更新失败')
  }
}

/* ----------- 修改用户名（行内编辑） ----------- */
const editingId = ref<number | null>(null)
const editName = ref('')
const startEditName = (u: SysUser) => {
  editingId.value = u.id
  editName.value = u.username
}
const cancelEditName = () => { editingId.value = null; editName.value = '' }
const saveEditName = async (u: SysUser) => {
  const name = editName.value.trim()
  if (!name) { showFailToast('用户名不能为空'); return }
  if (name === u.username) { cancelEditName(); return }
  try {
    await updateUser(u.id, { username: name })
    showSuccessToast('用户名已更新')
    cancelEditName()
    await refreshUsers()
  } catch (e: any) {
    showFailToast(e?.response?.data?.detail || e?.message || '更新失败')
  }
}

/* ----------- 重置密码 ----------- */
const onResetPassword = async (u: SysUser) => {
  try {
    await showConfirmDialog({
      title: '重置密码',
      message: `确定将 ${u.username} 的密码重置为 123456 吗？`
    })
  } catch { return }
  try {
    await resetPassword(u.id)
    showToast({ type: 'success', message: '密码已重置为 123456' })
  } catch (e: any) {
    showFailToast(e?.response?.data?.detail || e?.message || '重置失败')
  }
}

/* ----------- 删除账户 ----------- */
const onDelete = async (u: SysUser) => {
  try {
    await showConfirmDialog({
      title: '删除账户',
      message: `确定删除账户 ${u.username} 吗？该操作不可恢复。`,
      confirmButtonText: '删除',
      confirmButtonColor: '#e53935'
    })
  } catch { return }
  try {
    await deleteUser(u.id)
    showSuccessToast('账户已删除')
    await refreshUsers()
  } catch (e: any) {
    showFailToast(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

/* ----------- 创建账户 ----------- */
const createOpen = ref(false)
const createName = ref('')
const createPwd = ref('')
const createRole = ref<FrontendRole>('frontline')
const createLoading = ref(false)

const openCreate = () => {
  createOpen.value = true
  createName.value = ''
  createPwd.value = ''
  createRole.value = 'frontline'
}
const submitCreate = async () => {
  const name = createName.value.trim()
  if (!name) { showFailToast('请输入用户名'); return }
  createLoading.value = true
  try {
    await createUser({
      username: name,
      password: createPwd.value.trim() || undefined,
      role: mapFrontendRole(createRole.value)
    })
    showSuccessToast('账户已创建')
    createOpen.value = false
    await refreshUsers()
  } catch (e: any) {
    showFailToast(e?.response?.data?.detail || e?.message || '创建失败')
  } finally {
    createLoading.value = false
  }
}

const ROLE_BADGE_CLS: Record<string, string> = {
  admin:   'bg-accent/10 text-accent',
  auditor: 'bg-success/10 text-success',
  worker:  'bg-text-2/10 text-text-2'
}
</script>

<template>
  <div class="p-6 max-w-[1600px] mx-auto h-full flex flex-col">
    <header class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold flex items-center gap-2"><Cog class="w-5 h-5 text-accent" /> 用户管理</h1>
      <div class="flex items-center gap-2">
        <button @click="refreshUsers"
                class="h-9 px-3 rounded-btn border border-border text-sm flex items-center gap-1.5 hover:bg-bg">
          <RefreshCcw class="w-4 h-4" /> 刷新
        </button>
        <button @click="openCreate"
                class="h-9 px-3 rounded-btn bg-accent hover:bg-accent-2 text-white text-sm font-semibold flex items-center gap-1.5">
          <Plus class="w-4 h-4" /> 创建账户
        </button>
      </div>
    </header>

    <div class="industrial-card flex-1 overflow-hidden flex flex-col">
      <main class="flex-1 overflow-auto p-5 space-y-3">
        <!-- 过滤栏 -->
        <div class="flex items-center gap-2 flex-wrap">
          <input v-model="search" placeholder="按用户名 / ID 搜索…"
                 class="h-9 px-3 rounded-btn border border-border bg-bg outline-none text-sm w-64" />
          <select v-model="filterRole"
                  class="h-9 px-2 rounded-btn border border-border bg-bg text-sm">
            <option value="all">全部角色</option>
            <option v-for="r in ASSIGNABLE_ROLES" :key="r" :value="mapFrontendRole(r)">{{ ROLE_LABEL[r] }}</option>
          </select>
          <span class="text-xs text-text-2 ml-auto">
            共 <span class="mono text-accent">{{ filteredUsers.length }}</span> / {{ users.length }} 名用户
          </span>
        </div>

        <!-- 加载态 -->
        <div v-if="usersLoading" class="py-12 text-center text-text-2">
          <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-sm">加载用户列表…</div>
        </div>

        <!-- 错误态 -->
        <div v-else-if="usersError && !users.length" class="py-12 text-center text-warning">
          <AlertTriangle class="w-8 h-8 mx-auto" />
          <div class="mt-2 text-sm">{{ usersError }}</div>
          <button @click="refreshUsers" class="mt-3 h-9 px-4 rounded-btn border border-border text-sm text-text hover:bg-bg">重试</button>
        </div>

        <!-- 空态 -->
        <EmptyState v-else-if="!users.length" title="暂无用户" desc="点击右上角“创建账户”新增账户" />

        <!-- 表格 -->
        <table v-else class="w-full text-sm">
          <thead class="text-text-2 text-xs">
            <tr>
              <th class="p-2 text-left">用户名</th>
              <th class="p-2 text-left">角色</th>
              <th class="p-2 text-left">创建时间</th>
              <th class="p-2 text-left">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in filteredUsers" :key="u.id" class="border-t border-border hover:bg-bg">
              <!-- 用户名 -->
              <td class="p-2 font-medium">
                <div v-if="editingId === u.id" class="flex items-center gap-1">
                  <input v-model="editName" class="h-8 px-2 rounded-btn border border-border bg-card text-sm w-40 outline-none focus:border-accent"
                         @keyup.enter="saveEditName(u)" @keyup.esc="cancelEditName" />
                  <button @click="saveEditName(u)" class="w-8 h-8 rounded-btn text-success hover:bg-success/10 flex items-center justify-center"><Check class="w-4 h-4" /></button>
                  <button @click="cancelEditName" class="w-8 h-8 rounded-btn text-text-2 hover:bg-bg flex items-center justify-center"><X class="w-4 h-4" /></button>
                </div>
                <div v-else class="flex items-center gap-1.5">
                  <button @click="startEditName(u)" class="hover:text-accent transition" :title="'修改用户名'">{{ u.username }}</button>
                  <span v-if="String(u.username) === String(me.info?.name)"
                        class="text-[10px] px-1 py-0.5 rounded bg-accent/10 text-accent">本人</span>
                  <span v-if="u.isDefaultAdmin"
                        class="text-[10px] px-1 py-0.5 rounded bg-warning/10 text-warning flex items-center gap-0.5">
                    <Lock class="w-2.5 h-2.5" /> 默认管理员
                  </span>
                </div>
              </td>
              <!-- 角色 -->
              <td class="p-2">
                <span v-if="u.isDefaultAdmin"
                      class="text-[11px] px-1.5 py-0.5 rounded mono" :class="ROLE_BADGE_CLS[u.role] || ROLE_BADGE_CLS.worker">
                  {{ ROLE_LABEL[backendRoleToFrontend(u.role)] }}
                </span>
                <select v-else :value="backendRoleToFrontend(u.role)" @change="onChangeRole(u, $event)"
                        class="h-8 px-2 rounded-btn border border-border bg-bg text-sm">
                  <option v-for="r in ASSIGNABLE_ROLES" :key="r" :value="r">{{ ROLE_LABEL[r] }}</option>
                </select>
              </td>
              <!-- 创建时间 -->
              <td class="p-2 text-xs text-text-2">{{ u.createdAt ? formatTime(u.createdAt) : '—' }}</td>
              <!-- 操作 -->
              <td class="p-2">
                <div class="flex items-center gap-1.5">
                  <button @click="onResetPassword(u)"
                          class="h-8 px-2.5 rounded-btn border border-border text-xs flex items-center gap-1 hover:border-accent hover:text-accent transition">
                    <KeyRound class="w-3.5 h-3.5" /> 重置密码
                  </button>
                  <button v-if="!u.isDefaultAdmin" @click="onDelete(u)"
                          class="h-8 px-2.5 rounded-btn border border-danger/40 text-danger text-xs flex items-center gap-1 hover:bg-danger/10 transition">
                    <Trash2 class="w-3.5 h-3.5" /> 删除
                  </button>
                  <span v-else class="text-[11px] text-text-2 flex items-center gap-1">
                    <Lock class="w-3 h-3" /> 受保护
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </main>
    </div>

    <!-- 创建账户弹窗 -->
    <div v-if="createOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="createOpen = false">
      <div class="w-[420px] industrial-card p-6 shadow-float">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-bold flex items-center gap-2"><Users class="w-5 h-5 text-accent" /> 创建账户</h2>
          <button @click="createOpen = false" class="w-8 h-8 rounded-full hover:bg-bg flex items-center justify-center text-text-2"><X class="w-4 h-4" /></button>
        </div>
        <form @submit.prevent="submitCreate" class="space-y-3">
          <div>
            <div class="text-xs text-text-2 mb-1">用户名</div>
            <input v-model="createName" placeholder="请输入用户名"
                   class="w-full h-11 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
          </div>
          <div>
            <div class="text-xs text-text-2 mb-1">初始密码（留空默认 123456）</div>
            <input v-model="createPwd" placeholder="默认 123456"
                   class="w-full h-11 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
          </div>
          <div>
            <div class="text-xs text-text-2 mb-1">角色</div>
            <select v-model="createRole" class="w-full h-11 px-3 rounded-btn border border-border bg-bg text-sm outline-none focus:border-accent">
              <option v-for="r in ASSIGNABLE_ROLES" :key="r" :value="r">{{ ROLE_LABEL[r] }}</option>
            </select>
            <div v-if="createRole === 'admin'" class="mt-1.5 text-xs text-warning flex items-center gap-1">
              <AlertTriangle class="w-3.5 h-3.5" /> 系统管理员拥有用户管理等全部权限，请谨慎分配。
            </div>
          </div>
          <div class="flex gap-2 pt-1">
            <button type="submit" :disabled="createLoading"
                    class="flex-1 h-11 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold transition flex items-center justify-center gap-2 disabled:opacity-60">
              <Loader v-if="createLoading" class="w-4 h-4 animate-spin" />
              <span>{{ createLoading ? '创建中…' : '确认创建' }}</span>
            </button>
            <button type="button" @click="createOpen = false"
                    class="h-11 px-4 rounded-btn border border-border text-text-2 hover:bg-bg transition">取消</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
