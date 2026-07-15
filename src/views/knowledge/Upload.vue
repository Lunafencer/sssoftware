<script setup lang="ts">
/**
 * 员工经验分享（FIX5 / FIX6 第 5 项 / FIX6-resume O3）
 * - 路由 /knowledge/upload，roles: ['frontline']（worker-only）
 * - 经验 + 附件原子提交：一次 multipart 调 /api/kb/text-with-files，整体成功或失败
 * - 我的上传记录：listDocs({uploader:'me'})，状态徽标 + 驳回后「重提」（预填表单）
 * - worker 不可删除自己的上传
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useDevice } from '@/composables/useDevice'
import {
  ChevronLeft, FileText, Loader, Upload, Search,
  Sparkles, Send, X, Check, AlertTriangle, Database, ShieldCheck, RefreshCw, Lightbulb, Paperclip
} from 'lucide-vue-next'
import { showToast, showFailToast } from 'vant'
import { uploadTextWithFiles, listDocs, type KbDoc, STATUS_LABEL, isApprovedStatus } from '@/api/kb'
import { useUserStore } from '@/stores/user'
import { useSearchStore } from '@/stores/search'  // FIX6 第 9 项：草稿持久化

const router = useRouter()
const { isPC } = useDevice()
const user = useUserStore()
const searchStore = useSearchStore()

const ALLOWED = ['pdf', 'docx', 'txt', 'md']

// 经验分享表单
const title = ref('')
const body = ref('')
const category = ref<'experience' | 'manual'>('experience')
const submitting = ref(false)
// FIX6-resume O3：原子提交——附件暂存在前端，点"提交分享"时随经验一起发送
const pendingFiles = ref<File[]>([])

interface UploadItem { name: string; size: number; status: 'uploading' | 'done' | 'failed'; docId?: number }
const uploads = ref<UploadItem[]>([])
const docs = ref<KbDoc[]>([])
const loading = ref(false)
const offline = ref(false)
const q = ref('')

const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()

const refresh = async () => {
  loading.value = true
  try {
    docs.value = await listDocs({ uploader: 'me' })
    offline.value = false
  } catch {
    docs.value = []
    offline.value = true
  } finally {
    loading.value = false
  }
}

// FIX6 第 9 项：挂载时恢复草稿；卸载时持久化
onMounted(() => {
  const d = searchStore.uploadDraft
  if (d.title || d.content) {
    title.value = d.title
    body.value = d.content
  }
  refresh()
})
onBeforeUnmount(() => {
  // 始终保存当前状态——删除内容后也应保存空值，否则旧草稿不会被清掉
  searchStore.setUploadDraft(title.value, body.value, [])
})

const filtered = computed(() =>
  docs.value.filter(d => !q.value || d.title.toLowerCase().includes(q.value.toLowerCase()))
)

const stats = computed(() => ({
  total: docs.value.length,
  pending: docs.value.filter(d => d.status === 'pending').length,
  approved: docs.value.filter(d => isApprovedStatus(d.status)).length,
  rejected: docs.value.filter(d => d.status === 'rejected').length
}))

const fmtSize = (n: number) => n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`

/* ---------- 经验 + 附件原子提交（FIX6-resume O3） ---------- */
const submitExperience = async () => {
  const t = title.value.trim()
  const content = body.value.trim()
  if (!t) { showFailToast('请输入标题'); return }
  if (!content) { showFailToast('请输入经验内容'); return }
  submitting.value = true
  // 把 pendingFiles 同步登记到 uploads 显示列表
  const startIdx = uploads.value.length
  for (const f of pendingFiles.value) {
    uploads.value.push({ name: f.name, size: f.size, status: 'uploading' })
  }
  try {
    const res = await uploadTextWithFiles(
      { title: t, content, category: category.value },
      pendingFiles.value
    )
    // 把后端返回的附件 id 回填到对应 UploadItem
    res.attachments.forEach((a, i) => {
      const item = uploads.value[startIdx + i]
      if (item) { item.status = 'done'; item.docId = a.id }
    })
    // FIX7 第 3 项：根据角色显示不同的成功提示（审查员/管理员直接入库，员工进入待审）
    const isDirect = user.isAuditor
    const attTxt = pendingFiles.value.length
      ? `（含 ${pendingFiles.value.length} 个附件）`
      : ''
    const msg = isDirect
      ? `知识已直接入库${attTxt}`
      : `经验已提交${attTxt}，等待审查员审核`
    showToast({ type: 'success', message: msg })
    title.value = ''
    body.value = ''
    category.value = 'experience'
    pendingFiles.value = []
    searchStore.clearUploadDraft()
    await refresh()
  } catch {
    // 失败：把刚刚标记 uploading 的 item 全部置为 failed
    for (let i = startIdx; i < uploads.value.length; i++) {
      if (uploads.value[i].status === 'uploading') uploads.value[i].status = 'failed'
    }
    showFailToast('提交失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

/* ---------- 暂存附件（不立即上传，等"提交分享"时一起发） ---------- */
const handleFiles = (files: FileList | File[] | null) => {
  if (!files) return
  const arr = Array.from(files)
  if (!arr.length) return
  for (const f of arr) {
    const ext = (f.name.split('.').pop() || '').toLowerCase()
    if (!ALLOWED.includes(ext)) {
      showFailToast(`仅支持 ${ALLOWED.join(' / ')}：${f.name}`)
      continue
    }
    pendingFiles.value.push(f)
  }
}

const removePending = (idx: number) => {
  pendingFiles.value.splice(idx, 1)
}

const onPick = (e: Event) => {
  const t = e.target as HTMLInputElement
  handleFiles(t.files)
  t.value = ''
}
const onDrop = (e: DragEvent) => {
  e.preventDefault(); dragging.value = false
  handleFiles(e.dataTransfer?.files || null)
}

const STATUS_CLS: Record<string, string> = {
  pending:    'bg-warning/10 text-warning border-warning/30',
  approved:   'bg-success/10 text-success border-success/30',
  ready:      'bg-success/10 text-success border-success/30',
  rejected:   'bg-danger/10 text-danger border-danger/30',
  taken_down: 'bg-text-2/10 text-text-2 border-border',
  parsing:    'bg-warning/10 text-warning border-warning/30',
  failed:     'bg-danger/10 text-danger border-danger/30'
}

/** 驳回后重提：预填表单 */
const resubmit = (d: KbDoc) => {
  title.value = d.title.replace(/（重提）$/, '')
  body.value = ''
  showToast('已为你打开重提表单，请补充内容后再次提交')
  if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' })
}

const goReview = () => router.push('/auditor/review')
</script>

<template>
  <div :class="isPC ? 'p-6 max-w-5xl mx-auto space-y-4' : 'h-full flex flex-col'">
    <!-- 移动端顶栏 -->
    <header v-if="!isPC" class="flex-shrink-0 h-12 bg-card border-b border-border flex items-center px-2">
      <button @click="router.back()" class="w-10 h-10 flex items-center justify-center"><ChevronLeft class="w-5 h-5" /></button>
      <span class="flex-1 text-center font-semibold">{{ user.isAuditor ? '知识上传' : '经验分享' }}</span>
      <button v-if="user.isAuditor" @click="goReview" class="w-10 h-10 flex items-center justify-center text-accent" title="审查">
        <ShieldCheck class="w-5 h-5" />
      </button>
      <span v-else class="w-10"></span>
    </header>

    <!-- PC 标题栏 -->
    <header v-if="isPC" class="flex items-end justify-between gap-4">
      <div>
        <div class="text-xs text-text-2">知识库 / {{ user.isAuditor ? '知识上传' : '经验分享' }}</div>
        <h1 class="text-2xl font-bold text-primary mt-1 flex items-center gap-2">
          <Lightbulb class="w-6 h-6 text-accent" /> {{ user.isAuditor ? '知识上传' : '员工经验分享' }}
        </h1>
        <div class="text-sm text-text-2 mt-1">
          {{ user.isAuditor
            ? '作为审核员/管理员，您提交的知识会直接进入知识库，无需等待审核'
            : '把现场检修经验沉淀为知识，提交后进入「待审核」，审核通过后加入检索与图谱' }}
        </div>
      </div>
      <div class="flex items-center gap-2">
        <a v-if="user.isAuditor" @click.prevent="goReview" href="#"
                class="h-10 px-4 rounded-btn border border-accent text-accent hover:bg-accent/10 flex items-center gap-2">
          <ShieldCheck class="w-4 h-4" /> 进入知识审查
        </a>
        <button @click="refresh" :disabled="loading"
                class="h-10 w-10 rounded-btn border border-border bg-card flex items-center justify-center hover:border-accent text-text-2 hover:text-accent">
          <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
        </button>
      </div>
    </header>

    <div :class="isPC ? '' : 'flex-1 overflow-auto p-3 space-y-3'">
      <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
        <AlertTriangle class="w-4 h-4" />
        后端不可达，无法加载本人上传记录。
      </div>

      <!-- 概览统计 -->
      <div class="grid grid-cols-4 gap-2 text-center">
        <div class="industrial-card p-3">
          <div class="text-[11px] text-text-2">已提交</div>
          <div class="text-lg font-bold mt-1 mono">{{ stats.total }}</div>
        </div>
        <div class="industrial-card p-3">
          <div class="text-[11px] text-text-2">待审</div>
          <div class="text-lg font-bold mt-1 mono text-warning">{{ stats.pending }}</div>
        </div>
        <div class="industrial-card p-3">
          <div class="text-[11px] text-text-2">通过</div>
          <div class="text-lg font-bold mt-1 mono text-success">{{ stats.approved }}</div>
        </div>
        <div class="industrial-card p-3">
          <div class="text-[11px] text-text-2">驳回</div>
          <div class="text-lg font-bold mt-1 mono text-danger">{{ stats.rejected }}</div>
        </div>
      </div>

      <!-- 经验分享表单（主入口） -->
      <section class="industrial-card p-5 space-y-3">
        <div class="text-sm font-semibold flex items-center gap-2">
          <Lightbulb class="w-4 h-4 text-accent" />
          {{ user.isAuditor ? '录入一条知识' : '分享一条检修经验' }}
        </div>
        <!-- 审核员/管理员：分类选择（前线员工上传永远是案例，无需选择） -->
        <div v-if="user.isAuditor" class="flex items-center gap-2">
          <span class="text-sm text-text-2">分类</span>
          <div class="flex p-0.5 bg-bg rounded-btn border border-border text-sm w-max">
            <button v-for="c in [{k:'experience',l:'案例 / 经验'},{k:'manual',l:'手册 / 规程'}]" :key="c.k"
                    @click="category = c.k as any" :disabled="submitting"
                    :class="['px-4 h-8 rounded font-medium', category === c.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
              {{ c.l }}
            </button>
          </div>
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">标题 <span class="text-danger">*</span></div>
          <input v-model="title" placeholder="如：变频器报 OC 故障的快速排查思路"
                 :disabled="submitting"
                 class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card" />
        </div>
        <div>
          <div class="text-sm text-text-2 mb-1">经验正文（支持 Markdown） <span class="text-danger">*</span></div>
          <textarea v-model="body" rows="10"
                    placeholder="可使用 Markdown 标题、列表、表格记录现象、原因、处理步骤……如需附图片/手册，可在下方添加附件。"
                    :disabled="submitting"
                    class="w-full px-3 py-2 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card text-sm leading-relaxed"></textarea>
          <div class="text-[11px] text-text-2 mt-1">
            {{ user.isAuditor
              ? '您提交的内容会直接进入知识库，无需等待审核。'
              : '提交后状态为「待审」。如需添加附件，请在提交文字后再添加，附件会自动关联为本条经验的补充材料。' }}
          </div>
        </div>
        <div class="flex justify-end">
          <button class="h-10 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                  :disabled="submitting" @click="submitExperience">
            <Loader v-if="submitting" class="w-4 h-4 animate-spin" />
            <Send v-else class="w-4 h-4" />
            {{ submitting ? '提交中…' : (user.isAuditor ? '提交并入库' : '提交分享') }}
          </button>
        </div>
      </section>

      <!-- FIX6-resume O3：附件原子提交——选好附件后点上方"提交分享"一起发 -->
      <section class="industrial-card p-5">
        <div class="text-sm font-semibold mb-2 flex items-center gap-2">
          <Paperclip class="w-4 h-4 text-text-2" /> 添加附件（可选）
        </div>
        <div class="text-xs text-text-2 mb-2">
          附件会和经验一起原子提交，整体成功或失败；点击上方「提交分享」一起发送。
        </div>
        <div @click="fileInput?.click()"
             @dragover.prevent="dragging = true"
             @dragleave.prevent="dragging = false"
             @drop="onDrop"
             class="border-2 border-dashed rounded-card py-8 flex flex-col items-center justify-center cursor-pointer transition"
             :class="dragging ? 'border-accent bg-accent/5' : 'border-border hover:border-accent'">
          <Upload class="w-8 h-8" :class="dragging ? 'text-accent' : 'text-text-2'" />
          <div class="mt-2 text-sm font-medium" :class="dragging ? 'text-accent' : 'text-text'">
            {{ dragging ? '松手即可加入待提交列表' : '选择附件加入待提交列表' }}
          </div>
          <div class="mt-1 text-xs text-text-2 mono">支持 {{ ALLOWED.map(e => '.' + e).join(' · ') }} · 单文件 ≤ 50MB</div>
        </div>
        <input ref="fileInput" type="file" multiple class="hidden"
               :accept="ALLOWED.map(e => '.' + e).join(',')" @change="onPick" />

        <!-- 待提交附件列表（前端暂存，未上传） -->
        <ul v-if="pendingFiles.length" class="mt-3 space-y-1.5">
          <li v-for="(f, i) in pendingFiles" :key="i"
              class="flex items-center gap-2 px-3 py-2 rounded-btn border border-border bg-bg text-sm">
            <Paperclip class="w-4 h-4 text-accent" />
            <span class="flex-1 truncate">{{ f.name }}</span>
            <span class="text-xs text-text-2 mono">{{ fmtSize(f.size) }}</span>
            <span class="text-xs text-warning">待提交</span>
            <button @click="removePending(i)" :disabled="submitting"
                    class="ml-1 w-6 h-6 rounded hover:bg-danger/10 text-text-2 hover:text-danger flex items-center justify-center disabled:opacity-40">
              <X class="w-3.5 h-3.5" />
            </button>
          </li>
        </ul>

        <!-- 已提交附件状态（提交成功 / 失败回显） -->
        <ul v-if="uploads.length" class="mt-3 space-y-1.5">
          <li v-for="(u, i) in uploads" :key="i"
              class="flex items-center gap-2 px-3 py-2 rounded-btn border border-border bg-bg text-sm">
            <Loader v-if="u.status === 'uploading'" class="w-4 h-4 animate-spin text-accent" />
            <Check v-else-if="u.status === 'done'" class="w-4 h-4 text-success" />
            <X v-else class="w-4 h-4 text-danger" />
            <span class="flex-1 truncate">{{ u.name }}</span>
            <span class="text-xs text-text-2 mono">{{ fmtSize(u.size) }}</span>
            <span v-if="u.status === 'uploading'" class="text-xs text-text-2">提交中…</span>
            <span v-else-if="u.status === 'done'" class="text-xs text-warning mono">#{{ u.docId }} · 附件 · 待审</span>
            <span v-else class="text-xs text-danger">失败</span>
          </li>
        </ul>
      </section>

      <!-- 我的上传记录 -->
      <section class="industrial-card overflow-hidden">
        <header class="px-5 py-3 border-b border-border flex items-center gap-3">
          <div class="text-sm font-semibold flex items-center gap-2">
            <Database class="w-4 h-4 text-accent" /> 我的上传记录
            <span class="text-xs text-text-2 font-normal mono">{{ filtered.length }} / {{ docs.length }}</span>
          </div>
          <div class="ml-auto relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
            <input v-model="q" placeholder="搜索文档"
                   class="h-8 pl-9 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent text-sm"
                   :class="isPC ? 'w-64' : 'w-40'" />
          </div>
        </header>

        <div v-if="loading" class="py-8 text-center text-text-2">
          <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-xs">加载中…</div>
        </div>
        <div v-else-if="!filtered.length" class="py-10 text-center text-text-2">
          <Database class="w-8 h-8 mx-auto opacity-50" />
          <div class="mt-2 text-sm">{{ docs.length === 0 ? '尚未提交过任何经验 / 文档' : '没有匹配的文档' }}</div>
          <div class="mt-1 text-xs">提交后审核员会进行审核，通过后才会被检索引用</div>
        </div>
        <ul v-else class="divide-y divide-border max-h-[480px] overflow-auto">
          <li v-for="d in filtered" :key="d.id"
              class="px-5 py-3 flex items-start gap-3 hover:bg-bg/60">
            <FileText class="w-4 h-4 text-text-2 flex-shrink-0 mt-0.5" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium truncate">{{ d.title }}</div>
              <div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-text-2 flex-wrap">
                <span class="mono">#{{ d.id }}</span>
                <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ d.type }}</span>
                <span class="px-1.5 py-0.5 rounded-pill border whitespace-nowrap inline-block" :class="STATUS_CLS[d.status] || 'bg-bg border-border'">
                  {{ STATUS_LABEL[d.status] || d.status }}
                </span>
                <span v-if="d.attachments?.length" class="text-xs text-accent">
                  · 附件 x{{ d.attachments.length }}
                </span>
                <span class="mono opacity-70 hidden sm:inline">{{ d.created_at }}</span>
              </div>
              <div v-if="d.status === 'rejected' && d.reason" class="mt-1 text-xs text-danger">
                驳回原因：{{ d.reason }}
              </div>
            </div>
            <button v-if="d.status === 'rejected'" @click="resubmit(d)"
                    class="h-7 px-2 rounded-btn border border-accent text-accent hover:bg-accent/10 text-xs flex items-center gap-1 flex-shrink-0">
              <RefreshCw class="w-3 h-3" /> 重提
            </button>
          </li>
        </ul>
      </section>

      <div class="text-[11px] text-text-2 text-center pt-2">
        <Sparkles class="w-3 h-3 inline -mt-0.5" /> 一旦提交不可自行删除，如需下架请联系审核员
      </div>
    </div>
  </div>
</template>