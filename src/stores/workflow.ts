import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { SopFlow } from '@/api/workflow'
import { storage } from '@/utils/storage'
import { useUserStore } from '@/stores/user'

/**
 * 作业指引状态（FIX3 第 4 项 + FIX4 第 2 项）
 * - 步骤勾选 done 状态：以**后端 progress.stepDone 为唯一权威**（FIX7 续）
 * - 校验点 checks / 子步骤 subDone：UI 辅助状态，按 (userId, orderId) 持久化
 * - FIX4 第 2 项：subDone 跟踪每个大步骤下子步骤的完成；
 *   严格顺序约束（前序未完则后序不可勾）；
 *   全部子步骤勾选完毕，大步骤自动 done。
 *
 * FIX7 续：localStorage key 加入 userId 隔离，并不再缓存 stepDone——
 * 之前 `workorder:steps:t-5` 是全局 key，会导致：
 *   1) 不同用户共用同一台机器时互相污染勾选；
 *   2) 开发期重建 DB 后新工单复用旧 ticket id 时显示"默认全部完成"，
 *      首次同步还会把脏状态刷到后端。
 */
const CHECK_KEY = (uid: string, orderId: string) => `workorder:checks:${uid}:${orderId}`
const SUB_KEY   = (uid: string, orderId: string) => `workorder:subs:${uid}:${orderId}`

export const useWorkflowStore = defineStore('workflow', () => {
  const userStore = useUserStore()
  const uid = () => String(userStore.info?.id || 'anonymous')

  // FIX7 续：一次性清理旧版（未隔离用户、且会污染勾选）的 localStorage key
  // 旧 key 形如 `workorder:steps:t-N` / `workorder:checks:t-N` / `workorder:subs:t-N`，
  // 新 key 形如 `workorder:checks:<uid>:t-N` / `workorder:subs:<uid>:t-N`（stepDone 不再缓存）
  try {
    const LEGACY_RE = /^workorder:(steps|checks|subs):t-\d+$/
    const removed: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && LEGACY_RE.test(k)) removed.push(k)
    }
    removed.forEach(k => localStorage.removeItem(k))
  } catch { /* 浏览器禁用 localStorage 时静默忽略 */ }

  const flow = ref<SopFlow | null>(null)
  const currentIdx = ref(0)
  /** 步骤校验点的勾选 */
  const checks = ref<Record<string, boolean[]>>({})
  /** 整步是否已完成（来源：后端 progress.stepDone，唯一权威） */
  const stepDone = ref<Record<string, boolean>>({})
  /** 子步骤完成状态：subDone[stepId][subId] = true（FIX4 第 2 项） */
  const subDone = ref<Record<string, Record<string, boolean>>>({})

  const totalSteps = computed(() => flow.value?.steps.length || 0)
  const doneCount = computed(() =>
    flow.value?.steps.reduce((n, s) => n + (stepDone.value[s.id] ? 1 : 0), 0) || 0
  )
  const progress = computed(() =>
    totalSteps.value === 0 ? 0 : Math.min(1, doneCount.value / totalSteps.value)
  )
  const currentStep = computed(() => flow.value?.steps[currentIdx.value])
  const remainingMin = computed(() => {
    if (!flow.value) return 0
    return flow.value.steps
      .filter(s => !stepDone.value[s.id])
      .reduce((s, st) => s + st.estMinutes, 0)
  })

  const setFlow = (f: SopFlow) => {
    flow.value = f
    currentIdx.value = 0
    const u = uid()
    // 加载持久化的勾选（仅 UI 辅助状态——checks / subs）
    const persistedChecks = storage.get<Record<string, boolean[]>>(CHECK_KEY(u, f.id)) || {}
    const persistedSubs   = storage.get<Record<string, Record<string, boolean>>>(SUB_KEY(u, f.id)) || {}

    // FIX7 续：stepDone 严格来自后端 progress.stepDone，不读 localStorage
    const doneFromBackend = new Set((f.stepDone || []).map(String))
    const checksMap: Record<string, boolean[]> = {}
    const subsMap: Record<string, Record<string, boolean>> = {}
    const doneMap: Record<string, boolean> = {}
    f.steps.forEach(s => {
      const saved = persistedChecks[s.id]
      checksMap[s.id] = (s.checkPoints || []).map((_, i) =>
        Array.isArray(saved) && typeof saved[i] === 'boolean' ? saved[i] : false
      )
      const savedSubs = persistedSubs[s.id] || {}
      const subMap: Record<string, boolean> = {}
      const stepDoneByBackend = doneFromBackend.has(String(s.id))
      ;(s.subSteps || []).forEach(ss => {
        // 大步骤后端已标完成时，把它的所有子步骤补勾上（UI 一致性）
        subMap[ss.id] = stepDoneByBackend ? true : !!savedSubs[ss.id]
      })
      subsMap[s.id] = subMap
      doneMap[s.id] = stepDoneByBackend
    })
    checks.value = checksMap
    stepDone.value = doneMap
    subDone.value = subsMap
  }

  // 持久化（节流到 200ms）—— 仅 UI 辅助状态
  let saveTimer: number | null = null
  const persist = () => {
    if (!flow.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => {
      if (!flow.value) return
      const u = uid()
      storage.set(CHECK_KEY(u, flow.value.id), checks.value)
      storage.set(SUB_KEY(u,   flow.value.id), subDone.value)
    }, 200)
  }
  watch(checks,  persist, { deep: true })
  watch(subDone, persist, { deep: true })

  const allChecked = (stepId: string) =>
    (checks.value[stepId] || []).every(Boolean)

  /** FIX4 第 2 项：本步骤的所有子步骤都已勾选 */
  const allSubsDone = (stepId: string) => {
    const step = flow.value?.steps.find(s => s.id === stepId)
    const subs = step?.subSteps || []
    if (!subs.length) return true
    const m = subDone.value[stepId] || {}
    return subs.every(ss => m[ss.id])
  }

  /** 当前大步骤之前的所有大步骤是否已完成（用于"按序"约束） */
  const prevStepsDone = (stepIdx: number): boolean => {
    if (!flow.value || stepIdx <= 0) return true
    for (let i = 0; i < stepIdx; i++) {
      const s = flow.value.steps[i]
      if (!stepDone.value[s.id] && !allSubsDone(s.id)) return false
    }
    return true
  }

  /** 子步骤是否可勾选（前序子步骤都已完成 + 前序大步骤都已完成） */
  const canCheckSub = (stepIdx: number, subIdx: number): boolean => {
    if (!flow.value) return false
    if (!prevStepsDone(stepIdx)) return false
    const step = flow.value.steps[stepIdx]
    const subs = step?.subSteps || []
    if (subIdx <= 0) return true
    const m = subDone.value[step.id] || {}
    for (let i = 0; i < subIdx; i++) {
      if (!m[subs[i].id]) return false
    }
    return true
  }

  /**
   * 切换子步骤勾选状态。返回 true=操作成功；false=被顺序约束拦截。
   *  - 已勾选 → 取消时连带把它后面的子步骤一并清空（保持有序）
   *  - 全部子步骤勾完 → 自动把大步骤 stepDone 置 true
   */
  const toggleSub = (stepIdx: number, subIdx: number): boolean => {
    if (!flow.value) return false
    const step = flow.value.steps[stepIdx]
    const subs = step?.subSteps || []
    const sub = subs[subIdx]
    if (!sub) return false
    if (!subDone.value[step.id]) subDone.value[step.id] = {}
    const m = subDone.value[step.id]
    const cur = !!m[sub.id]
    if (!cur) {
      // 勾选：必须满足顺序
      if (!canCheckSub(stepIdx, subIdx)) return false
      m[sub.id] = true
      // 自动标记大步骤完成
      if (allSubsDone(step.id)) stepDone.value[step.id] = true
    } else {
      // 取消勾选：连带取消其后子步骤；大步骤回到未完成
      for (let i = subIdx; i < subs.length; i++) m[subs[i].id] = false
      stepDone.value[step.id] = false
    }
    return true
  }

  const toggleStepDone = (stepId: string) => {
    stepDone.value[stepId] = !stepDone.value[stepId]
  }

  const setStepDone = (stepId: string, done: boolean) => {
    stepDone.value[stepId] = done
  }

  const next = () => {
    if (currentIdx.value < totalSteps.value - 1) {
      if ('vibrate' in navigator) navigator.vibrate(60)
      currentIdx.value++
    }
  }
  const prev = () => { if (currentIdx.value > 0) currentIdx.value-- }

  return {
    flow, currentIdx, checks, stepDone, subDone,
    totalSteps, doneCount, progress, currentStep, remainingMin,
    setFlow, allChecked, allSubsDone, prevStepsDone, canCheckSub,
    toggleSub, toggleStepDone, setStepDone, next, prev
  }
})
