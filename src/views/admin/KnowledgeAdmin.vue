<script setup lang="ts">
/**
 * 管理员 · 知识库管理（FIX2 第 4 项 + FIX3 第 7.5 项）
 * - 仅 admin 可访问
 * - 增加 status 筛选器（全部 / 待审 / 已通过 / 已驳回 / 已下架）
 * - 上传按钮仅 admin 可见（保留）
 * - 删除按钮触发"下架"流程（保留物理删除作为最高权限的"硬删除"，二次确认）
 */
import { ref, computed, onMounted, reactive } from 'vue'
import { useDevice } from '@/composables/useDevice'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import {
  Database, Upload, Search, Trash2, FileText, RefreshCw,
  Loader, X, Eye, ShieldCheck, AlertTriangle, FileType2, ArrowDown
} from 'lucide-vue-next'
import {
  listDocs, uploadDoc, deleteDoc, reviewDoc,
  type KbDoc, STATUS_LABEL
} from '@/api/kb'

const { isPC } = useDevice()

const docs = ref<KbDoc[]>([])
const loading = ref(false)
const offline = ref(false)
const q = ref('')
const filterType = ref<'all' | 'pdf' | 'docx' | 'txt' | 'md'>('all')
const filterStatus = ref<'all' | 'pending' | 'approved' | 'rejected' | 'taken_down'>('all')

const ALLOWED = ['pdf', 'docx', 'txt', 'md']

interface UploadingItem { name: string; size: number; progress: 'uploading' | 'done' | 'failed'; docId?: number; chunks?: number; err?: string }
const uploads = reactive<UploadingItem[]>([])

const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()

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

const onFiles = async (files: FileList | File[] | null) => {
  if (!files) return
  const arr = Array.from(files)
  if (!arr.length) return
  for (const f of arr) {
    const ext = (f.name.split('.').pop() || '').toLowerCase()
    if (!ALLOWED.includes(ext)) {
      showFailToast(`仅支持 ${ALLOWED.join(' / ')}：${f.name}`)
      continue
    }
    const item: UploadingItem = { name: f.name, size: f.size, progress: 'uploading' }
    uploads.push(item)
    try {
      const res = await uploadDoc(f)
      item.docId = res.doc_id
      item.chunks = res.chunks
      item.progress = 'done'
      showToast({ type: 'success', message: `${f.name} 已入库（${res.chunks} chunks）` })
    } catch (e: any) {
      item.progress = 'failed'
      item.err = e?.message || '上传失败'
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

const takeDown = async (d: KbDoc) => {
  const reason = window.prompt(`下架「${d.title}」原因：`, '')
  if (reason === null) return
  if (!reason.trim()) { showFailToast('原因不能为空'); return }
  try {
    const res = await reviewDoc(d.id, 'take_down', reason.trim())
    if (!res.ok) throw new Error('failed')
    showToast({ type: 'success', message: '已下架' })
    await refresh()
  } catch {
    showFailToast('下架失败')
  }
}

const hardDelete = async (d: KbDoc) => {
  try {
    await showConfirmDialog({
      title: '⚠️ 物理删除',
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

const previewDoc = (_d: KbDoc) => {
  showToast('文档分块预览接口待后端提供，敬请期待')
}
</script>

<template>
  <!-- ==================== PC ==================== -->
  <div v-if="isPC" class="p-6 max-w-[1400px] mx-auto space-y-4">
    <header class="flex items-end justify-between gap-4">
      <div>
        <div class="text-xs text-text-2 flex items-center gap-1">
          <ShieldCheck class="w-3.5 h-3.5 text-accent" /> 管理员 / 知识库管理
        </div>
        <h1 class="text-2xl font-bold text-primary mt-1 flex items-center gap-2">
          <Database class="w-6 h-6 text-accent" /> 知识库管理
        </h1>
        <div class="text-sm text-text-2 mt-1">管理向量化知识库文档：上传 / 下架 / 状态查看</div>
      </div>
      <button @click="refresh" :disabled="loading"
              class="h-10 px-4 rounded-btn border border-border bg-card hover:border-accent text-text-2 hover:text-accent flex items-center gap-2">
        <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" /> 刷新
      </button>
    </header>

    <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" />
      后端不可达，无法加载知识库。请确认服务已启动并已登录管理员账号。
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

    <!-- 上传区（仅 admin 可见，路由已有 roles=admin 守卫） -->
    <section class="industrial-card p-5">
      <div class="text-sm font-semibold mb-2 flex items-center gap-2">
        <Upload class="w-4 h-4 text-accent" /> 上传新文档
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
          <!-- 状态筛选（FIX3 第 7.5 项） -->
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
      <div v-else-if="!filtered.length" class="py-16 text-center text-text-2">
        <Database class="w-10 h-10 mx-auto opacity-50" />
        <div class="mt-3 text-sm">{{ docs.length === 0 ? '当前筛选下无文档' : '没有符合条件的文档' }}</div>
      </div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-text-2 text-xs">
            <th class="text-left font-medium px-5 py-2 w-16">ID</th>
            <th class="text-left font-medium px-5 py-2">文档名</th>
            <th class="text-left font-medium px-5 py-2 w-20">类型</th>
            <th class="text-left font-medium px-5 py-2 w-24">状态</th>
            <th class="text-left font-medium px-5 py-2 w-32">提交人</th>
            <th class="text-left font-medium px-5 py-2 w-44">入库时间</th>
            <th class="text-right font-medium px-5 py-2 w-44">操作</th>
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
                <button class="w-8 h-8 rounded hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent"
                        title="预览分块" @click="previewDoc(d)">
                  <Eye class="w-4 h-4" />
                </button>
                <button v-if="d.status === 'approved' || d.status === 'ready'"
                        class="w-8 h-8 rounded hover:bg-warning/10 flex items-center justify-center text-text-2 hover:text-warning"
                        title="下架" @click="takeDown(d)">
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
    </header>

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

    <ul class="space-y-2">
      <li v-for="d in filtered" :key="d.id" class="industrial-card p-3 active:bg-bg">
        <div class="flex items-start gap-2">
          <FileText class="w-4 h-4 text-text-2 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium leading-snug truncate">{{ d.title }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-text-2">
              <span class="mono">#{{ d.id }}</span>
              <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ d.type }}</span>
              <span class="px-1.5 py-0.5 rounded-pill border whitespace-nowrap inline-block" :class="STATUS_CLS[d.status] || 'bg-bg border-border'">{{ STATUS_LABEL[d.status] || d.status }}</span>
            </div>
          </div>
          <button v-if="d.status === 'approved' || d.status === 'ready'"
                  class="w-8 h-8 rounded text-warning"
                  @click="takeDown(d)" title="下架">
            <ArrowDown class="w-4 h-4 mx-auto" />
          </button>
          <button class="w-8 h-8 rounded text-danger" @click="hardDelete(d)">
            <Trash2 class="w-4 h-4 mx-auto" />
          </button>
        </div>
      </li>
      <li v-if="!filtered.length && !loading" class="industrial-card p-8 text-center text-text-2 text-sm">
        当前筛选下无文档
      </li>
    </ul>
  </div>
</template>
