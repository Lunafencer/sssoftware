<script setup lang="ts">
/**
 * 知识库浏览（FIX5）
 * - 路由 /knowledge/browse，所有登录角色只读
 * - listDocs()：非审核员后端只返回已通过；审核员/管理员返回全部
 * - 搜索（按标题）+ 类型/分类筛选 chip 行
 * - 点击文档 → getDoc(id) 渲染 content（markdown / v-html）只读
 * - 导出 PDF / Markdown
 */
import { ref, computed, onMounted } from 'vue'
import { useDevice } from '@/composables/useDevice'
import { showToast, showFailToast } from 'vant'
import {
  Database, Search, FileText, Loader, RefreshCw, ChevronLeft,
  AlertTriangle, Download, FileDown, X
} from 'lucide-vue-next'
import { listDocs, getDoc, exportDoc, fetchDocBlobUrl, type KbDoc, type KbDocDetail, STATUS_LABEL } from '@/api/kb'
import { renderMarkdown } from '@/utils/markdown'
import EmptyState from '@/components/common/EmptyState.vue'

const { isPC } = useDevice()

const docs = ref<KbDoc[]>([])
const loading = ref(false)
const offline = ref(false)
const q = ref('')
const filterType = ref<string>('all')
const filterCategory = ref<string>('all')

const detail = ref<KbDocDetail | null>(null)
const detailLoading = ref(false)
const detailErr = ref('')
const showDetail = ref(false)
// FIX6 第 2 项：PDF 等二进制原始文件 Blob URL 预览
const detailBlobUrl = ref('')
const detailBlobErr = ref('')
const exporting = ref<'pdf' | 'md' | ''>('')

const refresh = async () => {
  loading.value = true
  try {
    docs.value = await listDocs()
    offline.value = false
  } catch {
    docs.value = []
    offline.value = true
  } finally {
    loading.value = false
  }
}
onMounted(refresh)

/** 文档类型 chip 列表（依据当前数据动态生成） */
const types = computed(() => {
  const set = new Set<string>()
  docs.value.forEach(d => d.type && set.add(d.type.toLowerCase()))
  return ['all', ...Array.from(set)]
})

const filtered = computed(() =>
  docs.value.filter(d =>
    (filterType.value === 'all' || d.type.toLowerCase() === filterType.value) &&
    (filterCategory.value === 'all' || (d.category || 'manual') === filterCategory.value) &&
    (!q.value || d.title.toLowerCase().includes(q.value.toLowerCase()))
  )
)

const openDoc = async (d: KbDoc) => {
  showDetail.value = true
  detail.value = null
  detailErr.value = ''
  detailBlobErr.value = ''
  if (detailBlobUrl.value) {
    URL.revokeObjectURL(detailBlobUrl.value)
    detailBlobUrl.value = ''
  }
  detailLoading.value = true
  try {
    detail.value = await getDoc(d.id)
    const t = (detail.value?.type || '').toLowerCase()
    if (t === 'pdf' || t === 'docx') {
      try {
        detailBlobUrl.value = await fetchDocBlobUrl(detail.value!.id)
      } catch {
        detailBlobErr.value = '原始文件加载失败'
      }
    }
  } catch {
    detailErr.value = '无法加载文档内容，请确认后端服务可用'
  } finally {
    detailLoading.value = false
  }
}

const closeDetail = () => {
  if (exporting.value) return
  showDetail.value = false
  detail.value = null
  if (detailBlobUrl.value) {
    URL.revokeObjectURL(detailBlobUrl.value)
    detailBlobUrl.value = ''
  }
}

const isBinaryDoc = (d: KbDocDetail | null) => {
  const t = (d?.type || '').toLowerCase()
  return t === 'pdf' || t === 'docx'
}

const doExport = async (format: 'pdf' | 'md') => {
  if (!detail.value || exporting.value) return
  exporting.value = format
  try {
    await exportDoc(detail.value.id, format, detail.value.title)
    showToast({ type: 'success', message: `已导出 ${format.toUpperCase()}` })
  } catch {
    showFailToast('导出失败，请稍后重试')
  } finally {
    exporting.value = ''
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
  <!-- ==================== PC ==================== -->
  <div v-if="isPC" class="p-6 max-w-[1400px] mx-auto space-y-4">
    <header class="flex items-end justify-between gap-4">
      <div>
        <div class="text-xs text-text-2">知识库 / 浏览</div>
        <h1 class="text-2xl font-bold text-primary mt-1 flex items-center gap-2">
          <Database class="w-6 h-6 text-accent" /> 知识库
        </h1>
        <div class="text-sm text-text-2 mt-1">浏览已入库的检修知识文档，支持导出 PDF / Markdown</div>
      </div>
      <button @click="refresh" :disabled="loading"
              class="h-10 px-4 rounded-btn border border-border bg-card hover:border-accent text-text-2 hover:text-accent flex items-center gap-2">
        <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" /> 刷新
      </button>
    </header>

    <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" />
      后端不可达，无法加载知识库。请确认服务已启动并已登录。
    </div>

    <section class="industrial-card overflow-hidden">
      <header class="px-5 py-3 border-b border-border flex items-center gap-3 flex-wrap">
        <div class="text-sm font-semibold flex items-center gap-2">
          <Database class="w-4 h-4 text-accent" /> 文档列表
          <span class="text-xs text-text-2 font-normal mono">{{ filtered.length }} / {{ docs.length }}</span>
        </div>
        <div class="ml-auto flex items-center gap-2 flex-wrap">
          <div class="flex p-0.5 bg-bg rounded-btn border border-border text-xs">
            <button v-for="c in [{k:'all',l:'全部'},{k:'experience',l:'案例'},{k:'manual',l:'手册'}]" :key="c.k" @click="filterCategory = c.k"
                    :class="['px-3 h-7 rounded font-medium', filterCategory === c.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
              {{ c.l }}
            </button>
          </div>
          <div class="flex p-0.5 bg-bg rounded-btn border border-border text-xs">
            <button v-for="t in types" :key="t" @click="filterType = t"
                    :class="['px-3 h-7 rounded font-medium uppercase', filterType === t ? 'bg-card shadow-card text-accent' : 'text-text-2']">
              {{ t === 'all' ? '全部' : t }}
            </button>
          </div>
          <div class="relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
            <input v-model="q" placeholder="按标题搜索"
                   class="h-8 pl-9 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent text-sm w-56" />
          </div>
        </div>
      </header>

      <div v-if="loading" class="py-16 text-center text-text-2">
        <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
        <div class="mt-2 text-sm">加载中…</div>
      </div>
      <EmptyState v-else-if="!filtered.length"
                  :title="offline ? '加载失败' : (docs.length === 0 ? '知识库暂无文档' : '没有符合条件的文档')"
                  :desc="offline ? '后端不可达，无法加载知识库' : '可调整筛选或搜索关键词'" />
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-text-2 text-xs">
            <th class="text-left font-medium px-5 py-2 w-16">ID</th>
            <th class="text-left font-medium px-5 py-2">文档名</th>
            <th class="text-left font-medium px-5 py-2 w-20">类型</th>
            <th class="text-left font-medium px-5 py-2 w-20">分类</th>
            <th class="text-left font-medium px-5 py-2 w-24">状态</th>
            <th class="text-left font-medium px-5 py-2 w-44">入库时间</th>
            <th class="text-right font-medium px-5 py-2 w-24">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in filtered" :key="d.id" class="border-t border-border hover:bg-bg/60 cursor-pointer" @click="openDoc(d)">
            <td class="px-5 py-3 mono text-text-2">#{{ d.id }}</td>
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <FileText class="w-4 h-4 text-text-2 flex-shrink-0" />
                <span class="font-medium truncate">{{ d.title }}</span>
              </div>
            </td>
            <td class="px-5 py-3">
              <span class="px-2 py-0.5 rounded text-[11px] mono uppercase bg-bg border border-border">{{ d.type }}</span>
            </td>
            <td class="px-5 py-3">
              <span class="px-2 py-0.5 rounded text-[11px] bg-bg border border-border whitespace-nowrap inline-block">{{ (d.category || 'manual') === 'experience' ? '案例' : '手册' }}</span>
            </td>
            <td class="px-5 py-3">
              <span class="px-2 py-0.5 rounded-pill text-[11px] border whitespace-nowrap inline-block" :class="STATUS_CLS[d.status] || 'bg-bg border-border text-text-2'">
                {{ STATUS_LABEL[d.status] || d.status }}
              </span>
            </td>
            <td class="px-5 py-3 text-text-2 mono text-xs">{{ d.created_at }}</td>
            <td class="px-5 py-3 text-right">
              <button class="h-7 px-2 rounded-btn border border-border text-text-2 hover:border-accent hover:text-accent text-xs"
                      @click.stop="openDoc(d)">查看</button>
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
        <Database class="w-5 h-5 text-accent" /> 知识库
      </h1>
      <div class="text-xs text-text-2 mt-1">共 {{ docs.length }} 份文档 · 点击查看全文</div>
    </header>

    <div v-if="offline" class="px-4 py-2 rounded-btn bg-warning/10 border border-warning/30 text-warning text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4" /> 后端不可达，无法加载知识库。
    </div>

    <div class="relative">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
      <input v-model="q" placeholder="按标题搜索"
             class="w-full h-9 pl-9 pr-3 rounded-btn border border-border bg-card outline-none focus:border-accent text-sm" />
    </div>

    <div class="flex gap-1 overflow-x-auto hide-scrollbar -mx-1 px-1">
      <button v-for="c in [{k:'all',l:'全部'},{k:'experience',l:'案例'},{k:'manual',l:'手册'}]" :key="c.k" @click="filterCategory = c.k"
              :class="['px-3 h-8 rounded-pill text-xs flex-shrink-0',
                       filterCategory === c.k ? 'bg-accent text-white' : 'bg-card border border-border text-text-2']">
        {{ c.l }}
      </button>
    </div>

    <div class="flex gap-1 overflow-x-auto hide-scrollbar -mx-1 px-1">
      <button v-for="t in types" :key="t" @click="filterType = t"
              :class="['px-3 h-8 rounded-pill text-xs flex-shrink-0 uppercase',
                       filterType === t ? 'bg-accent text-white' : 'bg-card border border-border text-text-2']">
        {{ t === 'all' ? '全部' : t }}
      </button>
    </div>

    <div v-if="loading" class="py-12 text-center text-text-2">
      <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
      <div class="mt-2 text-xs">加载中…</div>
    </div>
    <EmptyState v-else-if="!filtered.length"
                :title="offline ? '加载失败' : (docs.length === 0 ? '知识库暂无文档' : '没有符合条件的文档')"
                :desc="offline ? '后端不可达，无法加载知识库' : '可调整筛选或搜索关键词'" />
    <ul v-else class="space-y-2">
      <li v-for="d in filtered" :key="d.id" class="industrial-card p-3 active:bg-bg" @click="openDoc(d)">
        <div class="flex items-start gap-2">
          <FileText class="w-4 h-4 text-text-2 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium leading-snug truncate">{{ d.title }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-text-2">
              <span class="mono">#{{ d.id }}</span>
              <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ d.type }}</span>
              <span class="px-1.5 py-0.5 rounded bg-bg border border-border whitespace-nowrap inline-block">{{ (d.category || 'manual') === 'experience' ? '案例' : '手册' }}</span>
              <span class="px-1.5 py-0.5 rounded-pill border whitespace-nowrap inline-block" :class="STATUS_CLS[d.status] || 'bg-bg border-border'">{{ STATUS_LABEL[d.status] || d.status }}</span>
            </div>
          </div>
        </div>
      </li>
    </ul>
  </div>

  <!-- ==================== 详情弹层（PC 与移动端共用） ==================== -->
  <div v-if="showDetail" class="fixed inset-0 z-40 bg-black/40 flex items-stretch sm:items-center justify-center sm:p-4"
       @click.self="closeDetail">
    <div class="industrial-card bg-card w-full sm:max-w-3xl flex flex-col overflow-hidden"
         :class="isPC ? '' : 'rounded-none'" style="max-height: 100vh;">
      <header class="px-4 sm:px-5 py-3 border-b border-border flex items-center gap-2 flex-shrink-0">
        <button v-if="!isPC" @click="closeDetail" class="w-9 h-9 -ml-2 flex items-center justify-center">
          <ChevronLeft class="w-5 h-5" />
        </button>
        <FileText class="w-4 h-4 text-accent flex-shrink-0" />
        <span class="font-semibold flex-1 truncate">{{ detail?.title || '文档详情' }}</span>
        <button v-if="isPC" class="text-text-2 hover:text-danger" :disabled="!!exporting" @click="closeDetail">
          <X class="w-4 h-4" />
        </button>
      </header>

      <div class="flex-1 overflow-auto p-5">
        <div v-if="detailLoading" class="py-16 text-center text-text-2">
          <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
          <div class="mt-2 text-sm">加载文档内容…</div>
        </div>
        <div v-else-if="detailErr" class="py-16 text-center text-text-2">
          <AlertTriangle class="w-8 h-8 mx-auto text-warning opacity-70" />
          <div class="mt-3 text-sm">{{ detailErr }}</div>
        </div>
        <template v-else-if="detail">
          <div class="flex flex-wrap items-center gap-2 text-xs text-text-2 mb-4">
            <span class="mono">#{{ detail.id }}</span>
            <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ detail.type }}</span>
            <span v-if="detail.category" class="px-1.5 py-0.5 rounded bg-bg border border-border whitespace-nowrap inline-block">{{ detail.category === 'experience' ? '案例' : '手册' }}</span>
            <span class="px-1.5 py-0.5 rounded-pill border whitespace-nowrap inline-block" :class="STATUS_CLS[detail.status] || 'bg-bg border-border'">{{ STATUS_LABEL[detail.status] || detail.status }}</span>
            <span class="mono opacity-70">{{ detail.created_at }}</span>
          </div>
          <!-- FIX6 第 2 项：PDF / DOCX 用 iframe Blob URL 预览 -->
          <div v-if="isBinaryDoc(detail)" class="border border-border rounded-lg overflow-hidden" style="height:65vh">
            <div v-if="detailBlobErr" class="p-10 text-center text-text-2">
              <AlertTriangle class="w-8 h-8 mx-auto text-warning opacity-70" />
              <div class="mt-3 text-sm">{{ detailBlobErr }}</div>
            </div>
            <div v-else-if="!detailBlobUrl" class="p-10 text-center text-text-2">
              <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
              <div class="mt-2 text-sm">正在加载原始文件…</div>
            </div>
            <iframe v-else :src="detailBlobUrl" class="w-full h-full border-0" />
          </div>
          <div v-else class="md-body" v-html="renderMarkdown(detail.content || '（暂无正文内容）')"></div>
        </template>
      </div>

      <footer v-if="detail && !detailLoading && !detailErr"
              class="px-4 sm:px-5 py-3 border-t border-border flex justify-end gap-2 flex-shrink-0">
        <button class="h-9 px-4 rounded-btn border border-border flex items-center gap-2 disabled:opacity-60"
                :disabled="!!exporting" @click="doExport('md')">
          <Loader v-if="exporting === 'md'" class="w-4 h-4 animate-spin" />
          <FileDown v-else class="w-4 h-4" /> 导出 Markdown
        </button>
        <button class="h-9 px-4 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-2 disabled:opacity-60"
                :disabled="!!exporting" @click="doExport('pdf')">
          <Loader v-if="exporting === 'pdf'" class="w-4 h-4 animate-spin" />
          <Download v-else class="w-4 h-4" /> 导出 PDF
        </button>
      </footer>
    </div>
  </div>
</template>
