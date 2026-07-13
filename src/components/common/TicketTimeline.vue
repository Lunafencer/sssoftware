<script setup lang="ts">
/**
 * 工单时间线（FIX5 第 11 项 / FIX6 第 4 项 / FIX7 续）
 * - 员工（viewer='self'）：只看自己（events）
 * - 审查员/管理员（viewer='audit'）：按用户分组展示**所有用户**的时间线
 *   （即使分组为空也明确显示"暂无任何用户操作记录"，而不是回退到员工视角）
 * - 完整覆盖 5 种事件类型（created / added / step_completed / completed / deleted）
 *   各自配独立图标与颜色，对未知类型 fallback 到 Info。
 */
import { ref, watch, computed } from 'vue'
import { getTimeline, type TicketEvent } from '@/api/ticket'
import { useUserStore } from '@/stores/user'
import { formatTime } from '@/utils/format'
import {
  Loader, AlertTriangle, X, Clock, Users,
  PlusCircle, UserPlus, CheckCircle, Award, Trash2, Info
} from 'lucide-vue-next'

const props = defineProps<{ ticketId: number | string; open: boolean; steps?: any[] }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const userStore = useUserStore()

const loading = ref(false)
const error = ref<string | null>(null)
const events = ref<TicketEvent[]>([])
const grouped = ref<{ userId: number; user: string | null; events: TicketEvent[] }[]>([])
/** FIX7 续：以后端 viewer 为准，本地角色仅做兜底 */
const viewer = ref<'audit' | 'self'>('self')
const creatorName = ref<string | null>(null)
/** 是否按"所有用户视角"渲染（审查员/管理员） */
const isAuditView = computed(() => viewer.value === 'audit' || userStore.isAuditor)

interface EventStyle {
  icon: any
  iconCls: string
  dotCls: string
  label: string
}

const EVENT_STYLES: Record<string, EventStyle> = {
  created:        { icon: PlusCircle,  iconCls: 'text-accent',  dotCls: 'bg-accent',  label: '创建了工单' },
  added:          { icon: UserPlus,    iconCls: 'text-success', dotCls: 'bg-success', label: '加入了工单' },
  step_completed: { icon: CheckCircle, iconCls: 'text-warning', dotCls: 'bg-warning', label: '完成步骤' },
  completed:      { icon: Award,       iconCls: 'text-ai',      dotCls: 'bg-ai',      label: '完成工单' },
  deleted:        { icon: Trash2,      iconCls: 'text-danger',  dotCls: 'bg-danger',  label: '删除工单' }
}
const FALLBACK_STYLE: EventStyle = {
  icon: Info, iconCls: 'text-text-2', dotCls: 'bg-text-2', label: '事件'
}

const styleFor = (type: string): EventStyle => EVENT_STYLES[type] || FALLBACK_STYLE

/** 步骤索引/ID 解析为步骤标题（如可识别） */
const stepLabel = (ev: TicketEvent): string => {
  const sid = ev.detail?.stepId
  const sIdx = ev.detail?.stepIndex
  const steps = props.steps || []
  if (typeof sIdx === 'number' && steps[sIdx]?.title) return `第 ${sIdx + 1} 步：${steps[sIdx].title}`
  if (sid != null) {
    const m = steps.find((s: any) => String(s.id) === String(sid))
    if (m?.title) return `${sid} · ${m.title}`
    return `步骤 ${sid}`
  }
  return ''
}

const describe = (ev: TicketEvent): string => {
  const base = styleFor(ev.type).label
  if (ev.type === 'step_completed') {
    const sl = stepLabel(ev)
    return sl ? `${base} · ${sl}` : base
  }
  if (ev.type === 'deleted' && ev.detail?.reason) return `${base}：${ev.detail.reason}`
  if (ev.type === 'added' && ev.detail?.from) return `${base} · 来源 ${ev.detail.from}`
  return base
}

const load = async () => {
  loading.value = true
  error.value = null
  events.value = []
  grouped.value = []
  viewer.value = userStore.isAuditor ? 'audit' : 'self'
  creatorName.value = null
  try {
    const res = await getTimeline(props.ticketId)
    events.value = res.events || []
    grouped.value = res.grouped || []
    // 后端返回的 viewer 是权威值；缺省时按本地角色推断
    if (res.viewer === 'audit' || res.viewer === 'self') viewer.value = res.viewer
    creatorName.value = res.creator || null
    // FIX7 续：审查员视角下若 grouped 缺失而 events 非空（兼容旧后端 / 错误响应），
    // 将 events 包装成一个"当前用户"的分组，避免误回退到员工视角
    if (isAuditView.value && !grouped.value.length && events.value.length) {
      grouped.value = [{
        userId: Number(userStore.info?.id) || 0,
        user: userStore.info?.name || null,
        events: events.value,
      }]
      events.value = []
    }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// FIX7 续：用 immediate 监听确保「v-if 挂载即 open=true」的父用法也能触发 load
// （WorkList.vue 通过 v-if="timelineTarget" 挂载组件，open 启始就是 true，
// 若没有 immediate 监听不会触发，会导致管理员从列表点开未加入工单时时间线为空）
// 同时监听 ticketId，便于父组件切换查看不同工单时刷新。
watch(
  () => [props.open, props.ticketId] as const,
  ([v]) => { if (v) load() },
  { immediate: true }
)

const isEmpty = computed(() => !loading.value && !error.value && !grouped.value.length && !events.value.length)
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" @click.self="emit('close')">
    <div class="industrial-card w-full max-w-lg bg-card overflow-hidden flex flex-col max-h-[80vh]">
      <header class="px-5 py-3 border-b border-border flex items-center gap-2">
        <Clock class="w-4 h-4 text-accent" />
        <span class="font-semibold flex-1">
          {{ isAuditView ? '工单时间线 · 全部用户' : '工单时间线' }}
        </span>
        <span v-if="isAuditView" class="px-2 py-0.5 rounded-pill bg-ai/10 text-ai text-[11px] inline-flex items-center gap-1">
          <Users class="w-3 h-3" /> 审查视角
        </span>
        <button class="text-text-2 hover:text-danger" @click="emit('close')"><X class="w-4 h-4" /></button>
      </header>

      <div class="p-5 overflow-y-auto">
        <div v-if="loading" class="py-10 text-center text-text-2">
          <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-sm">加载时间线…</div>
        </div>
        <div v-else-if="error" class="py-10 text-center text-warning">
          <AlertTriangle class="w-7 h-7 mx-auto" />
          <div class="mt-2 text-sm">{{ error }}</div>
          <button @click="load" class="mt-3 h-8 px-4 rounded-btn border border-border text-sm hover:bg-bg">重试</button>
        </div>

        <!-- 审查员/管理员视角：始终按用户分组（即便只有一个用户，也明示"全部用户的时间线"） -->
        <template v-else-if="isAuditView">
          <div v-if="creatorName" class="text-xs text-text-2 mb-3">
            工单创建人 · <span class="font-medium text-text">{{ creatorName }}</span>
          </div>
          <template v-if="grouped.length">
            <div v-for="g in grouped" :key="g.userId" class="mb-5 last:mb-0">
              <div class="text-sm font-semibold text-text mb-2 flex items-center gap-1.5">
                <span class="w-6 h-6 rounded-full bg-ai/10 text-ai flex items-center justify-center text-[11px] font-bold">
                  {{ (g.user || '?').slice(0, 1) }}
                </span>
                {{ g.user || ('用户 #' + g.userId) }}
                <span class="text-[11px] text-text-2 font-normal">· {{ g.events.length }} 条事件</span>
              </div>
              <ol class="relative pl-6 space-y-3">
                <li v-for="(ev, i) in g.events" :key="i" class="relative">
                  <span class="absolute -left-6 top-0.5 w-5 h-5 rounded-full ring-2 ring-card flex items-center justify-center text-white"
                        :class="styleFor(ev.type).dotCls">
                    <component :is="styleFor(ev.type).icon" class="w-3 h-3" />
                  </span>
                  <span v-if="i < g.events.length - 1" class="absolute -left-[14px] top-6 w-px h-[calc(100%+0.25rem)] bg-border"></span>
                  <div class="text-sm font-medium" :class="styleFor(ev.type).iconCls">
                    {{ describe(ev) }}
                  </div>
                  <div class="text-xs text-text-2 mono mt-0.5">{{ formatTime(ev.at) }}</div>
                </li>
              </ol>
            </div>
          </template>
          <div v-else class="py-10 text-center text-text-2 text-sm">
            该工单暂无任何用户的操作记录
          </div>
        </template>

        <!-- 员工视角：只看自己的事件 -->
        <ol v-else-if="events.length" class="relative pl-6 space-y-3">
          <li v-for="(ev, i) in events" :key="i" class="relative">
            <span class="absolute -left-6 top-0.5 w-5 h-5 rounded-full ring-2 ring-card flex items-center justify-center text-white"
                  :class="styleFor(ev.type).dotCls">
              <component :is="styleFor(ev.type).icon" class="w-3 h-3" />
            </span>
            <span v-if="i < events.length - 1" class="absolute -left-[14px] top-6 w-px h-[calc(100%+0.25rem)] bg-border"></span>
            <div class="text-sm font-medium" :class="styleFor(ev.type).iconCls">
              {{ describe(ev) }}
            </div>
            <div class="text-xs text-text-2 mono mt-0.5">{{ formatTime(ev.at) }}</div>
          </li>
        </ol>

        <div v-else-if="isEmpty" class="py-10 text-center text-text-2 text-sm">暂无时间线记录</div>
      </div>
    </div>
  </div>
</template>
