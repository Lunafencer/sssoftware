<script setup lang="ts">
/**
 * 知识审查（FIX3 第 7.4 项）
 *  - 路由 /audit/knowledge，roles: ['auditor', 'admin']
 *  - 三个 Tab：待审 / 已通过 / 已驳回
 *  - 待审：通过 / 驳回（驳回须填原因）
 *  - 已通过：下架（须填原因）
 *  - 通过后由后端触发向量化、入图谱
 */
import { computed, onMounted, ref, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDevice } from '@/composables/useDevice'
import { useUserStore } from '@/stores/user'
import {
  listDocs, reviewDoc, exportDoc, type KbDoc, type ReviewAction,
  STATUS_LABEL
} from '@/api/kb'
import {
  ShieldCheck, FileText, Loader, RefreshCw, Search, Check, X, AlertTriangle,
  ChevronLeft, ArrowDown, Download
} from 'lucide-vue-next'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import { Field as VanField } from 'vant'

const router = useRouter()
const { isPC } = useDevice()
const user = useUserStore()

type Tab = 'pending' | 'approved' | 'rejected'
const tab = ref<Tab>('pending')
const docs = ref<KbDoc[]>([])
const loading = ref(false)
const offline = ref(false)
const q = ref('')

const refresh = async () => {
  loading.value = true
  try {
    docs.value = await listDocs({ status: tab.value })
    offline.value = false
  } catch {
    docs.value = []
    offline.value = true
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

const filtered = computed(() =>
  docs.value.filter(d =>
    !q.value || d.title.toLowerCase().includes(q.value.toLowerCase())
  )
)

const switchTab = async (t: Tab) => {
  tab.value = t
  await refresh()
}

const promptReason = async (d: KbDoc, action: Extract<ReviewAction, 'reject' | 'take_down'>): Promise<string | null> => {
  const label = action === 'reject' ? '驳回' : '下架'
  reasonInput.value = ''
  try {
    await showConfirmDialog({
      title: `${label}「${d.title}」`,
      confirmButtonText: `确认${label}`,
      confirmButtonColor: '#E5484D',
      message: () => h('div', { style: 'text-align:left' }, [
        h('div', { style: 'font-size:13px;color:#6B7280;margin-bottom:8px' },
          action === 'reject'
            ? '驳回后该文档不会进入检索/图谱，请填写原因告知提交人。'
            : '下架后该文档将从检索/图谱中移除，请填写原因。'),
        h(VanField as any, {
          modelValue: reasonInput.value,
          'onUpdate:modelValue': (v: string) => (reasonInput.value = v),
          type: 'textarea',
          rows: 3,
          autosize: true,
          placeholder: `请输入${label}原因`,
          maxlength: 200,
          showWordLimit: true,
          style: 'border:1px solid #E5E7EB;border-radius:8px;'
        })
      ])
    })
  } catch {
    return null
  }
  if (!reasonInput.value.trim()) {
    showFailToast('原因不能为空')
    return null
  }
  return reasonInput.value.trim()
}

const reasonInput = ref('')

const doReview = async (d: KbDoc, action: ReviewAction) => {
  let reason: string | undefined
  if (action === 'reject' || action === 'take_down') {
    const r = await promptReason(d, action)
    if (!r) return
    reason = r
  } else {
    try {
      await showConfirmDialog({ title: '通过审核', message: `确认通过「${d.title}」？通过后会进入 RAG 检索与图谱。` })
    } catch { return }
  }
  try {
    const res = await reviewDoc(d.id, action, reason)
    if (!res.ok) throw new Error('后端拒绝')
    showToast({
      type: 'success',
      message: action === 'approve' ? '已通过' : action === 'reject' ? '已驳回' : '已下架'
    })
    await refresh()
  } catch {
    showFailToast('操作失败，请确认后端接口可用')
  }
}

const exportingId = ref<number | null>(null)
const doExport = async (d: KbDoc) => {
  if (exportingId.value) return
  exportingId.value = d.id
  try {
    await exportDoc(d.id, 'pdf', d.title)
    showToast({ type: 'success', message: '已导出 PDF' })
  } catch {
    showFailToast('导出失败，请稍后重试')
  } finally {
    exportingId.value = null
  }
}

const STATUS_CLS: Record<string, string> = {
  pending:    'bg-warning/10 text-warning border-warning/30',
  approved:   'bg-success/10 text-success border-success/30',
  ready:      'bg-success/10 text-success border-success/30',
  rejected:   'bg-danger/10 text-danger border-danger/30',
  taken_down: 'bg-text-2/10 text-text-2 border-border'
}
</script>

<template>
  <div :class="isPC ? 'p-6 max-w-[1400px] mx-auto space-y-4' : 'p-3 space-y-3'">
    <header :class="isPC ? 'flex items-end justify-between gap-4' : 'industrial-card p-4 flex items-center gap-3'">
      <button v-if="!isPC" @click="router.back()" class="w-10 h-10 -ml-2 flex items-center justify-center">
        <ChevronLeft class="w-5 h-5" />
      </button>
      <div class="flex-1 min-w-0">
        <div v-if="isPC" class="text-xs text-text-2 flex items-center gap-1">
          <ShieldCheck class="w-3.5 h-3.5 text-accent" />
          {{ user.isAdmin ? '管理员' : '审核员' }} / 知识审查
        </div>
        <h1 :class="isPC ? 'text-2xl font-bold text-primary mt-1 flex items-center gap-2' : 'text-lg font-bold text-primary'">
          <ShieldCheck v-if="isPC" class="w-6 h-6 text-accent" /> 知识审查
        </h1>
        <div :class="isPC ? 'text-sm text-text-2 mt-1' : 'text-xs text-text-2 mt-0.5'">
          审核员 / 管理员可在此处审批员工提交的知识文档
        </div>
      </div>
      <button @click="refresh" :disabled="loading"
              class="h-10 px-4 rounded-btn border border-border bg-card flex items-center gap-2 hover:border-accent text-text-2 hover:text-accent">
        <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
        <span v-if="isPC">刷新</span>
      </button>
    </header>

    <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" />
      后端不可达，请确认服务已启动并已登录有权限的账号。
    </div>

    <!-- Tabs + 搜索 -->
    <div class="industrial-card overflow-hidden">
      <div class="flex border-b border-border">
        <button v-for="t in [
                  { k: 'pending',  l: '待审' },
                  { k: 'approved', l: '已通过' },
                  { k: 'rejected', l: '已驳回' }
                ]" :key="t.k" @click="switchTab(t.k as Tab)"
                :class="['h-11 px-4 text-sm border-b-2 -mb-px',
                         tab === t.k ? 'border-accent text-accent font-semibold' : 'border-transparent text-text-2']">
          {{ t.l }}
        </button>
        <div class="ml-auto flex items-center px-3">
          <div class="relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
            <input v-model="q" placeholder="搜索文档"
                   class="h-8 pl-9 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent text-sm w-48 sm:w-64" />
          </div>
        </div>
      </div>

      <div v-if="loading" class="py-12 text-center text-text-2">
        <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
        <div class="mt-2 text-sm">加载中…</div>
      </div>
      <div v-else-if="!filtered.length" class="py-16 text-center text-text-2">
        <FileText class="w-10 h-10 mx-auto opacity-40" />
        <div class="mt-3 text-sm">
          {{ tab === 'pending' ? '暂无待审文档' : tab === 'approved' ? '暂无已通过文档' : '暂无已驳回文档' }}
        </div>
      </div>
      <ul v-else class="divide-y divide-border">
        <li v-for="d in filtered" :key="d.id" class="px-5 py-3 flex items-start gap-3">
          <FileText class="w-4 h-4 text-text-2 flex-shrink-0 mt-1" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium truncate">{{ d.title }}</div>
            <div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-text-2">
              <span class="mono">#{{ d.id }}</span>
              <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ d.type }}</span>
              <span class="px-1.5 py-0.5 rounded-pill border" :class="STATUS_CLS[d.status] || 'bg-bg border-border'">
                {{ STATUS_LABEL[d.status] || d.status }}
              </span>
              <span v-if="d.uploader" class="mono">提交人 {{ d.uploader }}</span>
              <span class="mono opacity-70">{{ d.created_at }}</span>
            </div>
            <div v-if="d.reason" class="mt-1 text-xs"
                 :class="d.status === 'rejected' ? 'text-danger' : 'text-text-2'">
              {{ d.status === 'rejected' ? '驳回原因' : '备注' }}：{{ d.reason }}
            </div>
          </div>

          <!-- 导出（所有 Tab 通用） -->
          <button @click="doExport(d)" :disabled="exportingId === d.id"
                  class="h-8 px-3 rounded-btn border border-border text-text-2 text-xs flex items-center gap-1 hover:border-accent hover:text-accent disabled:opacity-60">
            <Loader v-if="exportingId === d.id" class="w-3.5 h-3.5 animate-spin" />
            <Download v-else class="w-3.5 h-3.5" /> 导出
          </button>
          <!-- 待审：通过 / 驳回 -->
          <template v-if="tab === 'pending'">
            <button @click="doReview(d, 'approve')"
                    class="h-8 px-3 rounded-btn bg-success text-white text-xs flex items-center gap-1 hover:opacity-90">
              <Check class="w-3.5 h-3.5" /> 通过
            </button>
            <button @click="doReview(d, 'reject')"
                    class="h-8 px-3 rounded-btn bg-danger text-white text-xs flex items-center gap-1 hover:opacity-90">
              <X class="w-3.5 h-3.5" /> 驳回
            </button>
          </template>
          <!-- 已通过：下架 -->
          <template v-else-if="tab === 'approved' && (user.isAuditor || user.isAdmin)">
            <button @click="doReview(d, 'take_down')"
                    class="h-8 px-3 rounded-btn border border-warning text-warning text-xs flex items-center gap-1 hover:bg-warning/10">
              <ArrowDown class="w-3.5 h-3.5" /> 下架
            </button>
          </template>
        </li>
      </ul>
    </div>
  </div>
</template>
