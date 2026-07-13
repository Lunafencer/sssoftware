<script setup lang="ts">
/**
 * 作业指引 · 移动端详情（FIX3 第 4 项）
 *  - 使用 van-tabs 切换 步骤 / 工具 / 手册
 *  - 步骤独立卡片可勾选 done
 *  - 顶部"返回"回工单列表
 */
import { onMounted, computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkflowStore } from '@/stores/workflow'
import {
  getFlow, getWorkflowTools, getWorkflowManuals, completeTicket, syncStepProgress,
  type ToolItem, type ManualRef
} from '@/api/workflow'
import {
  ChevronLeft, CheckCircle2, AlertTriangle, Clock, Wrench, BookOpen,
  Loader, ExternalLink, Lock, ChevronDown, ListChecks, Search
} from 'lucide-vue-next'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import { renderMarkdown } from '@/utils/markdown'
import TicketTimeline from '@/components/common/TicketTimeline.vue'

const wf = useWorkflowStore()
const route = useRoute()
const router = useRouter()

type Tab = 'steps' | 'tools' | 'manuals'
const tab = ref<Tab>('steps')

const tools = ref<ToolItem[]>([])
const manuals = ref<ManualRef[]>([])
const toolsLoading = ref(false)
const manualsLoading = ref(false)

const orderId = computed(() => String(route.params.id || ''))
const isDemo = computed(() => !orderId.value || !orderId.value.startsWith('t-'))
const ticketNumId = computed(() => orderId.value.startsWith('t-') ? orderId.value.slice(2) : orderId.value)
const showTimeline = ref(false)

const loadFlow = async () => {
  syncReady.value = false
  const f = await getFlow(orderId.value || undefined)
  wf.setFlow(f)
  tab.value = 'steps'
  loadTools()
  loadManuals()
  syncReady.value = true
}

/** 将已完成的大步骤同步到后端（按用户维度记录时间线，FIX5 第 11 项） */
const syncReady = ref(false)
let syncTimer: number | null = null
watch(() => ({ ...wf.stepDone }), () => {
  if (!syncReady.value || isDemo.value || !wf.flow) return
  if (syncTimer) clearTimeout(syncTimer)
  syncTimer = window.setTimeout(() => {
    const doneIds = (wf.flow?.steps || []).filter(s => wf.stepDone[s.id]).map(s => s.id)
    syncStepProgress(orderId.value, doneIds).catch(() => {})
  }, 400)
}, { deep: true })

const loadTools = async () => {
  if (isDemo.value) { tools.value = []; return }
  toolsLoading.value = true
  try { tools.value = await getWorkflowTools(orderId.value) }
  catch { tools.value = [] }
  finally { toolsLoading.value = false }
}
const loadManuals = async () => {
  if (isDemo.value) { manuals.value = []; return }
  manualsLoading.value = true
  try { manuals.value = await getWorkflowManuals(orderId.value) }
  catch { manuals.value = [] }
  finally { manualsLoading.value = false }
}

onMounted(loadFlow)
watch(() => route.params.id, loadFlow)

const back = () => router.push('/workflow')

const onToggleStep = (stepId: string, hasChecks: boolean) => {
  if (hasChecks && !wf.allChecked(stepId) && !wf.stepDone[stepId]) {
    showFailToast('请先勾选所有校验点')
    if ('vibrate' in navigator) navigator.vibrate([60, 40, 60])
    return
  }
  wf.toggleStepDone(stepId)
  if ('vibrate' in navigator) navigator.vibrate(40)
}

/** FIX4 第 2 项：勾子步骤；被顺序约束拦截时给提示 */
const onToggleSub = (stepIdx: number, subIdx: number) => {
  if (isDemo.value) return
  const ok = wf.toggleSub(stepIdx, subIdx)
  if (!ok) {
    showFailToast('请先完成上一步')
    if ('vibrate' in navigator) navigator.vibrate([60, 40, 60])
  } else if ('vibrate' in navigator) {
    navigator.vibrate(30)
  }
}

const expanded = ref<Record<string, boolean>>({})
const toggleExpand = (stepId: string) => { expanded.value[stepId] = !expanded.value[stepId] }
watch(() => wf.flow?.id, () => {
  expanded.value = {}
  if (!wf.flow) return
  const firstUndone = wf.flow.steps.find(s => !wf.stepDone[s.id])
  if (firstUndone) expanded.value[firstUndone.id] = true
}, { immediate: true })

const subProgress = (stepId: string) => {
  const step = wf.flow?.steps.find(s => s.id === stepId)
  const subs = step?.subSteps || []
  if (!subs.length) return null
  const m = wf.subDone[stepId] || {}
  const done = subs.filter(ss => m[ss.id]).length
  return { done, total: subs.length }
}

/** 工具 Tab：合并后端 /tools 接口 + 步骤内 tools 字段 */
const toolQuery = ref('')
const aggregatedTools = computed<ToolItem[]>(() => {
  const map = new Map<string, ToolItem>()
  for (const t of tools.value) { if (t?.name) map.set(t.name, { ...t }) }
  for (const s of wf.flow?.steps || []) {
    for (const name of (s.tools || [])) {
      if (name && !map.has(name)) map.set(name, { name, qty: 1 })
    }
  }
  const list = Array.from(map.values())
  if (!toolQuery.value.trim()) return list
  const q = toolQuery.value.trim().toLowerCase()
  return list.filter(t => t.name.toLowerCase().includes(q) || (t.spec || '').toLowerCase().includes(q))
})

const allDone = computed(() => wf.flow && wf.flow.steps.length > 0 && wf.doneCount === wf.flow.steps.length)
const progressPct = computed(() => Math.round(wf.progress * 100))

const finalizeTicket = async () => {
  if (isDemo.value) { showToast({ message: '示例工单不会落库', type: 'success' }); return }
  if (!allDone.value) {
    try {
      await showConfirmDialog({ title: '尚有未完成步骤', message: '仍要标记为完成吗？' })
    } catch { return }
  }
  try {
    await completeTicket(orderId.value.slice(2))
    showToast({ type: 'success', message: '已归档至已完成' })
    router.push('/workflow')
  } catch {
    showFailToast('提交失败')
  }
}

const openManual = (m: ManualRef) => {
  if (m.docId) router.push(`/kb/preview/${m.docId}`)
}
</script>

<template>
  <div v-if="wf.flow" class="h-full flex flex-col">
    <!-- 顶部 -->
    <header class="flex-shrink-0 bg-card border-b border-border">
      <div class="h-12 flex items-center px-2 relative safe-top">
        <button @click="back" class="w-10 h-10 flex items-center justify-center" aria-label="返回">
          <ChevronLeft class="w-5 h-5" />
        </button>
        <div class="flex-1 min-w-0 px-1 text-center">
          <div class="text-[11px] text-text-2 leading-tight flex items-center justify-center gap-1.5">
            <span>工单列表 / </span>
            <span v-if="isDemo" class="px-1 py-px rounded bg-warning/10 text-warning border border-warning/30 text-[9px]">示例</span>
          </div>
          <div class="text-sm font-semibold truncate">{{ wf.flow.name }}</div>
        </div>
        <button v-if="!isDemo" @click="showTimeline = true"
                class="w-9 h-9 flex items-center justify-center text-text-2" aria-label="时间线">
          <Clock class="w-5 h-5" />
        </button>
        <button v-if="!isDemo" @click="finalizeTicket"
                class="h-9 px-2.5 rounded-btn bg-success text-white text-xs font-semibold flex items-center gap-1 mr-1">
          <CheckCircle2 class="w-3.5 h-3.5" /> 完成
        </button>
      </div>

      <div class="px-4 pb-2">
        <div class="flex items-center justify-between text-xs text-text-2 mb-1">
          <span class="mono">{{ wf.doneCount }}/{{ wf.totalSteps }} 已完成</span>
          <span class="mono text-accent font-semibold">{{ progressPct }}%</span>
        </div>
        <div class="h-1.5 bg-border rounded-full overflow-hidden">
          <div class="h-full bg-success transition-all duration-500"
               :style="{ width: progressPct + '%' }"></div>
        </div>
      </div>

      <div class="flex border-t border-border">
        <button v-for="t in [
                  { k: 'steps', l: '步骤', n: wf.totalSteps },
                  { k: 'tools', l: '工具', n: aggregatedTools.length },
                  { k: 'manuals', l: '手册', n: manuals.length }
                ]" :key="t.k" @click="tab = t.k as Tab"
                :class="['flex-1 h-10 text-sm flex items-center justify-center gap-1 border-b-2',
                         tab === t.k ? 'border-accent text-accent font-semibold' : 'border-transparent text-text-2']">
          {{ t.l }} <span class="mono text-[10px] px-1 rounded bg-bg">{{ t.n }}</span>
        </button>
      </div>
    </header>

    <main class="flex-1 overflow-auto bg-bg p-3 space-y-3">
      <!-- 步骤 -->
      <template v-if="tab === 'steps'">
        <div v-for="(s, i) in wf.flow.steps" :key="s.id"
             class="industrial-card overflow-hidden border-l-4"
             :class="[
               wf.stepDone[s.id] ? 'border-l-success bg-success/5'
                 : (wf.prevStepsDone(i) ? 'border-l-accent' : 'border-l-border opacity-70')
             ]">
          <header class="p-3 flex items-start gap-2.5 active:bg-bg/50"
                  @click="toggleExpand(s.id)">
            <input type="checkbox"
                   :checked="!!wf.stepDone[s.id]"
                   @click.stop
                   @change="onToggleStep(s.id, !!s.checkPoints?.length)"
                   :disabled="isDemo || (s.subSteps?.length ? !wf.allSubsDone(s.id) : !wf.prevStepsDone(i))"
                   class="w-5 h-5 mt-1 accent-success flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5 text-[11px] text-text-2 flex-wrap">
                <span class="mono">{{ i + 1 }}/{{ wf.totalSteps }}</span>
                <span v-if="!wf.prevStepsDone(i) && !wf.stepDone[s.id]"
                      class="inline-flex items-center gap-0.5 px-1 py-px rounded bg-text-2/10 text-text-2 text-[10px]">
                  <Lock class="w-2.5 h-2.5" /> 待解锁
                </span>
                <span class="inline-flex items-center gap-0.5"><Clock class="w-3 h-3" /> {{ s.estMinutes }}分</span>
                <span v-if="subProgress(s.id)" class="inline-flex items-center gap-0.5 text-accent">
                  <ListChecks class="w-3 h-3" /> {{ subProgress(s.id)!.done }}/{{ subProgress(s.id)!.total }}
                </span>
                <AlertTriangle v-if="s.hazardous" class="w-3 h-3 text-warning ml-auto" />
              </div>
              <h3 class="text-sm font-semibold mt-0.5"
                  :class="wf.stepDone[s.id] ? 'line-through text-text-2' : ''">{{ s.name }}</h3>
            </div>
            <ChevronDown class="w-4 h-4 text-text-2 mt-1 transition-transform"
                         :class="{ 'rotate-180': expanded[s.id] }" />
          </header>

          <div v-if="expanded[s.id]" class="px-3 pb-3 -mt-1 space-y-2">
            <div v-if="s.safetyNote || s.hazardous"
                 class="px-2 py-1 rounded-btn bg-warning/10 border border-warning/30 text-warning text-[11px] flex items-start gap-1">
              <AlertTriangle class="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{{ s.safetyNote || '严格执行 LOTO 与安全规程' }}</span>
            </div>
            <div v-if="s.desc" class="md-body text-sm" v-html="renderMarkdown(s.desc)"></div>

            <!-- FIX6-resume F1：子步骤——按钮放大、点击区分明 -->
            <div v-if="s.subSteps?.length" class="pt-2 border-t border-border">
              <div class="text-[11px] font-semibold mb-2 flex items-center gap-1">
                <ListChecks class="w-3 h-3 text-accent" />
                子步骤（顺序完成）
                <span class="ml-auto mono text-text-2">
                  {{ subProgress(s.id)?.done ?? 0 }} / {{ s.subSteps.length }}
                </span>
              </div>
              <ol class="space-y-2">
                <li v-for="(ss, si) in s.subSteps" :key="ss.id">
                  <div class="flex items-stretch gap-2 rounded-card border-2 overflow-hidden"
                       :class="[
                         wf.subDone[s.id]?.[ss.id]
                           ? 'border-success/40 bg-success/5'
                           : (wf.canCheckSub(i, si)
                               ? 'border-border bg-card'
                               : 'border-border bg-bg/40 opacity-60')
                       ]">
                    <div class="w-10 flex-shrink-0 flex items-center justify-center font-bold mono text-sm"
                         :class="wf.subDone[s.id]?.[ss.id]
                                  ? 'bg-success/10 text-success'
                                  : (wf.canCheckSub(i, si) ? 'bg-accent/10 text-accent' : 'bg-bg text-text-2')">
                      {{ i + 1 }}.{{ si + 1 }}
                    </div>
                    <div class="flex-1 min-w-0 py-2.5 pr-2 text-sm leading-snug self-center"
                         :class="wf.subDone[s.id]?.[ss.id] ? 'text-text-2 line-through' : ''">
                      {{ ss.content }}
                    </div>
                    <button
                      @click="onToggleSub(i, si)"
                      :disabled="isDemo || (!wf.canCheckSub(i, si) && !wf.subDone[s.id]?.[ss.id])"
                      class="flex-shrink-0 w-20 flex flex-col items-center justify-center gap-0.5 text-xs font-semibold border-l disabled:opacity-40"
                      :class="wf.subDone[s.id]?.[ss.id]
                                ? 'bg-success/10 text-success border-success/30'
                                : 'bg-accent text-white border-accent active:bg-accent-2'">
                      <Check v-if="wf.subDone[s.id]?.[ss.id]" class="w-4 h-4" />
                      <Lock v-else-if="!wf.canCheckSub(i, si)" class="w-4 h-4" />
                      <span v-else class="w-4 h-4 rounded-full border-2 border-current"></span>
                      <span>{{ wf.subDone[s.id]?.[ss.id] ? '已完成' : (wf.canCheckSub(i, si) ? '完成' : '未解锁') }}</span>
                    </button>
                  </div>
                </li>
              </ol>
            </div>

            <div v-if="s.tools?.length" class="flex flex-wrap gap-1 text-[11px]">
              <span v-for="t in s.tools" :key="t" class="px-1.5 py-0.5 rounded bg-bg border border-border">{{ t }}</span>
            </div>

            <!-- 旧版校验点（仅当无 subSteps） -->
            <div v-if="!s.subSteps?.length && s.checkPoints?.length" class="pt-2 border-t border-border">
              <div class="text-[11px] font-semibold mb-1">校验点</div>
              <label v-for="(cp, ci) in s.checkPoints" :key="ci"
                     class="flex items-start gap-2 px-1.5 py-1 active:bg-bg rounded text-sm">
                <input type="checkbox"
                       :checked="!!wf.checks[s.id]?.[ci]"
                       @change="wf.checks[s.id][ci] = !wf.checks[s.id][ci]"
                       :disabled="isDemo || !!wf.stepDone[s.id]"
                       class="w-4 h-4 mt-0.5 accent-accent flex-shrink-0" />
                <span :class="wf.checks[s.id]?.[ci] ? 'text-text-2 line-through' : ''">{{ cp }}</span>
              </label>
            </div>

            <div v-if="s.acceptance" class="px-2 py-1.5 rounded-btn bg-bg border border-border text-[11px]">
              <div class="text-text-2 font-semibold mb-0.5">验收标准</div>
              <div>{{ s.acceptance }}</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 工具 -->
      <template v-else-if="tab === 'tools'">
        <div v-if="toolsLoading" class="industrial-card p-8 text-center text-text-2">
          <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-sm">加载中…</div>
        </div>
        <template v-else>
          <div v-if="aggregatedTools.length || toolQuery"
               class="industrial-card p-2 flex items-center gap-1.5">
            <Search class="w-4 h-4 text-text-2 ml-1" />
            <input v-model="toolQuery" placeholder="过滤工具…"
                   class="flex-1 bg-transparent outline-none text-sm" />
            <button v-if="toolQuery" @click="toolQuery = ''" class="text-xs text-text-2 px-2">清空</button>
          </div>
          <div v-if="!aggregatedTools.length" class="industrial-card p-8 text-center text-text-2">
            <Wrench class="w-8 h-8 mx-auto opacity-40" />
            <div class="mt-2 text-sm">
              {{ isDemo ? '示例工单暂不提供工具清单' : (toolQuery ? '未匹配到工具' : '暂未提供工具清单') }}
            </div>
          </div>
          <div v-else class="space-y-2">
            <div v-for="(t, i) in aggregatedTools" :key="i" class="industrial-card p-3 flex items-start gap-3">
              <div class="w-10 h-10 rounded-card bg-accent/10 text-accent flex items-center justify-center flex-shrink-0">
                <Wrench class="w-5 h-5" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="text-sm font-semibold">{{ t.name }}</div>
                <div v-if="t.spec" class="text-[11px] text-text-2 mt-0.5 mono">{{ t.spec }}</div>
              </div>
              <span class="text-sm font-semibold text-accent mono flex-shrink-0">×{{ t.qty }}</span>
            </div>
          </div>
        </template>
      </template>

      <!-- 手册 -->
      <template v-else>
        <div v-if="manualsLoading" class="industrial-card p-8 text-center text-text-2">
          <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-sm">加载中…</div>
        </div>
        <div v-else-if="!manuals.length" class="industrial-card p-8 text-center text-text-2">
          <BookOpen class="w-8 h-8 mx-auto opacity-40" />
          <div class="mt-2 text-sm">{{ isDemo ? '示例工单暂不关联手册' : '暂未关联到任何手册' }}</div>
        </div>
        <ul v-else class="space-y-2">
          <li v-for="m in manuals" :key="m.docId"
              class="industrial-card p-3 flex items-start gap-2.5 active:bg-bg"
              @click="openManual(m)">
            <div class="w-9 h-9 rounded-card bg-ai/10 text-ai flex items-center justify-center flex-shrink-0">
              <BookOpen class="w-4 h-4" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold truncate">{{ m.title }}</div>
              <div class="text-[11px] text-text-2 mono">doc-{{ m.docId }}</div>
              <div v-if="m.matchedSection" class="text-[11px] text-text-2 mt-0.5 truncate">{{ m.matchedSection }}</div>
            </div>
            <ExternalLink class="w-4 h-4 text-text-2 flex-shrink-0 mt-1" />
          </li>
        </ul>
      </template>
    </main>
  </div>
  <div v-else class="p-12 text-center text-text-2">流程加载中…</div>

  <TicketTimeline :ticket-id="ticketNumId" :open="showTimeline" :steps="wf.flow?.steps" @close="showTimeline = false" />
</template>
