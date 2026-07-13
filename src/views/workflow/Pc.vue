<script setup lang="ts">
/**
 * 作业指引 · PC 端详情（FIX4 第 2 项 · 三栏布局）
 *  布局：
 *    左 240px  ── 4 个大步骤的标题列表（点击切换）
 *    中  flex  ── 当前步骤的安全提示 / 描述 / 子步骤（按序勾选）
 *    右 320px  ── 工具清单（上）+ 关联手册（下）
 *  - 顶部面包屑可回列表，进度条贯穿三栏顶部
 *  - 完成工单 → POST /api/ticket/{id} status=done
 *  - 不再使用任何写死的"工具/手册"假数据，接口失败时显示空态
 */
import { onMounted, computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkflowStore } from '@/stores/workflow'
import {
  getFlow, getWorkflowTools, getWorkflowManuals, completeTicket, syncStepProgress,
  type ToolItem, type ManualRef
} from '@/api/workflow'
import {
  AlertTriangle, Clock, Wrench, BookOpen, ChevronLeft, ChevronRight,
  CheckCircle2, Loader, ListChecks, ExternalLink, Lock, Search,
  CircleDashed, Check
} from 'lucide-vue-next'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import { renderMarkdown } from '@/utils/markdown'
import TicketTimeline from '@/components/common/TicketTimeline.vue'

const wf = useWorkflowStore()
const route = useRoute()
const router = useRouter()

const tools = ref<ToolItem[]>([])
const manuals = ref<ManualRef[]>([])
const toolsLoading = ref(false)
const manualsLoading = ref(false)
const toolsError = ref(false)
const manualsError = ref(false)

const isDemo = computed(() =>
  !route.params.id || !String(route.params.id).startsWith('t-')
)

const orderId = computed(() => String(route.params.id || ''))
const ticketNumId = computed(() => orderId.value.startsWith('t-') ? orderId.value.slice(2) : orderId.value)
const showTimeline = ref(false)

/** 当前选中的大步骤索引（替代旧 Tab 系统） */
const activeIdx = ref(0)
const activeStep = computed(() => wf.flow?.steps[activeIdx.value])

const loadFlow = async () => {
  syncReady.value = false
  const id = orderId.value || undefined
  const f = await getFlow(id)
  wf.setFlow(f)
  // 默认定位到第一个未完成的大步骤
  const firstUndone = f.steps.findIndex(s => !wf.stepDone[s.id])
  activeIdx.value = firstUndone >= 0 ? firstUndone : 0
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
  if (isDemo.value) { tools.value = []; toolsError.value = false; return }
  toolsLoading.value = true
  toolsError.value = false
  try { tools.value = await getWorkflowTools(orderId.value) }
  catch { tools.value = []; toolsError.value = true }
  finally { toolsLoading.value = false }
}

const loadManuals = async () => {
  if (isDemo.value) { manuals.value = []; manualsError.value = false; return }
  manualsLoading.value = true
  manualsError.value = false
  try { manuals.value = await getWorkflowManuals(orderId.value) }
  catch { manuals.value = []; manualsError.value = true }
  finally { manualsLoading.value = false }
}

onMounted(loadFlow)
watch(() => route.params.id, loadFlow)

const remainingMinFmt = computed(() => {
  const m = wf.remainingMin
  if (m < 60) return `${m} 分钟`
  return `${Math.floor(m / 60)} 时 ${m % 60} 分`
})

const back = () => router.push('/workflow')

const onToggleStep = (stepId: string, hasChecks: boolean) => {
  if (hasChecks && !wf.allChecked(stepId) && !wf.stepDone[stepId]) {
    showFailToast('请先勾选该步骤的所有校验点')
    return
  }
  wf.toggleStepDone(stepId)
}

/** 勾子步骤；被顺序约束拦截时给提示 */
const onToggleSub = (stepIdx: number, subIdx: number) => {
  if (isDemo.value) return
  const ok = wf.toggleSub(stepIdx, subIdx)
  if (!ok) showFailToast('请先完成上一步')
}

/** 单个步骤的"x/y 子步骤已完成" */
const subProgress = (stepId: string) => {
  const step = wf.flow?.steps.find(s => s.id === stepId)
  const subs = step?.subSteps || []
  if (!subs.length) return null
  const m = wf.subDone[stepId] || {}
  const done = subs.filter(ss => m[ss.id]).length
  return { done, total: subs.length }
}

/** 工具清单：合并后端 /tools 接口 + 步骤内 tools 字段去重 */
const toolQuery = ref('')
const aggregatedTools = computed<ToolItem[]>(() => {
  const map = new Map<string, ToolItem>()
  for (const t of tools.value) {
    if (!t?.name) continue
    map.set(t.name, { ...t })
  }
  for (const s of wf.flow?.steps || []) {
    for (const name of (s.tools || [])) {
      if (!name) continue
      if (!map.has(name)) map.set(name, { name, qty: 1 })
    }
  }
  const list = Array.from(map.values())
  if (!toolQuery.value.trim()) return list
  const q = toolQuery.value.trim().toLowerCase()
  return list.filter(t => t.name.toLowerCase().includes(q) || (t.spec || '').toLowerCase().includes(q))
})

/** 当前步骤涉及的工具（高亮显示） */
const currentStepToolSet = computed(() => {
  const set = new Set<string>()
  for (const t of (activeStep.value?.tools || [])) set.add(t)
  return set
})

const allDone = computed(() => wf.flow && wf.flow.steps.length > 0 && wf.doneCount === wf.flow.steps.length)

const finalizeTicket = async () => {
  if (isDemo.value) {
    showToast({ message: '示例工单不会落库', type: 'success' })
    return
  }
  if (!allDone.value) {
    try {
      await showConfirmDialog({
        title: '尚有未完成步骤',
        message: '仍要将该工单标记为完成吗？已勾选的进度会保留。'
      })
    } catch { return }
  }
  try {
    const tid = orderId.value.slice(2)
    await completeTicket(tid)
    showToast({ type: 'success', message: '工单已归档至「已完成」' })
    router.push('/workflow')
  } catch {
    showFailToast('提交失败，请稍后重试')
  }
}

const openManual = (m: ManualRef) => {
  if (!m.docId) return
  router.push(`/kb/preview/${m.docId}`)
}

const progressPct = computed(() => Math.round(wf.progress * 100))

/** 切换大步骤 */
const selectStep = (idx: number) => { activeIdx.value = idx }
const goPrevStep = () => { if (activeIdx.value > 0) activeIdx.value-- }
const goNextStep = () => { if (wf.flow && activeIdx.value < wf.flow.steps.length - 1) activeIdx.value++ }
</script>

<template>
  <div v-if="wf.flow" class="h-full flex flex-col overflow-hidden">
    <!-- 顶部 -->
    <header class="flex-shrink-0 px-6 pt-3 pb-3 bg-card border-b border-border">
      <!-- 面包屑 -->
      <div class="flex items-center gap-1 text-xs text-text-2 mb-2">
        <button class="hover:text-accent" @click="back">工单列表</button>
        <ChevronRight class="w-3 h-3" />
        <span class="text-text font-medium truncate">{{ wf.flow.name }}</span>
      </div>

      <div class="flex items-start gap-4 flex-wrap">
        <button @click="back" class="h-9 px-3 rounded-btn border border-border bg-bg hover:bg-card flex items-center gap-1.5 text-sm flex-shrink-0">
          <ChevronLeft class="w-4 h-4" /> 返回列表
        </button>
        <button v-if="!isDemo" @click="showTimeline = true"
                class="h-9 px-3 rounded-btn border border-border bg-bg hover:bg-card flex items-center gap-1.5 text-sm flex-shrink-0">
          <Clock class="w-4 h-4" /> 时间线
        </button>

        <div class="flex-1 min-w-72">
          <div class="text-xs text-text-2 mb-1 flex items-center gap-2">
            <span class="mono">{{ wf.flow.id }}</span>
            <span v-if="isDemo" class="px-1.5 py-0.5 rounded bg-warning/10 text-warning border border-warning/30 text-[10px]">示例工单</span>
          </div>
          <h1 class="text-xl font-bold text-primary">{{ wf.flow.name }}</h1>
          <div class="text-sm text-text-2 mt-1 flex items-center gap-3">
            <span class="mono">{{ wf.flow.deviceModel }}</span>
            <span class="px-2 py-0.5 rounded text-xs"
                  :class="wf.flow.level === 1 ? 'bg-success/10 text-success'
                       : wf.flow.level === 2 ? 'bg-warning/10 text-warning'
                       : 'bg-danger/10 text-danger'">
              {{ ['', '一级·常规', '二级·重要', '三级·紧急'][wf.flow.level] }}
            </span>
            <span>共 {{ wf.totalSteps }} 步 · 剩余 ~{{ remainingMinFmt }}</span>
          </div>
        </div>

        <div class="flex-1 min-w-96 max-w-2xl">
          <div class="flex items-center gap-3 mb-2 text-sm">
            <div class="text-text-2">总进度</div>
            <div class="font-semibold text-accent mono">{{ progressPct }}%</div>
            <div class="text-text-2 ml-auto mono">{{ wf.doneCount }} / {{ wf.totalSteps }} 已完成</div>
          </div>
          <div class="h-2 bg-border rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-accent to-accent-2 transition-all"
                 :style="{ width: progressPct + '%' }"></div>
          </div>
        </div>

        <button v-if="!isDemo" @click="finalizeTicket"
                class="h-9 px-4 rounded-btn bg-success hover:bg-success/90 text-white font-semibold flex items-center gap-1.5 text-sm flex-shrink-0">
          <CheckCircle2 class="w-4 h-4" /> 完成工单
        </button>
      </div>
    </header>

    <!-- 三栏主体 -->
    <div class="flex-1 overflow-hidden flex bg-bg">
      <!-- ========================= 左：步骤标题列表 ========================= -->
      <aside class="w-60 flex-shrink-0 border-r border-border bg-card overflow-y-auto">
        <div class="px-4 pt-4 pb-2 text-xs font-semibold text-text-2 flex items-center gap-2">
          <ListChecks class="w-3.5 h-3.5 text-accent" /> 检修步骤
          <span class="ml-auto mono">{{ wf.totalSteps }}</span>
        </div>
        <ol class="px-2 pb-3 space-y-1">
          <li v-for="(s, i) in wf.flow.steps" :key="s.id">
            <button @click="selectStep(i)"
                    :disabled="!wf.prevStepsDone(i) && !wf.stepDone[s.id]"
                    class="w-full text-left rounded-btn px-3 py-2.5 transition border flex items-start gap-2.5 group"
                    :class="[
                      i === activeIdx
                        ? 'border-accent bg-accent/10'
                        : 'border-transparent hover:border-border hover:bg-bg',
                      wf.stepDone[s.id] ? 'text-text-2' : 'text-text',
                      (!wf.prevStepsDone(i) && !wf.stepDone[s.id]) ? 'opacity-50 cursor-not-allowed' : ''
                    ]">
              <!-- 状态图标 -->
              <span class="mt-0.5 w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 border text-[11px] font-bold"
                    :class="[
                      wf.stepDone[s.id]
                        ? 'bg-success text-white border-success'
                        : (i === activeIdx
                            ? 'bg-accent text-white border-accent'
                            : (!wf.prevStepsDone(i) ? 'bg-bg text-text-2 border-border' : 'bg-card text-text-2 border-border'))
                    ]">
                <Check v-if="wf.stepDone[s.id]" class="w-3.5 h-3.5" />
                <Lock v-else-if="!wf.prevStepsDone(i)" class="w-3 h-3" />
                <span v-else>{{ i + 1 }}</span>
              </span>
              <div class="flex-1 min-w-0">
                <div class="text-sm font-semibold leading-snug truncate"
                     :class="wf.stepDone[s.id] ? 'line-through' : ''">
                  {{ s.name }}
                </div>
                <div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-text-2 flex-wrap">
                  <span v-if="subProgress(s.id)" class="inline-flex items-center gap-0.5">
                    <ListChecks class="w-3 h-3" />
                    {{ subProgress(s.id)!.done }}/{{ subProgress(s.id)!.total }}
                  </span>
                  <span class="inline-flex items-center gap-0.5">
                    <Clock class="w-3 h-3" /> {{ s.estMinutes }}m
                  </span>
                  <span v-if="s.hazardous" class="inline-flex items-center gap-0.5 text-warning">
                    <AlertTriangle class="w-3 h-3" />
                  </span>
                </div>
              </div>
            </button>
          </li>
        </ol>

        <div v-if="!wf.flow.steps.length" class="px-4 py-8 text-center text-text-2 text-xs">
          <CircleDashed class="w-8 h-8 mx-auto opacity-40" />
          <div class="mt-2">尚未生成检修步骤</div>
        </div>
      </aside>

      <!-- ========================= 中：当前步骤的详细操作 ========================= -->
      <main class="flex-1 overflow-y-auto p-6 min-w-0">
        <div v-if="activeStep" class="max-w-3xl mx-auto space-y-4">
          <!-- 步骤标题区 -->
          <div class="industrial-card p-5 border-l-4 transition"
               :class="wf.stepDone[activeStep.id] ? 'border-l-success bg-success/5'
                       : (wf.prevStepsDone(activeIdx) ? 'border-l-accent' : 'border-l-border opacity-80')">
            <div class="flex items-start gap-3">
              <input type="checkbox"
                     :checked="!!wf.stepDone[activeStep.id]"
                     @change="onToggleStep(activeStep.id, !!activeStep.checkPoints?.length)"
                     :disabled="isDemo || (activeStep.subSteps?.length ? !wf.allSubsDone(activeStep.id) : !wf.prevStepsDone(activeIdx))"
                     class="w-5 h-5 mt-1 accent-success flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="mono text-xs text-text-2">步骤 {{ activeIdx + 1 }} / {{ wf.totalSteps }}</span>
                  <span v-if="!wf.prevStepsDone(activeIdx) && !wf.stepDone[activeStep.id]"
                        class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-text-2/10 text-text-2">
                    <Lock class="w-3 h-3" /> 请先完成上一步
                  </span>
                  <span class="inline-flex items-center gap-1 text-xs text-text-2">
                    <Clock class="w-3 h-3" /> 预计 {{ activeStep.estMinutes }} 分钟
                  </span>
                  <span v-if="subProgress(activeStep.id)" class="inline-flex items-center gap-1 text-xs text-accent">
                    <ListChecks class="w-3 h-3" />
                    {{ subProgress(activeStep.id)!.done }} / {{ subProgress(activeStep.id)!.total }} 已完成
                  </span>
                  <span v-if="activeStep.hazardous"
                        class="inline-flex items-center gap-1 text-xs text-warning ml-auto">
                    <AlertTriangle class="w-3 h-3" /> 危险作业
                  </span>
                </div>
                <h2 class="text-lg font-bold mt-1.5"
                    :class="wf.stepDone[activeStep.id] ? 'line-through text-text-2' : ''">
                  {{ activeStep.name }}
                </h2>
              </div>
            </div>

            <!-- 安全提醒 -->
            <div v-if="activeStep.safetyNote || activeStep.hazardous"
                 class="mt-3 px-3 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-start gap-2">
              <AlertTriangle class="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{{ activeStep.safetyNote || '严格执行 LOTO 与安全规程' }}</span>
            </div>

            <!-- 步骤描述 -->
            <div v-if="activeStep.desc" class="md-body mt-3 text-sm" v-html="renderMarkdown(activeStep.desc)"></div>
          </div>

          <!-- 子步骤列表（FIX6-resume F1：放大点击区、按钮明显化） -->
          <div v-if="activeStep.subSteps?.length" class="industrial-card p-5">
            <div class="text-sm font-semibold mb-3 flex items-center gap-2">
              <ListChecks class="w-4 h-4 text-accent" />
              详细操作（按顺序完成才能进入下一步）
              <span class="ml-auto text-xs text-text-2 mono">
                {{ subProgress(activeStep.id)?.done ?? 0 }} / {{ activeStep.subSteps.length }}
              </span>
            </div>
            <ol class="space-y-3">
              <li v-for="(ss, si) in activeStep.subSteps" :key="ss.id">
                <div class="flex items-stretch gap-3 rounded-card transition border-2 overflow-hidden"
                     :class="[
                       wf.subDone[activeStep.id]?.[ss.id]
                         ? 'border-success/40 bg-success/5'
                         : (wf.canCheckSub(activeIdx, si)
                             ? 'border-border hover:border-accent/60 bg-card'
                             : 'border-border bg-bg/40 opacity-60')
                     ]">
                  <!-- 序号块 -->
                  <div class="w-12 flex-shrink-0 flex items-center justify-center font-bold mono text-base"
                       :class="wf.subDone[activeStep.id]?.[ss.id]
                                ? 'bg-success/10 text-success'
                                : (wf.canCheckSub(activeIdx, si) ? 'bg-accent/10 text-accent' : 'bg-bg text-text-2')">
                    {{ activeIdx + 1 }}.{{ si + 1 }}
                  </div>
                  <!-- 文本 -->
                  <div class="flex-1 min-w-0 py-3 pr-3 text-sm leading-relaxed self-center"
                       :class="wf.subDone[activeStep.id]?.[ss.id] ? 'text-text-2 line-through' : ''">
                    {{ ss.content }}
                  </div>
                  <!-- 大完成按钮 -->
                  <button
                    @click="onToggleSub(activeIdx, si)"
                    :disabled="isDemo || (!wf.canCheckSub(activeIdx, si) && !wf.subDone[activeStep.id]?.[ss.id])"
                    class="flex-shrink-0 w-32 flex items-center justify-center gap-2 font-semibold text-sm border-l transition disabled:opacity-40 disabled:cursor-not-allowed"
                    :class="wf.subDone[activeStep.id]?.[ss.id]
                              ? 'bg-success/10 text-success border-success/30 hover:bg-success/15'
                              : 'bg-accent text-white border-accent hover:bg-accent-2'">
                    <Check v-if="wf.subDone[activeStep.id]?.[ss.id]" class="w-4 h-4" />
                    <Lock v-else-if="!wf.canCheckSub(activeIdx, si)" class="w-4 h-4" />
                    <CircleDashed v-else class="w-4 h-4" />
                    <span>
                      {{ wf.subDone[activeStep.id]?.[ss.id]
                           ? '已完成'
                           : (wf.canCheckSub(activeIdx, si) ? '标记完成' : '未解锁') }}
                    </span>
                  </button>
                </div>
              </li>
            </ol>
          </div>

          <!-- 旧版校验点（兼容；只在没有子步骤时显示） -->
          <div v-else-if="activeStep.checkPoints?.length" class="industrial-card p-5">
            <div class="text-sm font-semibold mb-3">校验点（必须勾选才能完成本步骤）</div>
            <div class="space-y-2">
              <label v-for="(cp, ci) in activeStep.checkPoints" :key="ci"
                     class="flex items-start gap-2 px-3 py-2 rounded-btn hover:bg-bg cursor-pointer transition text-sm border border-border">
                <input type="checkbox"
                       :checked="!!wf.checks[activeStep.id]?.[ci]"
                       @change="wf.checks[activeStep.id][ci] = !wf.checks[activeStep.id][ci]"
                       :disabled="isDemo || !!wf.stepDone[activeStep.id]"
                       class="w-4 h-4 mt-0.5 accent-accent flex-shrink-0" />
                <span :class="wf.checks[activeStep.id]?.[ci] ? 'text-text-2 line-through' : ''">{{ cp }}</span>
              </label>
            </div>
          </div>

          <!-- 验收标准 -->
          <div v-if="activeStep.acceptance" class="industrial-card p-5">
            <div class="text-sm font-semibold mb-2 text-success flex items-center gap-2">
              <CheckCircle2 class="w-4 h-4" /> 验收标准
            </div>
            <div class="text-sm text-text leading-relaxed">{{ activeStep.acceptance }}</div>
          </div>

          <!-- FIX6-resume F1：中部不再放上一步/下一步导航，按钮统一放到右侧底栏 -->
        </div>
        <div v-else class="py-12 text-center text-text-2">
          <CircleDashed class="w-10 h-10 mx-auto opacity-40" />
          <div class="mt-3 text-sm">未选择步骤</div>
        </div>
      </main>

      <!-- ========================= 右：工具清单 + 关联手册 + 步骤导航底栏 ========================= -->
      <aside class="w-80 flex-shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
        <!-- 工具清单 -->
        <section class="flex-1 min-h-0 flex flex-col border-b border-border">
          <header class="px-4 pt-3 pb-2 flex-shrink-0">
            <div class="text-xs font-semibold text-text-2 flex items-center gap-2">
              <Wrench class="w-3.5 h-3.5 text-accent" /> 工具清单
              <span class="ml-auto mono">{{ aggregatedTools.length }}</span>
            </div>
            <div v-if="aggregatedTools.length || toolQuery" class="mt-2 flex items-center gap-1.5 px-2 h-8 rounded-btn border border-border bg-bg">
              <Search class="w-3.5 h-3.5 text-text-2" />
              <input v-model="toolQuery" placeholder="过滤工具…"
                     class="flex-1 bg-transparent outline-none text-xs" />
              <button v-if="toolQuery" @click="toolQuery = ''" class="text-[10px] text-text-2 px-1 hover:text-accent">清空</button>
            </div>
          </header>
          <div class="flex-1 overflow-y-auto px-3 pb-3">
            <div v-if="toolsLoading" class="py-8 text-center text-text-2">
              <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
              <div class="mt-2 text-xs">加载工具…</div>
            </div>
            <div v-else-if="!aggregatedTools.length" class="py-8 text-center text-text-2">
              <Wrench class="w-8 h-8 mx-auto opacity-40" />
              <div class="mt-2 text-xs">
                {{ isDemo ? '示例工单暂不提供工具清单' : (toolQuery ? '未匹配到工具' : '暂未提供工具清单') }}
              </div>
              <div v-if="!toolQuery && !isDemo" class="mt-1 text-[10px]">
                {{ toolsError ? '后端接口不可达' : '后端尚未维护工具列表' }}
              </div>
            </div>
            <ul v-else class="space-y-1.5">
              <li v-for="(t, i) in aggregatedTools" :key="i"
                  class="px-2 py-2 rounded-btn flex items-start gap-2 text-sm transition border"
                  :class="currentStepToolSet.has(t.name)
                          ? 'border-accent/40 bg-accent/5'
                          : 'border-border'">
                <div class="w-7 h-7 rounded bg-accent/10 text-accent flex items-center justify-center flex-shrink-0">
                  <Wrench class="w-3.5 h-3.5" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-xs font-semibold truncate">{{ t.name }}</div>
                  <div v-if="t.spec" class="text-[10px] text-text-2 truncate mono">{{ t.spec }}</div>
                </div>
                <span class="text-xs font-semibold text-accent mono flex-shrink-0">×{{ t.qty }}</span>
              </li>
            </ul>
          </div>
        </section>

        <!-- 关联手册 -->
        <section class="flex-1 min-h-0 flex flex-col">
          <header class="px-4 pt-3 pb-2 flex-shrink-0">
            <div class="text-xs font-semibold text-text-2 flex items-center gap-2">
              <BookOpen class="w-3.5 h-3.5 text-ai" /> 关键手册
              <span class="ml-auto mono">{{ manuals.length }}</span>
            </div>
          </header>
          <div class="flex-1 overflow-y-auto px-3 pb-3">
            <div v-if="manualsLoading" class="py-8 text-center text-text-2">
              <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
              <div class="mt-2 text-xs">加载手册…</div>
            </div>
            <div v-else-if="!manuals.length" class="py-8 text-center text-text-2">
              <BookOpen class="w-8 h-8 mx-auto opacity-40" />
              <div class="mt-2 text-xs">
                {{ isDemo ? '示例工单暂不关联手册' : '暂未关联到任何手册' }}
              </div>
              <div v-if="!isDemo" class="mt-1 text-[10px]">
                {{ manualsError ? '后端接口不可达' : '可让管理员上传相关手册' }}
              </div>
            </div>
            <ul v-else class="space-y-1.5">
              <li v-for="m in manuals" :key="m.docId"
                  class="px-2 py-2 rounded-btn flex items-start gap-2 cursor-pointer hover:border-ai border border-border transition"
                  @click="openManual(m)">
                <div class="w-7 h-7 rounded bg-ai/10 text-ai flex items-center justify-center flex-shrink-0">
                  <BookOpen class="w-3.5 h-3.5" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-xs font-semibold truncate">{{ m.title }}</div>
                  <div class="text-[10px] text-text-2 mono">doc-{{ m.docId }}</div>
                  <div v-if="m.matchedSection" class="text-[10px] text-text-2 truncate mt-0.5">
                    {{ m.matchedSection }}
                  </div>
                </div>
                <div class="flex flex-col items-end gap-0.5 flex-shrink-0">
                  <span class="text-[10px] mono text-accent">{{ Math.round((m.score || 0) * 100) }}%</span>
                  <ExternalLink class="w-3 h-3 text-text-2" />
                </div>
              </li>
            </ul>
          </div>
        </section>

        <!-- FIX6-resume F1：右侧底部固定的步骤导航按钮区（突出"下一步"） -->
        <section class="flex-shrink-0 border-t border-border bg-bg/40 px-3 py-3 space-y-2">
          <div class="flex items-center justify-between text-xs text-text-2 mono px-1">
            <span>步骤 {{ activeIdx + 1 }} / {{ wf.totalSteps }}</span>
            <span v-if="activeStep && subProgress(activeStep.id)" class="text-accent">
              {{ subProgress(activeStep.id)!.done }}/{{ subProgress(activeStep.id)!.total }} 子步骤
            </span>
          </div>
          <div class="flex gap-2">
            <button @click="goPrevStep" :disabled="activeIdx === 0"
                    class="flex-1 h-11 rounded-btn border border-border bg-card hover:bg-bg flex items-center justify-center gap-1.5 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed">
              <ChevronLeft class="w-4 h-4" /> 上一步
            </button>
            <button @click="goNextStep" :disabled="activeIdx >= wf.totalSteps - 1"
                    class="flex-1 h-11 rounded-btn bg-accent hover:bg-accent-2 text-white flex items-center justify-center gap-1.5 text-sm font-semibold shadow-card disabled:opacity-40 disabled:cursor-not-allowed">
              下一步 <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </section>
      </aside>
    </div>

    <!-- 底部完成提示 -->
    <footer v-if="allDone && !isDemo" class="flex-shrink-0 px-6 py-3 border-t border-border bg-success/5 flex items-center gap-3">
      <CheckCircle2 class="w-5 h-5 text-success" />
      <span class="text-sm font-semibold text-success">所有步骤已勾选完成</span>
      <button @click="finalizeTicket"
              class="ml-auto h-9 px-5 rounded-btn bg-success hover:bg-success/90 text-white font-semibold text-sm flex items-center gap-2">
        <CheckCircle2 class="w-4 h-4" /> 提交并归档
      </button>
    </footer>
  </div>
  <div v-else class="p-12 text-center text-text-2">流程加载中…</div>

  <TicketTimeline :ticket-id="ticketNumId" :open="showTimeline" :steps="wf.flow?.steps" @close="showTimeline = false" />
</template>
