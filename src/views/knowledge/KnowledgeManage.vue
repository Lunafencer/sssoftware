<script setup lang="ts">
/**
 * 知识库管理（FIX5）
 * - 路由 /auditor/knowledge，roles: ['auditor', 'admin']（/admin/knowledge 重定向至此）
 * - 列出全部文档，status 筛选 + 类型筛选 + 统计卡片
 * - 自由新增任意文档：文件上传（uploadDoc）+ 录入文本知识（uploadText，带分类）→ 审核员/管理员直接已通过
 * - 单文档操作：通过 / 下架 / 驳回 / 物理删除 / 导出
 * - AI 辅助分析：把标题+正文交给 multimodalSearch 做完整性/关键步骤分析
 * - 二次确认机制：所有变更操作均弹确认框；不可逆操作（删除/驳回/下架）用警示样式
 * - 原因（驳回/下架）通过带输入框的对话框收集（禁止 window.prompt）
 * - 知识图谱编辑入口：跳转 /kg
 */
import { ref, computed, onMounted, reactive, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDevice } from '@/composables/useDevice'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import { Field as VanField } from 'vant'
import {
  Database, Upload, Search, Trash2, FileText, RefreshCw, Loader, X, Check,
  ShieldCheck, AlertTriangle, FileType2, ArrowDown, Edit3, Send, Sparkles, Download, Share2
} from 'lucide-vue-next'
import {
  listDocs, uploadDoc, uploadText, deleteDoc, reviewDoc, getDoc, exportDoc, updateDoc,
  type KbDoc, type ReviewAction, STATUS_LABEL
} from '@/api/kb'
import { multimodalSearch } from '@/api/search'
import { renderMarkdown } from '@/utils/markdown'
import EmptyState from '@/components/common/EmptyState.vue'

const router = useRouter()
const { isPC } = useDevice()

const docs = ref<KbDoc[]>([])
const loading = ref(false)
const offline = ref(false)
const q = ref('')
const filterType = ref<'all' | 'pdf' | 'docx' | 'txt' | 'md'>('all')
const filterStatus = ref<'all' | 'pending' | 'approved' | 'rejected' | 'taken_down'>('all')

const ALLOWED = ['pdf', 'docx', 'txt', 'md']

interface UploadingItem { name: string; size: number; progress: 'uploading' | 'done' | 'failed'; docId?: number; chunks?: number }
const uploads = reactive<UploadingItem[]>([])

const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()
const fileCategory = ref<'manual' | 'experience'>('manual')

// 录入文本知识
const showText = ref(false)
const textTitle = ref('')
const textBody = ref('')
const textCategory = ref<'manual' | 'experience'>('manual')
const textSubmitting = ref(false)

// AI 辅助分析
const showAI = ref(false)
const aiDoc = ref<KbDoc | null>(null)
const aiLoading = ref(false)
const aiResult = ref('')
const aiErr = ref('')

const refresh = async () => {
  loading.value = true
  try {
    docs.value = await listDocs(filterStatus.value === 'all' ? undefined : { status: filterStatus.value })
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
    (filterType.value === 'all' || d.type.toLowerCase() === filterType.value) &&
    (!q.value || d.title.toLowerCase().includes(q.value.toLowerCase()))
  )
)

const stats = computed(() => {
  const total = docs.value.length
  const pending = docs.value.filter(d => d.status === 'pending').length
  const approved = docs.value.filter(d => d.status === 'approved' || d.status === 'ready').length
  const rejected = docs.value.filter(d => d.status === 'rejected').length
  return { total, pending, approved, rejected }
})

/* ---------- 文件上传（二次确认） ---------- */
const onFiles = async (files: FileList | File[] | null) => {
  if (!files) return
  const arr = Array.from(files)
  if (!arr.length) return
  const valid = arr.filter(f => {
    const ext = (f.name.split('.').pop() || '').toLowerCase()
    if (!ALLOWED.includes(ext)) { showFailToast(`仅支持 ${ALLOWED.join(' / ')}：${f.name}`); return false }
    return true
  })
  if (!valid.length) return
  try {
    await showConfirmDialog({
      title: '确认上传',
      message: `将以「${fileCategory.value === 'manual' ? '手册' : '案例'}」分类上传 ${valid.length} 个文件并直接入库（已通过）。是否继续？`
    })
  } catch { return }
  for (const f of valid) {
    const item: UploadingItem = { name: f.name, size: f.size, progress: 'uploading' }
    uploads.push(item)
    try {
      const res = await uploadDoc(f, undefined, fileCategory.value)
      item.docId = res.doc_id
      item.chunks = res.chunks
      item.progress = 'done'
      showToast({ type: 'success', message: `${f.name} 已入库（${res.chunks} chunks）` })
    } catch {
      item.progress = 'failed'
      showFailToast(`${f.name} 上传失败`)
    }
  }
  await refresh()
}

const onDrop = (e: DragEvent) => {
  e.preventDefault(); dragging.value = false
  onFiles(e.dataTransfer?.files || null)
}
const onPick = (e: Event) => {
  const t = e.target as HTMLInputElement
  onFiles(t.files)
  t.value = ''
}

/* ---------- 录入文本知识（二次确认） ---------- */
const submitText = async () => {
  const title = textTitle.value.trim()
  const content = textBody.value.trim()
  if (!title) { showFailToast('请输入标题'); return }
  if (!content) { showFailToast('请输入正文内容'); return }
  try {
    await showConfirmDialog({
      title: '确认录入',
      message: `将以「${textCategory.value === 'manual' ? '手册' : '经验'}」分类录入「${title}」并直接入库（已通过）。是否继续？`
    })
  } catch { return }
  textSubmitting.value = true
  try {
    const res = await uploadText({ title, content, category: textCategory.value })
    showToast({ type: 'success', message: `已录入（${res.chunks} chunks）` })
    showText.value = false
    textTitle.value = ''
    textBody.value = ''
    await refresh()
  } catch {
    showFailToast('录入失败，请稍后重试')
  } finally {
    textSubmitting.value = false
  }
}

/* ---------- 通过（二次确认） ---------- */
const approve = async (d: KbDoc) => {
  try {
    await showConfirmDialog({
      title: '通过审核',
      message: `确认通过「${d.title}」？通过后会进入 RAG 检索与图谱。`
    })
  } catch { return }
  await runReview(d, 'approve')
}

/* ---------- 驳回 / 下架（带输入框 + 警示二次确认） ---------- */
const reasonInput = ref('')
const reviewWithReason = async (d: KbDoc, action: Extract<ReviewAction, 'reject' | 'take_down'>) => {
  reasonInput.value = ''
  const label = action === 'reject' ? '驳回' : '下架'
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
  } catch { return }
  if (!reasonInput.value.trim()) { showFailToast('原因不能为空'); return }
  await runReview(d, action, reasonInput.value.trim())
}

const runReview = async (d: KbDoc, action: ReviewAction, reason?: string) => {
  try {
    const res = await reviewDoc(d.id, action, reason)
    if (!res.ok) throw new Error('failed')
    showToast({ type: 'success', message: action === 'approve' ? '已通过' : action === 'reject' ? '已驳回' : '已下架' })
    await refresh()
  } catch {
    showFailToast('操作失败，请确认后端接口可用')
  }
}

/* ---------- 物理删除（警示二次确认） ---------- */
const hardDelete = async (d: KbDoc) => {
  try {
    await showConfirmDialog({
      title: '物理删除',
      confirmButtonText: '彻底删除',
      confirmButtonColor: '#E5484D',
      message: `这将彻底删除「${d.title}」并清理向量索引，无法恢复。仅在确认无任何引用时使用，建议优先使用「下架」。`
    })
  } catch { return }
  try {
    await deleteDoc(d.id)
    showToast({ type: 'success', message: '已删除' })
    await refresh()
  } catch {
    showFailToast('删除失败')
  }
}

/* ---------- 导出 ---------- */
const exportingId = ref<number | null>(null)
const doExport = async (d: KbDoc, format: 'pdf' | 'md') => {
  if (exportingId.value) return
  exportingId.value = d.id
  try {
    await exportDoc(d.id, format, d.title)
    showToast({ type: 'success', message: `已导出 ${format.toUpperCase()}` })
  } catch {
    showFailToast('导出失败，请稍后重试')
  } finally {
    exportingId.value = null
  }
}

/* ---------- FIX6 第 6 项：编辑文档（包括 AI 自动入库的） ---------- */
const showEdit = ref(false)
const editDoc = ref<KbDoc | null>(null)
const editTitle = ref('')
const editContent = ref('')
const editCategory = ref('')
const editSubmitting = ref(false)

const openEdit = async (d: KbDoc) => {
  editDoc.value = d
  editTitle.value = d.title
  editCategory.value = d.category || 'manual'
  editContent.value = ''
  showEdit.value = true
  try {
    const det = await getDoc(d.id)
    editContent.value = det.content || ''
  } catch {
    showFailToast('加载文档内容失败')
  }
}

const submitEdit = async () => {
  if (!editDoc.value) return
  if (!editTitle.value.trim()) { showFailToast('标题不能为空'); return }
  editSubmitting.value = true
  try {
    await updateDoc(editDoc.value.id, {
      title: editTitle.value.trim(),
      content: editContent.value,
      category: editCategory.value
    })
    showToast({ type: 'success', message: '已保存' })
    showEdit.value = false
    await refresh()
  } catch {
    showFailToast('保存失败')
  } finally {
    editSubmitting.value = false
  }
}

/* ---------- AI 辅助分析 ---------- */
const analyzeDoc = async (d: KbDoc) => {
  aiDoc.value = d
  aiResult.value = ''
  aiErr.value = ''
  showAI.value = true
  aiLoading.value = true
  try {
    const det = await getDoc(d.id)
    const text = `请分析以下检修知识文档的完整性与关键步骤：\n标题：${det.title}\n正文：\n${det.content || ''}`
    const res = await multimodalSearch({ text })
    aiResult.value = res.summary || '（AI 未返回分析内容）'
  } catch {
    aiErr.value = 'AI 分析失败，请确认后端服务可用后重试'
  } finally {
    aiLoading.value = false
  }
}

const goKG = () => router.push('/kg')

const fmtSize = (n: number) => n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`

const STATUS_CLS: Record<string, string> = {
  pending:    'bg-warning/10 text-warning border-warning/30',
  approved:   'bg-success/10 text-success border-success/30',
  ready:      'bg-success/10 text-success border-success/30',
  rejected:   'bg-danger/10 text-danger border-danger/30',
  taken_down: 'bg-text-2/10 text-text-2 border-border',
  parsing:    'bg-warning/10 text-warning border-warning/30',
  failed:     'bg-danger/10 text-danger border-danger/30'
}

const isApproved = (s: string) => s === 'approved' || s === 'ready'
</script>

<template>
  <!-- ==================== PC ==================== -->
  <div v-if="isPC" class="p-6 max-w-[1400px] mx-auto space-y-4">
    <header class="flex items-end justify-between gap-4">
      <div>
        <div class="text-xs text-text-2 flex items-center gap-1">
          <ShieldCheck class="w-3.5 h-3.5 text-accent" /> 审核员 / 知识库管理
        </div>
        <h1 class="text-2xl font-bold text-primary mt-1 flex items-center gap-2">
          <Database class="w-6 h-6 text-accent" /> 知识库管理
        </h1>
        <div class="text-sm text-text-2 mt-1">管理向量化知识库文档：新增 / 审批 / 下架 / 删除 / 导出 / AI 分析</div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="goKG"
                class="h-10 px-4 rounded-btn border border-accent text-accent hover:bg-accent/10 flex items-center gap-2">
          <Share2 class="w-4 h-4" /> 编辑知识图谱
        </button>
        <button @click="showText = true"
                class="h-10 px-4 rounded-btn border border-border bg-card hover:border-accent hover:text-accent flex items-center gap-2">
          <Edit3 class="w-4 h-4" /> 录入文本知识
        </button>
        <button @click="refresh" :disabled="loading"
                class="h-10 px-4 rounded-btn border border-border bg-card hover:border-accent text-text-2 hover:text-accent flex items-center gap-2">
          <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" /> 刷新
        </button>
      </div>
    </header>

    <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" />
      后端不可达，无法加载知识库。请确认服务已启动并已登录有权限的账号。
    </div>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-4 gap-3">
      <div class="industrial-card p-4">
        <div class="text-xs text-text-2">文档总数</div>
        <div class="text-2xl font-bold mt-1 mono">{{ stats.total }}</div>
      </div>
      <div class="industrial-card p-4">
        <div class="text-xs text-text-2 flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-warning" /> 待审</div>
        <div class="text-2xl font-bold mt-1 mono text-warning">{{ stats.pending }}</div>
      </div>
      <div class="industrial-card p-4">
        <div class="text-xs text-text-2 flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-success" /> 已通过</div>
        <div class="text-2xl font-bold mt-1 mono text-success">{{ stats.approved }}</div>
      </div>
      <div class="industrial-card p-4">
        <div class="text-xs text-text-2 flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-danger" /> 已驳回</div>
        <div class="text-2xl font-bold mt-1 mono text-danger">{{ stats.rejected }}</div>
      </div>
    </div>

    <!-- 上传区 -->
    <section class="industrial-card p-5">
      <div class="text-sm font-semibold mb-2 flex items-center gap-2">
        <Upload class="w-4 h-4 text-accent" /> 上传新文档
      </div>
      <div class="flex items-center gap-2 mb-3">
        <span class="text-sm text-text-2">分类</span>
        <div class="flex p-0.5 bg-bg rounded-btn border border-border text-sm w-max">
          <button v-for="c in [{k:'manual',l:'手册 / 规程'},{k:'experience',l:'案例 / 经验'}]" :key="c.k"
                  @click="fileCategory = c.k as any"
                  :class="['px-4 h-8 rounded font-medium', fileCategory === c.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
            {{ c.l }}
          </button>
        </div>
      </div>
      <div @click="fileInput?.click()"
           @dragover.prevent="dragging = true"
           @dragleave.prevent="dragging = false"
           @drop="onDrop"
           class="border-2 border-dashed rounded-card py-12 flex flex-col items-center justify-center cursor-pointer transition"
           :class="dragging ? 'border-accent bg-accent/5' : 'border-border hover:border-accent'">
        <FileType2 class="w-10 h-10 text-text-2" :class="dragging ? 'text-accent' : ''" />
        <div class="mt-3 text-sm font-medium" :class="dragging ? 'text-accent' : 'text-text'">
          {{ dragging ? '松手即可上传' : '拖拽文件到此处，或点击选择' }}
        </div>
        <div class="mt-1 text-xs text-text-2 mono">{{ ALLOWED.map(e => '.' + e).join(' · ') }} · 单文件 ≤ 50MB</div>
      </div>
      <input ref="fileInput" type="file" multiple class="hidden"
             :accept="ALLOWED.map(e => '.' + e).join(',')" @change="onPick" />

      <ul v-if="uploads.length" class="mt-3 space-y-1.5">
        <li v-for="(u, i) in uploads" :key="i"
            class="flex items-center gap-2 px-3 py-2 rounded-btn border border-border bg-bg text-sm">
          <Loader v-if="u.progress === 'uploading'" class="w-4 h-4 animate-spin text-accent" />
          <FileText v-else class="w-4 h-4" :class="u.progress === 'done' ? 'text-success' : 'text-danger'" />
          <span class="flex-1 truncate">{{ u.name }}</span>
          <span class="text-xs text-text-2 mono">{{ fmtSize(u.size) }}</span>
          <span v-if="u.progress === 'uploading'" class="text-xs text-text-2">上传中…</span>
          <span v-else-if="u.progress === 'done'" class="text-xs text-success mono">#{{ u.docId }} · {{ u.chunks }} chunks</span>
          <span v-else class="text-xs text-danger">失败</span>
        </li>
      </ul>
    </section>

    <!-- 列表区 -->
    <section class="industrial-card overflow-hidden">
      <header class="px-5 py-3 border-b border-border flex items-center gap-3 flex-wrap">
        <div class="text-sm font-semibold flex items-center gap-2">
          <Database class="w-4 h-4 text-accent" /> 已入库文档
          <span class="text-xs text-text-2 font-normal mono">{{ filtered.length }} / {{ docs.length }}</span>
        </div>
        <div class="ml-auto flex items-center gap-2 flex-wrap">
          <div class="flex p-0.5 bg-bg rounded-btn border border-border text-xs">
            <button v-for="s in [{k:'all',l:'全部'},{k:'pending',l:'待审'},{k:'approved',l:'已通过'},{k:'rejected',l:'已驳回'},{k:'taken_down',l:'已下架'}]"
                    :key="s.k" @click="filterStatus = s.k as any; refresh()"
                    :class="['px-3 h-7 rounded font-medium', filterStatus === s.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
              {{ s.l }}
            </button>
          </div>
          <div class="flex p-0.5 bg-bg rounded-btn border border-border text-xs">
            <button v-for="t in [{k:'all',l:'全部'},{k:'pdf',l:'PDF'},{k:'docx',l:'DOCX'},{k:'txt',l:'TXT'},{k:'md',l:'MD'}]"
                    :key="t.k" @click="filterType = t.k as any"
                    :class="['px-3 h-7 rounded font-medium', filterType === t.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
              {{ t.l }}
            </button>
          </div>
          <div class="relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
            <input v-model="q" placeholder="按文档名搜索"
                   class="h-8 pl-9 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent text-sm w-56" />
          </div>
        </div>
      </header>

      <div v-if="loading" class="py-16 text-center text-text-2">
        <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
        <div class="mt-2 text-sm">加载中…</div>
      </div>
      <EmptyState v-else-if="!filtered.length"
                  :title="offline ? '加载失败' : (docs.length === 0 ? '当前筛选下无文档' : '没有符合条件的文档')"
                  :desc="offline ? '后端不可达，无法加载知识库' : '可调整筛选或搜索关键词'" />
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-text-2 text-xs">
            <th class="text-left font-medium px-5 py-2 w-16">ID</th>
            <th class="text-left font-medium px-5 py-2">文档名</th>
            <th class="text-left font-medium px-5 py-2 w-20">类型</th>
            <th class="text-left font-medium px-5 py-2 w-24">状态</th>
            <th class="text-left font-medium px-5 py-2 w-32">提交人</th>
            <th class="text-left font-medium px-5 py-2 w-40">入库时间</th>
            <th class="text-right font-medium px-5 py-2 w-64">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in filtered" :key="d.id" class="border-t border-border hover:bg-bg/60">
            <td class="px-5 py-3 mono text-text-2">#{{ d.id }}</td>
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <FileText class="w-4 h-4 text-text-2 flex-shrink-0" />
                <span class="font-medium truncate">{{ d.title }}</span>
              </div>
              <div v-if="d.reason" class="text-[11px] text-text-2 mt-0.5 truncate">原因：{{ d.reason }}</div>
            </td>
            <td class="px-5 py-3">
              <span class="px-2 py-0.5 rounded text-[11px] mono uppercase bg-bg border border-border">{{ d.type }}</span>
            </td>
            <td class="px-5 py-3">
              <span class="px-2 py-0.5 rounded-pill text-[11px] border whitespace-nowrap inline-block" :class="STATUS_CLS[d.status] || 'bg-bg border-border text-text-2'">
                {{ STATUS_LABEL[d.status] || d.status }}
              </span>
            </td>
            <td class="px-5 py-3 text-text-2 text-xs">{{ d.uploader || '—' }}</td>
            <td class="px-5 py-3 text-text-2 mono text-xs">{{ d.created_at }}</td>
            <td class="px-5 py-3">
              <div class="flex justify-end gap-1">
                <button class="w-8 h-8 rounded hover:bg-ai/10 flex items-center justify-center text-text-2 hover:text-ai"
                        title="AI 辅助分析" @click="analyzeDoc(d)">
                  <Sparkles class="w-4 h-4" />
                </button>
                <button class="w-8 h-8 rounded hover:bg-accent/10 flex items-center justify-center text-text-2 hover:text-accent"
                        title="编辑文档" @click="openEdit(d)">
                  <Edit3 class="w-4 h-4" />
                </button>
                <button class="w-8 h-8 rounded hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent disabled:opacity-50"
                        title="导出 PDF" :disabled="exportingId === d.id" @click="doExport(d, 'pdf')">
                  <Loader v-if="exportingId === d.id" class="w-4 h-4 animate-spin" />
                  <Download v-else class="w-4 h-4" />
                </button>
                <button v-if="d.status === 'pending'"
                        class="w-8 h-8 rounded hover:bg-success/10 flex items-center justify-center text-text-2 hover:text-success"
                        title="通过" @click="approve(d)">
                  <Check class="w-4 h-4" />
                </button>
                <button v-if="d.status === 'pending'"
                        class="w-8 h-8 rounded hover:bg-danger/10 flex items-center justify-center text-text-2 hover:text-danger"
                        title="驳回" @click="reviewWithReason(d, 'reject')">
                  <X class="w-4 h-4" />
                </button>
                <button v-if="isApproved(d.status)"
                        class="w-8 h-8 rounded hover:bg-warning/10 flex items-center justify-center text-text-2 hover:text-warning"
                        title="下架" @click="reviewWithReason(d, 'take_down')">
                  <ArrowDown class="w-4 h-4" />
                </button>
                <button class="w-8 h-8 rounded hover:bg-danger/10 flex items-center justify-center text-text-2 hover:text-danger"
                        title="物理删除" @click="hardDelete(d)">
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>

  <!-- ==================== 移动端 ==================== -->
  <div v-else class="p-3 space-y-3">
    <header class="industrial-card p-4">
      <h1 class="text-lg font-bold text-primary flex items-center gap-2">
        <Database class="w-5 h-5 text-accent" /> 知识库管理
      </h1>
      <div class="text-xs text-text-2 mt-1">{{ stats.total }} 份 · 待审 {{ stats.pending }} · 通过 {{ stats.approved }} · 驳回 {{ stats.rejected }}</div>
      <div class="mt-3 grid grid-cols-2 gap-2">
        <button @click="showText = true"
                class="h-9 rounded-btn border border-border bg-card flex items-center justify-center gap-1.5 text-sm">
          <Edit3 class="w-4 h-4" /> 录入文本
        </button>
        <button @click="goKG"
                class="h-9 rounded-btn border border-accent text-accent flex items-center justify-center gap-1.5 text-sm">
          <Share2 class="w-4 h-4" /> 编辑图谱
        </button>
      </div>
    </header>

    <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" /> 后端不可达，无法加载知识库。
    </div>

    <div class="flex gap-1 overflow-x-auto hide-scrollbar -mx-1 px-1">
      <button v-for="s in [{k:'all',l:'全部'},{k:'pending',l:'待审'},{k:'approved',l:'已通过'},{k:'rejected',l:'已驳回'},{k:'taken_down',l:'已下架'}]"
              :key="s.k" @click="filterStatus = s.k as any; refresh()"
              :class="['px-3 h-8 rounded-pill text-xs flex-shrink-0',
                       filterStatus === s.k ? 'bg-accent text-white' : 'bg-card border border-border text-text-2']">
        {{ s.l }}
      </button>
    </div>

    <button @click="fileInput?.click()"
            class="w-full industrial-card border-2 border-dashed border-border py-6 flex flex-col items-center text-text-2 active:bg-bg">
      <FileType2 class="w-7 h-7" />
      <div class="mt-1.5 text-sm">点击选择文档上传</div>
    </button>
    <input ref="fileInput" type="file" multiple class="hidden"
           :accept="ALLOWED.map(e => '.' + e).join(',')" @change="onPick" />

    <EmptyState v-if="!filtered.length && !loading"
                :title="offline ? '加载失败' : '当前筛选下无文档'"
                :desc="offline ? '后端不可达，无法加载知识库' : '可调整筛选或搜索关键词'" />
    <ul v-else class="space-y-2">
      <li v-for="d in filtered" :key="d.id" class="industrial-card p-3">
        <div class="flex items-start gap-2">
          <FileText class="w-4 h-4 text-text-2 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium leading-snug truncate">{{ d.title }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-text-2">
              <span class="mono">#{{ d.id }}</span>
              <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ d.type }}</span>
              <span class="px-1.5 py-0.5 rounded-pill border whitespace-nowrap inline-block" :class="STATUS_CLS[d.status] || 'bg-bg border-border'">{{ STATUS_LABEL[d.status] || d.status }}</span>
            </div>
            <div v-if="d.reason" class="text-[11px] text-text-2 mt-0.5 truncate">原因：{{ d.reason }}</div>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <button class="h-7 px-2.5 rounded-btn border border-border text-ai text-xs flex items-center gap-1" @click="analyzeDoc(d)">
            <Sparkles class="w-3.5 h-3.5" /> AI 分析
          </button>
          <button class="h-7 px-2.5 rounded-btn border border-border text-accent text-xs flex items-center gap-1" @click="openEdit(d)">
            <Edit3 class="w-3.5 h-3.5" /> 编辑
          </button>
          <button class="h-7 px-2.5 rounded-btn border border-border text-text-2 text-xs flex items-center gap-1 disabled:opacity-50"
                  :disabled="exportingId === d.id" @click="doExport(d, 'pdf')">
            <Loader v-if="exportingId === d.id" class="w-3.5 h-3.5 animate-spin" />
            <Download v-else class="w-3.5 h-3.5" /> 导出
          </button>
          <button v-if="d.status === 'pending'" class="h-7 px-2.5 rounded-btn bg-success text-white text-xs flex items-center gap-1" @click="approve(d)">
            <Check class="w-3.5 h-3.5" /> 通过
          </button>
          <button v-if="d.status === 'pending'" class="h-7 px-2.5 rounded-btn bg-danger text-white text-xs flex items-center gap-1" @click="reviewWithReason(d, 'reject')">
            <X class="w-3.5 h-3.5" /> 驳回
          </button>
          <button v-if="isApproved(d.status)" class="h-7 px-2.5 rounded-btn border border-warning text-warning text-xs flex items-center gap-1" @click="reviewWithReason(d, 'take_down')">
            <ArrowDown class="w-3.5 h-3.5" /> 下架
          </button>
          <button class="h-7 px-2.5 rounded-btn border border-danger text-danger text-xs flex items-center gap-1" @click="hardDelete(d)">
            <Trash2 class="w-3.5 h-3.5" /> 删除
          </button>
        </div>
      </li>
    </ul>
  </div>

  <!-- ==================== 录入文本知识对话框 ==================== -->
  <div v-if="showText" class="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
       @click.self="!textSubmitting && (showText = false)">
    <div class="industrial-card w-full max-w-2xl bg-card overflow-hidden flex flex-col" style="max-height: 88vh;">
      <header class="px-5 py-3 border-b border-border flex items-center gap-2">
        <Edit3 class="w-4 h-4 text-accent" />
        <span class="font-semibold flex-1">录入文本知识</span>
        <button class="text-text-2 hover:text-danger" :disabled="textSubmitting" @click="showText = false">
          <X class="w-4 h-4" />
        </button>
      </header>
      <div class="p-5 space-y-3 overflow-auto">
        <div>
          <div class="text-sm text-text-2 mb-1">标题 <span class="text-danger">*</span></div>
          <input v-model="textTitle" placeholder="如：减速机轴承更换作业要点"
                 :disabled="textSubmitting"
                 class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card" />
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">分类</div>
          <div class="flex p-0.5 bg-bg rounded-btn border border-border text-sm w-max">
            <button v-for="c in [{k:'manual',l:'手册 / 规程'},{k:'experience',l:'经验分享'}]" :key="c.k"
                    @click="textCategory = c.k as any" :disabled="textSubmitting"
                    :class="['px-4 h-8 rounded font-medium', textCategory === c.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
              {{ c.l }}
            </button>
          </div>
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">正文内容（支持 Markdown） <span class="text-danger">*</span></div>
          <textarea v-model="textBody" rows="12"
                    placeholder="支持 Markdown 标题/列表/表格……AI 会按段落自动切分入库。"
                    :disabled="textSubmitting"
                    class="w-full px-3 py-2 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card text-sm leading-relaxed"></textarea>
          <div class="text-[11px] text-text-2 mt-1">审核员/管理员录入将直接进入检索 / 图谱（已通过）</div>
        </div>
      </div>
      <footer class="px-5 py-3 border-t border-border flex justify-end gap-2">
        <button class="h-9 px-4 rounded-btn border border-border" :disabled="textSubmitting" @click="showText = false">取消</button>
        <button class="h-9 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                :disabled="textSubmitting" @click="submitText">
          <Loader v-if="textSubmitting" class="w-4 h-4 animate-spin" />
          <Send v-else class="w-4 h-4" />
          {{ textSubmitting ? '提交中…' : '录入' }}
        </button>
      </footer>
    </div>
  </div>

  <!-- ==================== AI 辅助分析对话框 ==================== -->
  <div v-if="showAI" class="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
       @click.self="!aiLoading && (showAI = false)">
    <div class="industrial-card w-full max-w-2xl bg-card overflow-hidden flex flex-col" style="max-height: 88vh;">
      <header class="px-5 py-3 border-b border-border flex items-center gap-2 bg-primary text-on-dark">
        <Sparkles class="w-4 h-4 text-ai" />
        <span class="font-semibold flex-1 truncate">AI 辅助分析 · {{ aiDoc?.title }}</span>
        <button class="opacity-70 hover:opacity-100" :disabled="aiLoading" @click="showAI = false">
          <X class="w-4 h-4" />
        </button>
      </header>
      <div class="p-5 overflow-auto">
        <div v-if="aiLoading" class="py-12 text-center text-text-2">
          <Loader class="w-6 h-6 mx-auto animate-spin text-ai" />
          <div class="mt-2 text-sm">AI 正在分析文档完整性与关键步骤…</div>
        </div>
        <div v-else-if="aiErr" class="py-12 text-center text-text-2">
          <AlertTriangle class="w-8 h-8 mx-auto text-warning opacity-70" />
          <div class="mt-3 text-sm">{{ aiErr }}</div>
        </div>
        <div v-else class="md-body" v-html="renderMarkdown(aiResult)"></div>
      </div>
    </div>
  </div>

  <!-- ==================== FIX6 第 6 项：编辑文档对话框 ==================== -->
  <div v-if="showEdit" class="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
       @click.self="!editSubmitting && (showEdit = false)">
    <div class="industrial-card w-full max-w-2xl bg-card overflow-hidden flex flex-col" style="max-height: 88vh;">
      <header class="px-5 py-3 border-b border-border flex items-center gap-2">
        <Edit3 class="w-4 h-4 text-accent" />
        <span class="font-semibold flex-1 truncate">编辑文档 · {{ editDoc?.title }}</span>
        <button class="text-text-2 hover:text-danger" :disabled="editSubmitting" @click="showEdit = false">
          <X class="w-4 h-4" />
        </button>
      </header>
      <div class="p-5 space-y-3 overflow-auto">
        <div>
          <div class="text-sm text-text-2 mb-1">标题</div>
          <input v-model="editTitle" :disabled="editSubmitting"
                 class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent" />
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">分类</div>
          <input v-model="editCategory" :disabled="editSubmitting"
                 class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent" />
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">正文（Markdown）</div>
          <textarea v-model="editContent" rows="14" :disabled="editSubmitting"
                    class="w-full px-3 py-2 rounded-btn border border-border bg-bg outline-none focus:border-accent text-sm leading-relaxed"></textarea>
          <div class="text-[11px] text-text-2 mt-1">保存后将自动重建向量索引（仅对已通过文档生效）</div>
        </div>
      </div>
      <footer class="px-5 py-3 border-t border-border flex justify-end gap-2">
        <button class="h-9 px-4 rounded-btn border border-border" :disabled="editSubmitting" @click="showEdit = false">取消</button>
        <button class="h-9 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                :disabled="editSubmitting" @click="submitEdit">
          <Loader v-if="editSubmitting" class="w-4 h-4 animate-spin" />
          <Check v-else class="w-4 h-4" />
          {{ editSubmitting ? '保存中…' : '保存' }}
        </button>
      </footer>
    </div>
  </div>
</template>
