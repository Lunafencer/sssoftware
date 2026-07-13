<script setup lang="ts">
/**
 * 个人中心 —— 全部数据从 API / Store 取，零假数据
 *  - 用户信息：来自 user store / 后端 /api/auth/me
 *  - 上传统计：调用 kbApi.listDocs({ uploader: 'me' }) 实时统计
 *  - 工单统计：调用 ticket listTickets() 后按 mine 统计
 *  - 历史工单：listTicketHistory()（已完成 / 已删除）+ 时间线 getTimeline
 *  - 修改密码：changePassword(old,new)
 *  - 接口缺失时显示"加载失败"或"暂无数据"，不允许任何硬编码
 */
import { ref, computed, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { useChatHistoryStore } from '@/stores/chatHistory'
import { ROLE_LABEL } from '@/utils/permission'
import { useDevice } from '@/composables/useDevice'
import {
  Award, FileText, ShieldCheck, Bell, Edit, Lock,
  Loader, AlertTriangle, MessageCircle, Star, Database, ListChecks,
  History, RotateCcw, ChevronDown, ChevronRight
} from 'lucide-vue-next'
import { listDocs, type KbDoc, isApprovedStatus, STATUS_LABEL } from '@/api/kb'
import {
  listTickets, listTicketHistory, addTicketToMine, getTimeline,
  type TicketSummary, type TicketHistoryItem, type TicketEvent
} from '@/api/ticket'
import { changePassword } from '@/api/auth'
import { formatTime } from '@/utils/format'
import { showSuccessToast, showFailToast } from 'vant'
import EmptyState from '@/components/common/EmptyState.vue'

const user = useUserStore()
const { isPC } = useDevice()
const chat = useChatHistoryStore()

const tab = ref<'basic' | 'security' | 'notif' | 'history' | 'contrib'>('basic')
const tabs = [
  { k: 'basic',    l: '基本信息', icon: Edit },
  { k: 'security', l: '安全设置', icon: Lock },
  { k: 'notif',    l: '通知偏好', icon: Bell },
  { k: 'history',  l: '历史工单', icon: History },
  { k: 'contrib',  l: '我的贡献', icon: Award }
]

// —— 真实统计 —— //
const myDocs = ref<KbDoc[]>([])
const myTickets = ref<TicketSummary[]>([])
const docsLoading = ref(false)
const ticketsLoading = ref(false)
const docsError = ref(false)
const ticketsError = ref(false)

const refreshDocs = async () => {
  docsLoading.value = true
  docsError.value = false
  try {
    myDocs.value = await listDocs({ uploader: 'me' })
  } catch {
    myDocs.value = []
    docsError.value = true
  } finally {
    docsLoading.value = false
  }
}
const refreshTickets = async () => {
  ticketsLoading.value = true
  ticketsError.value = false
  try {
    const res = await listTickets()
    myTickets.value = res.mine || []
  } catch {
    myTickets.value = []
    ticketsError.value = true
  } finally {
    ticketsLoading.value = false
  }
}

onMounted(() => { refreshDocs(); refreshTickets() })

const stats = computed(() => ({
  docsTotal: myDocs.value.length,
  docsPending: myDocs.value.filter(d => d.status === 'pending').length,
  docsApproved: myDocs.value.filter(d => isApprovedStatus(d.status)).length,
  docsRejected: myDocs.value.filter(d => d.status === 'rejected').length,
  ticketsTotal: myTickets.value.length,
  ticketsDone: myTickets.value.filter(t => t.status === 'done').length,
  sessions: chat.sessions.length,
  starred: chat.starredSessions.length
}))

const recentDocs = computed(() =>
  [...myDocs.value]
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    .slice(0, 5)
)

const STATUS_CLS: Record<string, string> = {
  pending:    'text-warning',
  approved:   'text-success',
  ready:      'text-success',
  rejected:   'text-danger',
  taken_down: 'text-text-2'
}

/* ----------------- 修改密码 ----------------- */
const pwdFormOpen = ref(false)
const pwdOld = ref('')
const pwdNew = ref('')
const pwdConfirm = ref('')
const pwdLoading = ref(false)

const openPwdForm = () => {
  pwdFormOpen.value = true
  pwdOld.value = ''
  pwdNew.value = ''
  pwdConfirm.value = ''
}

const submitPwd = async () => {
  if (!pwdOld.value || !pwdNew.value) { showFailToast('请填写完整'); return }
  if (pwdNew.value.length < 6) { showFailToast('新密码至少 6 位'); return }
  if (pwdNew.value !== pwdConfirm.value) { showFailToast('两次新密码不一致'); return }
  pwdLoading.value = true
  try {
    await changePassword(pwdOld.value, pwdNew.value)
    showSuccessToast('密码修改成功')
    pwdFormOpen.value = false
  } catch (e: any) {
    showFailToast(e?.message || '修改失败')
  } finally {
    pwdLoading.value = false
  }
}

/* ----------------- 历史工单 ----------------- */
const history = ref<TicketHistoryItem[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)
const historyLoaded = ref(false)

const refreshHistory = async () => {
  historyLoading.value = true
  historyError.value = null
  try {
    history.value = await listTicketHistory()
    historyLoaded.value = true
  } catch (e: any) {
    history.value = []
    historyError.value = e?.message || '加载失败'
  } finally {
    historyLoading.value = false
  }
}

const openHistoryTab = () => {
  tab.value = 'history'
  if (!historyLoaded.value && !historyLoading.value) refreshHistory()
}

const HISTORY_STATUS: Record<string, { label: string; cls: string }> = {
  done:    { label: '已完成', cls: 'text-success bg-success/10' },
  deleted: { label: '已删除', cls: 'text-danger bg-danger/10' }
}

const reAdding = ref<Record<number, boolean>>({})
const onReAdd = async (item: TicketHistoryItem) => {
  reAdding.value[item.id] = true
  try {
    await addTicketToMine(item.id)
    showSuccessToast('已重新添加到作业指引')
  } catch (e: any) {
    showFailToast(e?.message || '添加失败')
  } finally {
    reAdding.value[item.id] = false
  }
}

/* 时间线展开 */
const expanded = ref<Record<number, boolean>>({})
const timelines = ref<Record<number, TicketEvent[]>>({})
const timelineLoading = ref<Record<number, boolean>>({})
const timelineError = ref<Record<number, string | null>>({})

const EVENT_LABEL: Record<string, string> = {
  created:        '创建工单',
  added:          '加入作业指引',
  step_completed: '完成步骤',
  completed:      '完成工单',
  deleted:        '删除工单'
}

const toggleTimeline = async (item: TicketHistoryItem) => {
  const id = item.id
  expanded.value[id] = !expanded.value[id]
  if (expanded.value[id] && !timelines.value[id] && !timelineLoading.value[id]) {
    timelineLoading.value[id] = true
    timelineError.value[id] = null
    try {
      const res = await getTimeline(id)
      timelines.value[id] = res.events || []
    } catch (e: any) {
      timelines.value[id] = []
      timelineError.value[id] = e?.message || '加载失败'
    } finally {
      timelineLoading.value[id] = false
    }
  }
}
</script>

<template>
  <div :class="isPC ? 'p-6 max-w-6xl mx-auto grid grid-cols-12 gap-4' : 'p-3 space-y-3'">
    <!-- 头像卡 -->
    <aside :class="isPC ? 'col-span-3 industrial-card p-5' : 'industrial-card p-4'">
      <div :class="isPC ? 'text-center' : 'flex items-center gap-3'">
        <div class="w-20 h-20 rounded-full bg-gradient-to-br from-accent to-accent-2 flex items-center justify-center text-white text-3xl font-bold flex-shrink-0"
             :class="isPC ? 'mx-auto' : ''">
          {{ (user.info?.name || '游').slice(0, 1) }}
        </div>
        <div :class="isPC ? 'mt-3' : 'flex-1 min-w-0'">
          <div class="text-lg font-bold">{{ user.info?.name || '访客' }}</div>
          <div class="text-xs text-text-2 mt-0.5">{{ ROLE_LABEL[user.role] }}</div>
        </div>
      </div>

      <!-- 移动端三宫格贡献（用真实数据） -->
      <div v-if="!isPC" class="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-border text-center">
        <div>
          <div class="font-bold text-base text-accent mono">{{ stats.docsTotal }}</div>
          <div class="text-[11px] text-text-2">提交文档</div>
        </div>
        <div>
          <div class="font-bold text-base text-success mono">{{ stats.docsApproved }}</div>
          <div class="text-[11px] text-text-2">已通过</div>
        </div>
        <div>
          <div class="font-bold text-base text-ai mono">{{ stats.sessions }}</div>
          <div class="text-[11px] text-text-2">检索会话</div>
        </div>
      </div>
    </aside>

    <!-- 主内容 -->
    <main :class="isPC ? 'col-span-9 industrial-card p-5' : 'industrial-card p-3'">
      <div :class="isPC ? 'flex border-b border-border -mx-5 px-5 mb-4' : 'flex gap-1 mb-3'">
        <button v-for="t in tabs" :key="t.k" @click="t.k === 'history' ? openHistoryTab() : (tab = t.k as any)"
                :class="[isPC ? 'h-10 px-4 text-sm border-b-2 -mb-px' : 'flex-1 h-9 rounded-btn text-xs',
                         tab === t.k
                           ? (isPC ? 'border-accent text-accent font-semibold' : 'bg-accent text-white font-semibold')
                           : (isPC ? 'border-transparent text-text-2' : 'bg-card border border-border text-text-2')]">
          <component :is="t.icon" class="w-4 h-4 inline mr-1" />{{ t.l }}
        </button>
      </div>

      <!-- 基本信息 -->
      <div v-if="tab === 'basic'" class="space-y-3 text-sm">
        <div class="grid grid-cols-2 gap-3">
          <div><div class="text-text-2 text-xs mb-1">用户名</div><div class="font-medium">{{ user.info?.name || '—' }}</div></div>
          <div><div class="text-text-2 text-xs mb-1">用户 ID</div><div class="font-medium mono">{{ user.info?.id || '—' }}</div></div>
          <div><div class="text-text-2 text-xs mb-1">角色</div><div>{{ ROLE_LABEL[user.role] }}</div></div>
        </div>
        <div class="text-xs text-text-2 italic mt-3">
          基本信息由登录账号决定。如需修改请联系管理员。
        </div>
      </div>

      <!-- 安全设置 -->
      <div v-if="tab === 'security'" class="space-y-2 text-sm">
        <!-- 修改密码 -->
        <div v-if="!pwdFormOpen">
          <button @click="openPwdForm"
                  class="w-full h-12 px-3 rounded-btn border border-border flex items-center justify-between hover:border-accent hover:bg-bg transition">
            <span class="flex items-center gap-2"><Lock class="w-4 h-4 text-accent" /> 修改密码</span>
            <ChevronRight class="w-4 h-4 text-text-2" />
          </button>
        </div>
        <form v-else @submit.prevent="submitPwd" class="industrial-card p-4 space-y-3">
          <div class="font-semibold flex items-center gap-2"><Lock class="w-4 h-4 text-accent" /> 修改密码</div>
          <div>
            <div class="text-xs text-text-2 mb-1">当前密码</div>
            <input v-model="pwdOld" type="password" autocomplete="current-password" placeholder="请输入当前密码"
                   class="w-full h-11 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
          </div>
          <div>
            <div class="text-xs text-text-2 mb-1">新密码（至少 6 位）</div>
            <input v-model="pwdNew" type="password" autocomplete="new-password" placeholder="请输入新密码"
                   class="w-full h-11 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
          </div>
          <div>
            <div class="text-xs text-text-2 mb-1">确认新密码</div>
            <input v-model="pwdConfirm" type="password" autocomplete="new-password" placeholder="再次输入新密码"
                   class="w-full h-11 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
          </div>
          <div class="flex gap-2 pt-1">
            <button type="submit" :disabled="pwdLoading"
                    class="flex-1 h-11 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold transition flex items-center justify-center gap-2 disabled:opacity-60">
              <Loader v-if="pwdLoading" class="w-4 h-4 animate-spin" />
              <span>{{ pwdLoading ? '提交中…' : '确认修改' }}</span>
            </button>
            <button type="button" @click="pwdFormOpen = false"
                    class="h-11 px-4 rounded-btn border border-border text-text-2 hover:bg-bg transition">取消</button>
          </div>
        </form>

        <div class="text-xs text-text-2 italic mt-2">
          手机绑定 / 登录设备管理接口尚未开放。
        </div>
        <button disabled class="w-full h-12 px-3 rounded-btn border border-border flex items-center justify-between opacity-60 cursor-not-allowed">
          绑定手机 <span class="text-text-2 text-xs">即将开放</span>
        </button>
        <button disabled class="w-full h-12 px-3 rounded-btn border border-border flex items-center justify-between opacity-60 cursor-not-allowed">
          登录设备管理 <span class="text-text-2 text-xs">即将开放</span>
        </button>
      </div>

      <!-- 通知偏好 -->
      <div v-if="tab === 'notif'" class="space-y-2 text-sm">
        <div class="text-xs text-text-2 italic mb-2">
          后端尚未实现通知偏好接口；当前仅作占位展示。
        </div>
        <label v-for="n in ['案例审核结果', '待办流程提醒', '系统公告', '夜间静默']" :key="n"
               class="flex items-center justify-between h-12 px-3 rounded-btn border border-border opacity-60">
          <span>{{ n }}</span>
          <input type="checkbox" disabled class="w-5 h-5 accent-accent" />
        </label>
      </div>

      <!-- 历史工单 -->
      <div v-if="tab === 'history'" class="space-y-3">
        <div v-if="historyLoading" class="py-12 text-center text-text-2">
          <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-sm">加载历史工单…</div>
        </div>
        <div v-else-if="historyError && !history.length" class="py-12 text-center text-warning">
          <AlertTriangle class="w-8 h-8 mx-auto" />
          <div class="mt-2 text-sm">{{ historyError }}</div>
          <button @click="refreshHistory" class="mt-3 h-9 px-4 rounded-btn border border-border text-sm text-text hover:bg-bg">重试</button>
        </div>
        <EmptyState v-else-if="!history.length" title="暂无历史工单" desc="已完成或已删除的工单会出现在这里" />
        <ul v-else class="space-y-2">
          <li v-for="item in history" :key="item.id" class="industrial-card p-4">
            <div class="flex items-start gap-3">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-semibold truncate">{{ item.device }}</span>
                  <span class="text-[11px] px-1.5 py-0.5 rounded mono"
                        :class="(HISTORY_STATUS[item.status] || HISTORY_STATUS.done).cls">
                    {{ (HISTORY_STATUS[item.status] || HISTORY_STATUS.done).label }}
                  </span>
                </div>
                <div class="text-sm text-text-2 mt-1 truncate">{{ item.fault }}</div>
                <div class="text-xs text-text-2 mt-1 flex items-center gap-3 flex-wrap mono">
                  <span v-if="item.status === 'done' && item.completedAt">完成于 {{ formatTime(item.completedAt) }}</span>
                  <span v-if="item.status === 'deleted' && item.deletedAt">删除于 {{ formatTime(item.deletedAt) }}</span>
                  <span v-if="item.status === 'deleted' && item.deleteReason" class="text-danger not-italic">原因：{{ item.deleteReason }}</span>
                </div>
              </div>
              <div class="flex flex-col gap-2 flex-shrink-0">
                <button @click="onReAdd(item)" :disabled="reAdding[item.id]"
                        class="h-8 px-3 rounded-btn border border-border text-xs flex items-center gap-1.5 hover:border-accent hover:text-accent transition disabled:opacity-60">
                  <RotateCcw class="w-3.5 h-3.5" /> 重新添加
                </button>
                <button @click="toggleTimeline(item)"
                        class="h-8 px-3 rounded-btn border border-border text-xs flex items-center gap-1.5 hover:bg-bg transition">
                  <component :is="expanded[item.id] ? ChevronDown : ChevronRight" class="w-3.5 h-3.5" /> 时间线
                </button>
              </div>
            </div>

            <!-- 时间线 -->
            <div v-if="expanded[item.id]" class="mt-3 pt-3 border-t border-border">
              <div v-if="timelineLoading[item.id]" class="py-3 text-center text-text-2 text-xs">
                <Loader class="w-4 h-4 mx-auto animate-spin text-accent" />
              </div>
              <div v-else-if="timelineError[item.id]" class="py-2 text-center text-warning text-xs">
                {{ timelineError[item.id] }}
              </div>
              <div v-else-if="!(timelines[item.id] || []).length" class="py-2 text-center text-text-2 text-xs">
                暂无时间线记录
              </div>
              <ol v-else class="relative pl-5 space-y-3">
                <li v-for="(ev, i) in timelines[item.id]" :key="i" class="relative">
                  <span class="absolute -left-5 top-1 w-2.5 h-2.5 rounded-full bg-accent ring-2 ring-card"></span>
                  <span v-if="i < (timelines[item.id] || []).length - 1"
                        class="absolute -left-[15px] top-3.5 w-px h-[calc(100%+0.75rem)] bg-border"></span>
                  <div class="text-sm font-medium">
                    {{ EVENT_LABEL[ev.type] || ev.type }}
                    <span v-if="ev.detail?.stepId" class="text-text-2 font-normal">· 步骤 {{ ev.detail.stepId }}</span>
                    <span v-if="ev.detail?.reason" class="text-danger font-normal">· {{ ev.detail.reason }}</span>
                  </div>
                  <div class="text-xs text-text-2 mono mt-0.5">{{ formatTime(ev.at) }}</div>
                </li>
              </ol>
            </div>
          </li>
        </ul>
      </div>

      <!-- 我的贡献（真实数据） -->
      <div v-if="tab === 'contrib'" class="space-y-3">
        <div v-if="docsLoading || ticketsLoading" class="py-8 text-center text-text-2">
          <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-xs">统计加载中…</div>
        </div>
        <template v-else>
          <!-- 概览 -->
          <div :class="isPC ? 'grid grid-cols-4 gap-3' : 'grid grid-cols-2 gap-2'">
            <div class="industrial-card p-4 text-center">
              <Database class="w-6 h-6 mx-auto text-accent mb-1" />
              <div class="text-2xl font-bold mono">{{ stats.docsTotal }}</div>
              <div class="text-xs text-text-2">提交文档</div>
              <div v-if="stats.docsPending" class="text-[10px] text-warning mt-0.5">待审 {{ stats.docsPending }}</div>
            </div>
            <div class="industrial-card p-4 text-center">
              <ShieldCheck class="w-6 h-6 mx-auto text-success mb-1" />
              <div class="text-2xl font-bold mono">{{ stats.docsApproved }}</div>
              <div class="text-xs text-text-2">通过审核</div>
              <div v-if="stats.docsRejected" class="text-[10px] text-danger mt-0.5">被驳回 {{ stats.docsRejected }}</div>
            </div>
            <div class="industrial-card p-4 text-center">
              <ListChecks class="w-6 h-6 mx-auto text-ai mb-1" />
              <div class="text-2xl font-bold mono">{{ stats.ticketsTotal }}</div>
              <div class="text-xs text-text-2">我的工单</div>
              <div v-if="stats.ticketsDone" class="text-[10px] text-success mt-0.5">已完成 {{ stats.ticketsDone }}</div>
            </div>
            <div class="industrial-card p-4 text-center">
              <MessageCircle class="w-6 h-6 mx-auto text-primary mb-1" />
              <div class="text-2xl font-bold mono">{{ stats.sessions }}</div>
              <div class="text-xs text-text-2">检索会话</div>
              <div v-if="stats.starred" class="text-[10px] text-warning mt-0.5">
                <Star class="w-2.5 h-2.5 inline -mt-px" /> {{ stats.starred }}
              </div>
            </div>
          </div>

          <!-- 错误态 -->
          <div v-if="docsError || ticketsError"
               class="px-3 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-xs flex items-center gap-1.5">
            <AlertTriangle class="w-3.5 h-3.5" />
            部分统计数据加载失败（{{ [docsError ? '文档' : '', ticketsError ? '工单' : ''].filter(Boolean).join(' / ') }}），请确认后端可用。
          </div>

          <!-- 最近上传 -->
          <div class="industrial-card p-4 text-sm">
            <div class="font-semibold mb-2 flex items-center gap-2">
              <FileText class="w-4 h-4 text-accent" /> 最近上传
              <span class="text-xs text-text-2 font-normal mono">{{ recentDocs.length }} / {{ stats.docsTotal }}</span>
            </div>
            <ul v-if="recentDocs.length" class="divide-y divide-border">
              <li v-for="d in recentDocs" :key="d.id" class="py-2 flex items-center gap-2">
                <FileText class="w-4 h-4 text-text-2 flex-shrink-0" />
                <span class="flex-1 truncate">{{ d.title }}</span>
                <span class="text-[11px] mono text-text-2 hidden sm:inline">{{ formatTime(d.created_at) }}</span>
                <span class="text-xs flex-shrink-0" :class="STATUS_CLS[d.status] || 'text-text-2'">
                  {{ STATUS_LABEL[d.status] || d.status }}
                </span>
              </li>
            </ul>
            <div v-else class="text-center text-text-2 text-sm py-6">
              <Database class="w-8 h-8 mx-auto opacity-40" />
              <div class="mt-2">{{ docsError ? '加载失败' : '尚未上传过文档' }}</div>
            </div>
          </div>
        </template>
      </div>
    </main>
  </div>
</template>
