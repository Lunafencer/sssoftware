<script setup lang="ts">
/**
 * 作业指引 · 工单列表（FIX5 第 8/9/10 项）
 * - 我的工单：当前用户已添加的工单，显示自己的进度
 * - 推荐工单：他人创建、我未添加的工单，可一键"添加到我的工单"
 * - 新建工单前先做相似度推荐（item 10），无合适项再新建
 * - 删除：已完成无需理由；未完成必须填写理由（需求错误 / 误触 / 其他）
 * - 无 Mock：接口失败显示错误状态
 */
import { onMounted, ref, computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { listFlows, type WorkItem } from '@/api/workflow'
import {
  createTicket, recommendTickets, addTicketToMine, deleteTicket,
  type TicketSummary
} from '@/api/ticket'
import { useDevice } from '@/composables/useDevice'
import { useUserStore } from '@/stores/user'
import { showToast, showFailToast, showSuccessToast } from 'vant'
import {
  ListChecks, Search, AlertTriangle, Clock, Cpu, ChevronRight, ChevronDown,
  Plus, Loader, X, Sparkles, Inbox, Trash2, UserPlus, Users, CheckCircle2
} from 'lucide-vue-next'
import EmptyState from '@/components/common/EmptyState.vue'
import TicketTimeline from '@/components/common/TicketTimeline.vue'

const router = useRouter()
const { isPC } = useDevice()
const userStore = useUserStore()
// FIX7 续：审查员/管理员可直接查看任意工单的时间线，无需先添加到自己的工单
const canAuditAll = computed(() => userStore.isAuditor)

const mine = ref<WorkItem[]>([])
const recommended = ref<WorkItem[]>([])
const loaded = ref(false)
const loadError = ref<string | null>(null)
const q = ref('')
const showDone = ref(false)
const showRecommend = ref(true)

const refresh = async () => {
  loadError.value = null
  try {
    const res = await listFlows()
    mine.value = res.mine
    recommended.value = res.recommended
  } catch (e: any) {
    loadError.value = e?.message || '服务不可用，请确认后端已启动并已登录'
    mine.value = []
    recommended.value = []
  } finally {
    loaded.value = true
  }
}
onMounted(refresh)

const matchKeyword = (it: WorkItem) =>
  !q.value || it.name.includes(q.value) || it.deviceModel.includes(q.value)

const pendingList = computed(() =>
  mine.value.filter(it => it.status === '待办' && matchKeyword(it))
)
const doneList = computed(() =>
  mine.value.filter(it => it.status === '已完成' && matchKeyword(it))
)
// FIX7 续：审查员/管理员视角下后端会把 mine 内工单也回填到 recommended（便于查看时间线），
// 此处去重，避免列表中重复出现
const recommendList = computed(() => {
  const mineIds = new Set(mine.value.map(it => it.ticketId))
  return recommended.value.filter(it => !mineIds.has(it.ticketId) && matchKeyword(it))
})
// FIX7 续：审查员/管理员的"全部工单"——把 mine 也算进去，按更新时间归并
const allTickets = computed(() => {
  const map = new Map<number, WorkItem>()
  for (const it of mine.value) map.set(it.ticketId, it)
  for (const it of recommended.value) {
    if (!map.has(it.ticketId)) map.set(it.ticketId, it)
  }
  return Array.from(map.values()).filter(matchKeyword)
})

const open = (it: WorkItem) => router.push(`/workflow/${it.id}`)

/* ---------------- 工单时间线（审查员/管理员可在列表直接查看） ---------------- */
const timelineTarget = ref<WorkItem | null>(null)
const openTimeline = (it: WorkItem) => { timelineTarget.value = it }

/* ---------------- 添加他人工单到我的 ---------------- */
const adding = ref<Record<number, boolean>>({})
const onAdd = async (it: WorkItem) => {
  adding.value[it.ticketId] = true
  try {
    await addTicketToMine(it.ticketId)
    showSuccessToast('已添加到我的工单')
    await refresh()
  } catch (e: any) {
    showFailToast(e?.message || '添加失败')
  } finally {
    adding.value[it.ticketId] = false
  }
}

/* ---------------- 删除工单 ---------------- */
const delTarget = ref<WorkItem | null>(null)
const delReason = ref<'需求错误' | '误触' | '其他' | ''>('')
const delOther = ref('')
const deleting = ref(false)

const askDelete = (it: WorkItem) => {
  delTarget.value = it
  delReason.value = ''
  delOther.value = ''
}
const confirmDelete = async () => {
  const it = delTarget.value
  if (!it) return
  let reason: string | undefined
  if (it.status !== '已完成') {
    if (!delReason.value) { showFailToast('请选择删除理由'); return }
    if (delReason.value === '其他') {
      if (!delOther.value.trim()) { showFailToast('请填写其他理由'); return }
      reason = delOther.value.trim()
    } else {
      reason = delReason.value
    }
  }
  deleting.value = true
  try {
    await deleteTicket(it.ticketId, reason)
    showSuccessToast('已删除')
    delTarget.value = null
    await refresh()
  } catch (e: any) {
    showFailToast(e?.message || '删除失败')
  } finally {
    deleting.value = false
  }
}

/* ---------------- 新建工单（先推荐再新建） ---------------- */
const showCreate = ref(false)
const creating = ref(false)
const recommending = ref(false)
const draft = reactive({ device: '', fault: '' })
const createMatches = ref<TicketSummary[]>([])
const showMatchStep = ref(false)

const openCreate = () => {
  draft.device = ''
  draft.fault = ''
  createMatches.value = []
  showMatchStep.value = false
  showCreate.value = true
}

/** 第一步：相似度推荐 */
const findSimilar = async () => {
  if (!draft.device.trim() || !draft.fault.trim()) {
    showFailToast('请填写设备与故障描述')
    return
  }
  recommending.value = true
  try {
    createMatches.value = await recommendTickets({
      device: draft.device.trim(), fault: draft.fault.trim()
    })
    if (createMatches.value.length) {
      showMatchStep.value = true
    } else {
      await doCreate()
    }
  } catch {
    // 推荐失败不阻断，直接进入新建
    await doCreate()
  } finally {
    recommending.value = false
  }
}

const addMatch = async (t: TicketSummary) => {
  adding.value[t.id] = true
  try {
    await addTicketToMine(t.id)
    showSuccessToast('已添加到我的工单')
    showCreate.value = false
    await refresh()
    router.push(`/workflow/t-${t.id}`)
  } catch (e: any) {
    showFailToast(e?.message || '添加失败')
  } finally {
    adding.value[t.id] = false
  }
}

/** 第二步：确认新建 */
const doCreate = async () => {
  creating.value = true
  try {
    const res = await createTicket({ device: draft.device.trim(), fault: draft.fault.trim() })
    showToast({ type: 'success', message: 'AI 已生成检修方案' })
    showCreate.value = false
    await refresh()
    router.push(`/workflow/t-${res.id}`)
  } catch (e: any) {
    showFailToast(e?.message || '创建失败：请确认后端已启动并已登录')
  } finally {
    creating.value = false
  }
}

const STATUS_CLS: Record<string, string> = {
  '待办':   'bg-accent/10 text-accent border-accent/30',
  '已完成': 'bg-success/10 text-success border-success/30'
}
const formatMin = (m: number) => m < 60 ? `${m} 分钟` : `${Math.floor(m / 60)}h ${m % 60}m`
const pct = (it: WorkItem) => it.totalSteps ? Math.round((it.doneSteps / it.totalSteps) * 100) : 0
</script>

<template>
  <!-- ==================== PC ==================== -->
  <div v-if="isPC" class="p-6 max-w-[1400px] mx-auto">
    <header class="mb-4 flex items-end justify-between gap-4">
      <div>
        <div class="text-xs text-text-2">作业指引 / 列表</div>
        <h1 class="text-2xl font-bold text-primary mt-1">作业指引</h1>
        <div class="text-sm text-text-2 mt-1">我的工单显示个人进度；他人创建的工单作为推荐，可一键添加</div>
      </div>
      <button @click="openCreate"
              class="h-10 px-4 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 ai-shine">
        <Plus class="w-4 h-4" /> 新建 AI 工单
      </button>
    </header>

    <div v-if="loadError" class="mb-4 px-4 py-2 rounded-btn bg-danger/10 border border-danger/30 text-danger text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" />
      <span>{{ loadError }}</span>
      <button @click="refresh" class="ml-auto h-7 px-3 rounded-btn border border-danger/40 text-xs hover:bg-danger/10">重试</button>
    </div>

    <div class="industrial-card p-3 flex items-center gap-3 mb-4">
      <div class="relative flex-1 max-w-md">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
        <input v-model="q" placeholder="搜索作业名称或设备型号"
               class="w-full h-9 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent" />
      </div>
      <div class="ml-auto text-sm text-text-2">
        待办 <span class="font-semibold text-text">{{ pendingList.length }}</span>
        · 已完成 <span class="font-semibold text-text">{{ doneList.length }}</span>
        · <span v-if="canAuditAll">全部 <span class="font-semibold text-text">{{ allTickets.length }}</span></span>
          <span v-else>推荐 <span class="font-semibold text-text">{{ recommendList.length }}</span></span>
      </div>
    </div>

    <!-- 我的工单 -->
    <section>
      <div class="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="it in pendingList" :key="it.id"
             class="industrial-card p-5 text-left hover:shadow-float hover:-translate-y-0.5 transition group cursor-pointer relative"
             @click="open(it)">
          <div class="flex items-start gap-3">
            <div class="w-11 h-11 rounded-card flex-shrink-0 flex items-center justify-center"
                 :class="it.hazardous ? 'bg-warning/10 text-warning' : 'bg-accent/10 text-accent'">
              <AlertTriangle v-if="it.hazardous" class="w-5 h-5" />
              <ListChecks v-else class="w-5 h-5" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-base font-semibold leading-snug group-hover:text-accent transition">{{ it.name }}</div>
              <div class="text-xs text-text-2 mt-1 mono">{{ it.id }}</div>
            </div>
            <span class="px-2 py-0.5 rounded-pill text-xs border whitespace-nowrap" :class="STATUS_CLS[it.status]">
              {{ it.status }}
            </span>
          </div>

          <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div class="flex items-center gap-1.5 text-text-2">
              <Cpu class="w-3.5 h-3.5" /> <span class="mono">{{ it.deviceModel }}</span>
            </div>
            <div class="flex items-center gap-1.5 text-text-2">
              <Clock class="w-3.5 h-3.5" /> {{ formatMin(it.estimatedMinutes) }}
            </div>
          </div>

          <!-- 进度条 -->
          <div class="mt-3">
            <div class="flex items-center justify-between text-[11px] text-text-2 mb-1">
              <span>进度 {{ it.doneSteps }}/{{ it.totalSteps }}</span>
              <span class="mono">{{ pct(it) }}%</span>
            </div>
            <div class="h-1.5 rounded-full bg-border overflow-hidden">
              <div class="h-full bg-accent transition-all" :style="{ width: pct(it) + '%' }"></div>
            </div>
          </div>

          <div class="mt-4 pt-3 border-t border-border flex items-center justify-between text-xs text-text-2">
            <span class="truncate">{{ it.workshop || '—' }}</span>
            <button class="text-danger hover:text-danger/80 flex items-center gap-1" @click.stop="askDelete(it)">
              <Trash2 class="w-3.5 h-3.5" /> 删除
            </button>
          </div>
        </div>
      </div>

      <EmptyState v-if="loaded && pendingList.length === 0 && !loadError"
                  title="暂无待办工单"
                  desc="点击右上角“新建 AI 工单”，或从下方推荐工单中添加" class="mt-2" />
    </section>

    <!-- 已完成（折叠） -->
    <section v-if="doneList.length" class="mt-6">
      <button class="w-full h-11 px-4 rounded-card border border-border bg-card hover:bg-bg flex items-center gap-2 transition"
              @click="showDone = !showDone">
        <ChevronDown class="w-4 h-4 text-text-2 transition-transform" :class="showDone ? 'rotate-180' : ''" />
        <span class="text-sm font-semibold">已完成（{{ doneList.length }}）</span>
        <span class="ml-auto text-xs text-text-2">{{ showDone ? '点击收起' : '点击展开查看' }}</span>
      </button>
      <div v-if="showDone" class="grid grid-cols-2 lg:grid-cols-3 gap-4 mt-3">
        <div v-for="it in doneList" :key="it.id"
             class="industrial-card p-5 text-left opacity-80 hover:opacity-100 hover:shadow-float transition cursor-pointer"
             @click="open(it)">
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-card flex-shrink-0 bg-success/10 text-success flex items-center justify-center">
              <CheckCircle2 class="w-5 h-5" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold leading-snug">{{ it.name }}</div>
              <div class="text-[11px] text-text-2 mt-1 mono">{{ it.id }} · {{ it.deviceModel }}</div>
            </div>
            <button class="text-danger hover:text-danger/80 flex-shrink-0" @click.stop="askDelete(it)">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 推荐工单（折叠）—— 审查员/管理员视角显示"全部工单"且可直接查看时间线 -->
    <section v-if="canAuditAll ? allTickets.length : recommendList.length" class="mt-6">
      <button class="w-full h-11 px-4 rounded-card border border-border bg-card hover:bg-bg flex items-center gap-2 transition"
              @click="showRecommend = !showRecommend">
        <Users class="w-4 h-4 text-ai" />
        <span class="text-sm font-semibold">
          {{ canAuditAll ? '全部工单' : '推荐工单' }}（{{ canAuditAll ? allTickets.length : recommendList.length }}）
        </span>
        <span v-if="canAuditAll" class="text-[11px] text-text-2 ml-1">点击可查看任意工单时间线</span>
        <ChevronDown class="ml-auto w-4 h-4 text-text-2 transition-transform" :class="showRecommend ? 'rotate-180' : ''" />
      </button>
      <div v-if="showRecommend" class="grid grid-cols-2 lg:grid-cols-3 gap-4 mt-3">
        <div v-for="it in (canAuditAll ? allTickets : recommendList)" :key="it.id" class="industrial-card p-5 border-dashed">
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-card flex-shrink-0 bg-ai/10 text-ai flex items-center justify-center">
              <ListChecks class="w-5 h-5" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold leading-snug">{{ it.name }}</div>
              <div class="text-[11px] text-text-2 mt-1 mono">{{ it.deviceModel }} · 共 {{ it.totalSteps }} 步</div>
              <div v-if="it.creator" class="text-[11px] text-text-2 mt-0.5">创建人 · {{ it.creator }}</div>
              <div v-if="canAuditAll && it.added"
                   class="text-[11px] text-success mt-0.5 inline-flex items-center gap-0.5">
                <CheckCircle2 class="w-3 h-3" /> 已在我的工单
              </div>
            </div>
          </div>
          <div class="mt-3 flex items-center gap-2">
            <!-- 审查员/管理员：查看时间线 -->
            <button v-if="canAuditAll" @click="openTimeline(it)"
                    class="flex-1 h-9 rounded-btn border border-border text-text-2 text-sm font-medium flex items-center justify-center gap-1.5 hover:border-accent hover:text-accent transition">
              <Clock class="w-4 h-4" /> 查看时间线
            </button>
            <!-- 添加到我的工单（仅未加过时显示） -->
            <button v-if="!it.added" @click="onAdd(it)" :disabled="adding[it.ticketId]"
                    class="flex-1 h-9 rounded-btn border border-accent/40 text-accent text-sm font-semibold flex items-center justify-center gap-1.5 hover:bg-accent/10 transition disabled:opacity-60">
              <Loader v-if="adding[it.ticketId]" class="w-4 h-4 animate-spin" />
              <UserPlus v-else class="w-4 h-4" /> 添加到我的工单
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- ==================== 移动端 ==================== -->
  <div v-else class="p-3 space-y-3">
    <header class="industrial-card p-4 flex items-center gap-3">
      <div class="flex-1 min-w-0">
        <h1 class="text-lg font-bold text-primary">作业指引</h1>
        <div class="text-xs text-text-2 mt-1">
          待办 {{ pendingList.length }} · 已完成 {{ doneList.length }} ·
          <span v-if="canAuditAll">全部 {{ allTickets.length }}</span>
          <span v-else>推荐 {{ recommendList.length }}</span>
        </div>
      </div>
      <button @click="openCreate"
              class="h-9 px-3 rounded-btn bg-accent text-white text-sm font-semibold flex items-center gap-1 flex-shrink-0">
        <Plus class="w-4 h-4" /> 新建
      </button>
    </header>

    <div v-if="loadError" class="px-3 py-2 rounded-btn bg-danger/10 border border-danger/30 text-danger text-xs flex items-center gap-1.5">
      <AlertTriangle class="w-3.5 h-3.5" /> {{ loadError }}
      <button @click="refresh" class="ml-auto underline">重试</button>
    </div>

    <div class="relative">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
      <input v-model="q" placeholder="搜索作业 / 设备型号"
             class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-card text-base" />
    </div>

    <!-- 我的待办 -->
    <ul class="space-y-3">
      <li v-for="it in pendingList" :key="it.id" class="industrial-card p-4 active:bg-bg" @click="open(it)">
        <div class="flex items-start gap-3">
          <div class="w-10 h-10 rounded-card flex-shrink-0 flex items-center justify-center"
               :class="it.hazardous ? 'bg-warning/10 text-warning' : 'bg-accent/10 text-accent'">
            <AlertTriangle v-if="it.hazardous" class="w-5 h-5" />
            <ListChecks v-else class="w-5 h-5" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-semibold leading-snug">{{ it.name }}</div>
            <div class="text-xs text-text-2 mt-1 flex items-center gap-2 flex-wrap">
              <span class="mono">{{ it.deviceModel }}</span>
              <span>{{ it.doneSteps }}/{{ it.totalSteps }} 步</span>
            </div>
          </div>
          <button class="text-danger flex-shrink-0 p-1" @click.stop="askDelete(it)">
            <Trash2 class="w-4 h-4" />
          </button>
        </div>
        <div class="mt-2 h-1.5 rounded-full bg-border overflow-hidden">
          <div class="h-full bg-accent transition-all" :style="{ width: pct(it) + '%' }"></div>
        </div>
      </li>
      <li v-if="loaded && pendingList.length === 0 && !loadError">
        <EmptyState title="暂无待办工单" desc="点击上方“新建”，或从推荐工单中添加" />
      </li>
    </ul>

    <!-- 已完成（折叠） -->
    <div v-if="doneList.length">
      <button class="w-full h-11 px-3 rounded-card border border-border bg-card flex items-center gap-2"
              @click="showDone = !showDone">
        <ChevronDown class="w-4 h-4 text-text-2 transition-transform" :class="showDone ? 'rotate-180' : ''" />
        <span class="text-sm font-semibold">已完成（{{ doneList.length }}）</span>
      </button>
      <ul v-if="showDone" class="space-y-2 mt-2">
        <li v-for="it in doneList" :key="it.id" class="industrial-card p-3 opacity-80 active:bg-bg">
          <div class="flex items-start gap-2">
            <div class="w-8 h-8 rounded-card flex-shrink-0 bg-success/10 text-success flex items-center justify-center" @click="open(it)">
              <CheckCircle2 class="w-4 h-4" />
            </div>
            <div class="flex-1 min-w-0" @click="open(it)">
              <div class="text-sm font-medium">{{ it.name }}</div>
              <div class="text-[11px] text-text-2 mt-0.5 mono">{{ it.deviceModel }}</div>
            </div>
            <button class="text-danger flex-shrink-0 p-1" @click.stop="askDelete(it)">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </li>
      </ul>
    </div>

    <!-- 推荐工单（折叠）—— 审查员/管理员视角显示"全部工单" -->
    <div v-if="canAuditAll ? allTickets.length : recommendList.length">
      <button class="w-full h-11 px-3 rounded-card border border-border bg-card flex items-center gap-2"
              @click="showRecommend = !showRecommend">
        <Users class="w-4 h-4 text-ai" />
        <span class="text-sm font-semibold">
          {{ canAuditAll ? '全部工单' : '推荐工单' }}（{{ canAuditAll ? allTickets.length : recommendList.length }}）
        </span>
        <ChevronDown class="ml-auto w-4 h-4 text-text-2 transition-transform" :class="showRecommend ? 'rotate-180' : ''" />
      </button>
      <ul v-if="showRecommend" class="space-y-2 mt-2">
        <li v-for="it in (canAuditAll ? allTickets : recommendList)" :key="it.id" class="industrial-card p-3 border-dashed">
          <div class="flex items-start gap-2">
            <div class="w-8 h-8 rounded-card flex-shrink-0 bg-ai/10 text-ai flex items-center justify-center">
              <ListChecks class="w-4 h-4" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium">{{ it.name }}</div>
              <div class="text-[11px] text-text-2 mt-0.5 mono">{{ it.deviceModel }} · {{ it.creator || '其他用户' }}</div>
              <div v-if="canAuditAll && it.added"
                   class="text-[11px] text-success mt-0.5 inline-flex items-center gap-0.5">
                <CheckCircle2 class="w-3 h-3" /> 已在我的工单
              </div>
            </div>
          </div>
          <div class="mt-2 flex gap-2">
            <button v-if="canAuditAll" @click="openTimeline(it)"
                    class="flex-1 h-9 rounded-btn border border-border text-text-2 text-sm font-medium flex items-center justify-center gap-1.5">
              <Clock class="w-4 h-4" /> 时间线
            </button>
            <button v-if="!it.added" @click="onAdd(it)" :disabled="adding[it.ticketId]"
                    class="flex-1 h-9 rounded-btn border border-accent/40 text-accent text-sm font-semibold flex items-center justify-center gap-1.5 disabled:opacity-60">
              <Loader v-if="adding[it.ticketId]" class="w-4 h-4 animate-spin" />
              <UserPlus v-else class="w-4 h-4" /> 添加
            </button>
          </div>
        </li>
      </ul>
    </div>
  </div>

  <!-- ==================== 删除工单弹窗 ==================== -->
  <div v-if="delTarget" class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
       @click.self="!deleting && (delTarget = null)">
    <div class="industrial-card w-full max-w-sm bg-card overflow-hidden">
      <header class="px-5 py-3 border-b border-border flex items-center gap-2">
        <Trash2 class="w-4 h-4 text-danger" />
        <span class="font-semibold flex-1">删除工单</span>
        <button class="text-text-2 hover:text-danger" :disabled="deleting" @click="delTarget = null"><X class="w-4 h-4" /></button>
      </header>
      <div class="p-5 space-y-3">
        <div class="text-sm text-text-2 truncate">{{ delTarget.name }}</div>
        <!-- 已完成：无需理由 -->
        <div v-if="delTarget.status === '已完成'" class="text-sm">
          该工单已完成，将以“已完成”记录保存到历史工单，确认删除？
        </div>
        <!-- 未完成：必须填写理由 -->
        <div v-else class="space-y-2">
          <div class="text-sm">未完成的工单，请选择删除理由：</div>
          <div class="grid grid-cols-3 gap-2">
            <button v-for="r in (['需求错误','误触','其他'] as const)" :key="r"
                    @click="delReason = r"
                    :class="['h-9 rounded-btn border text-sm transition',
                             delReason === r ? 'border-accent bg-accent/10 text-accent font-semibold' : 'border-border text-text-2']">
              {{ r }}
            </button>
          </div>
          <textarea v-if="delReason === '其他'" v-model="delOther" rows="2" placeholder="请填写删除理由"
                    class="w-full px-3 py-2 rounded-btn border border-border bg-bg outline-none focus:border-accent resize-none text-sm"></textarea>
        </div>
      </div>
      <footer class="px-5 py-3 border-t border-border flex justify-end gap-2">
        <button class="h-9 px-4 rounded-btn border border-border" :disabled="deleting" @click="delTarget = null">取消</button>
        <button class="h-9 px-5 rounded-btn bg-danger hover:bg-danger/90 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                :disabled="deleting" @click="confirmDelete">
          <Loader v-if="deleting" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" /> 确认删除
        </button>
      </footer>
    </div>
  </div>

  <!-- ==================== 新建工单弹窗 ==================== -->
  <div v-if="showCreate" class="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
       @click.self="!(creating || recommending) && (showCreate = false)">
    <div class="industrial-card w-full max-w-md bg-card overflow-hidden">
      <header class="px-5 py-3 border-b border-border flex items-center gap-2">
        <Sparkles class="w-4 h-4 text-ai" />
        <span class="font-semibold flex-1">{{ showMatchStep ? '发现相似工单' : 'AI 工单 · 自动生成检修步骤' }}</span>
        <button class="text-text-2 hover:text-danger" :disabled="creating || recommending" @click="showCreate = false">
          <X class="w-4 h-4" />
        </button>
      </header>

      <!-- 第一步：填写 -->
      <div v-if="!showMatchStep" class="p-5 space-y-3">
        <div>
          <div class="text-sm text-text-2 mb-1">设备</div>
          <input v-model="draft.device" placeholder="如：空压机-XG200" :disabled="recommending"
                 class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card mono" />
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">故障描述</div>
          <textarea v-model="draft.fault" rows="4" placeholder="一句话描述故障现象，AI 会按【风险预检/工具准备/检修步骤/验收标准】生成方案"
                    :disabled="recommending"
                    class="w-full px-3 py-2 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card resize-none"></textarea>
        </div>
        <div class="text-[11px] text-text-2 leading-relaxed">
          新建前会先为您匹配相似的已有工单；若无合适项再调用大模型生成（约 5–30 秒）。
        </div>
      </div>

      <!-- 第二步：相似推荐 -->
      <div v-else class="p-5 space-y-3 max-h-[60vh] overflow-y-auto">
        <div class="text-sm text-text-2">已为您找到 {{ createMatches.length }} 条相似工单，可直接添加；或选择继续新建。</div>
        <div v-for="t in createMatches" :key="t.id" class="industrial-card p-3">
          <div class="flex items-start gap-2">
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold">{{ t.fault || ('工单 #' + t.id) }}</div>
              <div class="text-[11px] text-text-2 mt-0.5 mono">
                {{ t.device }} · {{ t.creator || '其他用户' }}
                <span v-if="t.score" class="ml-1">· 匹配 {{ Math.round(t.score * 100) }}%</span>
              </div>
            </div>
            <button @click="addMatch(t)" :disabled="adding[t.id]"
                    class="h-8 px-3 rounded-btn border border-accent/40 text-accent text-xs font-semibold flex items-center gap-1 hover:bg-accent/10 disabled:opacity-60">
              <Loader v-if="adding[t.id]" class="w-3.5 h-3.5 animate-spin" />
              <UserPlus v-else class="w-3.5 h-3.5" /> 添加
            </button>
          </div>
        </div>
      </div>

      <footer class="px-5 py-3 border-t border-border flex justify-end gap-2">
        <button class="h-9 px-4 rounded-btn border border-border" :disabled="creating || recommending" @click="showCreate = false">取消</button>
        <button v-if="!showMatchStep"
                class="h-9 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                :disabled="recommending" @click="findSimilar">
          <Loader v-if="recommending" class="w-4 h-4 animate-spin" />
          <Sparkles v-else class="w-4 h-4" />
          {{ recommending ? '匹配中…' : '下一步' }}
        </button>
        <button v-else
                class="h-9 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                :disabled="creating" @click="doCreate">
          <Loader v-if="creating" class="w-4 h-4 animate-spin" />
          <Sparkles v-else class="w-4 h-4" />
          {{ creating ? 'AI 生成中…' : '仍要新建' }}
        </button>
      </footer>
    </div>
  </div>

  <!-- ==================== 工单时间线（审查员/管理员可在列表直接查看） ==================== -->
  <TicketTimeline v-if="timelineTarget"
                  :ticket-id="timelineTarget.ticketId"
                  :open="!!timelineTarget"
                  @close="timelineTarget = null" />
</template>
