<script setup lang="ts">
/**
 * 知识库文档预览（FIX5 / FIX6 第 2 项）
 * - 文本类（txt/md/experience）：getDoc 取正文 + markdown 渲染
 * - PDF 等二进制：fetchDocBlobUrl 取带 token 的 Blob URL，注入 <iframe> 预览
 * - 导出 PDF / Markdown（exportDoc）
 *
 * FIX7 续：从 AI 回答的引用面板跳过来时，支持 ?chunk=&hl=&page= 三种锚点：
 *   - 文本类：渲染完 markdown 后在 .md-body 内按 hl 找文本节点，加 <mark> 并滚动；
 *     找不到完整 hl 时按长度逐级折半重试，最大限度命中片段开头
 *   - PDF：iframe src 拼 #page=&search= 让浏览器 PDF viewer 跳页 + 查找
 *   - DOCX：iframe 浏览器原生不支持锚点搜索，给一行 toast 提示
 */
import { computed, onMounted, onBeforeUnmount, ref, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDoc, exportDoc, fetchDocBlobUrl, type KbDocDetail, STATUS_LABEL } from '@/api/kb'
import { renderMarkdown } from '@/utils/markdown'
import { showToast, showFailToast } from 'vant'
import { ChevronLeft, FileText, Loader, AlertTriangle, Download, FileDown, Crosshair } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const docId = computed(() => Number(route.params.docId || 0))
const doc = ref<KbDocDetail | null>(null)
const loading = ref(false)
const error = ref('')
const exporting = ref<'pdf' | 'md' | ''>('')
const blobUrl = ref<string>('')      // FIX6 第 2 项：PDF Blob URL
const blobErr = ref('')

// FIX7 续：跳转锚点
const keyword = computed(() => (route.query.keyword as string) || '')   // 优先：节点 label（精准关键词）
const highlight = computed(() => (route.query.hl as string) || '')      // fallback：上下文片段
const targetPage = computed(() => {
  const p = Number(route.query.page)
  return Number.isFinite(p) && p > 0 ? p : 0
})
const mdBodyRef = ref<HTMLDivElement>()
const locateHint = ref('')   // 顶部小条：「已定位到引用片段」/「未在文本中找到引用片段」

const STATUS_CLS: Record<string, string> = {
  pending:    'bg-warning/10 text-warning border-warning/30',
  approved:   'bg-success/10 text-success border-success/30',
  ready:      'bg-success/10 text-success border-success/30',
  rejected:   'bg-danger/10 text-danger border-danger/30',
  taken_down: 'bg-text-2/10 text-text-2 border-border'
}

/** 是否走 iframe 预览（PDF 等二进制） */
const isBinary = computed(() => {
  const t = (doc.value?.type || '').toLowerCase()
  return t === 'pdf' || t === 'docx'
})

/**
 * FIX7 续：PDF iframe src 拼锚点。
 * Chrome / Edge 内置 viewer 识别 #page=N&search=... 跳页 + 自动查找命中。
 * keyword（节点 label）比 hl 片段更短更精准，PDF 查找器更适合短词搜索。
 */
const iframeSrc = computed(() => {
  if (!blobUrl.value) return ''
  const t = (doc.value?.type || '').toLowerCase()
  if (t !== 'pdf') return blobUrl.value
  const parts: string[] = []
  if (targetPage.value) parts.push(`page=${targetPage.value}`)
  // PDF search 用 keyword（短词精准），fallback 用 hl 前 40 字
  const searchTerm = keyword.value || highlight.value.slice(0, 40)
  if (searchTerm) parts.push(`search=${encodeURIComponent(searchTerm)}`)
  return parts.length ? `${blobUrl.value}#${parts.join('&')}` : blobUrl.value
})

const loadBlob = async () => {
  if (!doc.value) return
  try {
    blobUrl.value = await fetchDocBlobUrl(doc.value.id)
  } catch {
    blobErr.value = '原始文件加载失败，请稍后重试或联系管理员'
  }
}

/**
 * FIX7 续 + FIX9：在 markdown 渲染结果里查找并高亮文本节点。
 * 定位策略（优先级从高到低）：
 *   1. keyword（节点 label）——最精准，直接搜索关键词本身
 *   2. hl 片段逐级折半——hl 现在从 keyword 开头（单行内截取），所以短子串也以 keyword 起始
 * 命中后用 Range 拆分包 <mark>，scrollIntoView + 闪动提示用户视线。
 *
 * 关键改进：hl 不再是 space-join 跨行拼接（在 markdown 渲染后因换行而断裂无法匹配），
 * 而是包含 keyword 的单行原文从 keyword 位置截取，hl.slice(0,N) 的短子串也从 keyword 开始。
 */
const locateInMarkdown = () => {
  if (!mdBodyRef.value) return
  const root = mdBodyRef.value

  // 策略 1：优先搜索 keyword（节点 label），精准定位到关键词本身
  if (keyword.value) {
    const kw = keyword.value.trim()
    if (kw.length >= 2) {
      const hit = findAndMark(root, kw)
      if (hit) {
        locateHint.value = `已精准定位到「${kw}」`
        hit.scrollIntoView({ behavior: 'smooth', block: 'center' })
        return
      }
    }
  }

  // 策略 2：keyword 未命中，用 hl 片段搜索（hl 现从 keyword 开头，短子串也以 keyword 起始）
  if (!highlight.value) {
    locateHint.value = keyword.value ? `未在文本中找到「${keyword.value}」` : ''
    if (locateHint.value) showToast({ message: locateHint.value, position: 'top' })
    return
  }
  let needle = highlight.value.trim()
  // hl 从 keyword 开头，所以 tryLens 从短到长更合理——短子串更可能在单个 text node 内命中
  const tryLens = [needle.length, 60, 40, 24, 12, 8].filter(n => n > 0 && n <= needle.length)
  const seen = new Set<number>()
  for (const len of tryLens) {
    if (seen.has(len)) continue
    seen.add(len)
    const probe = needle.slice(0, len)
    if (probe.length < 2) continue   // 最低 2 字（中文关键词如"轴承"就 2 字）
    const hit = findAndMark(root, probe)
    if (hit) {
      locateHint.value = keyword.value
        ? `已定位到引用片段（关键词「${keyword.value}」未直接命中，使用了上下文定位）`
        : '已定位到引用片段'
      hit.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
  }
  locateHint.value = keyword.value
    ? `未在文本中找到「${keyword.value}」及相关片段`
    : '未在文本中找到引用片段'
  showToast({ message: locateHint.value, position: 'top' })
}

const findAndMark = (root: HTMLElement, probe: string): HTMLElement | null => {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) =>
      (n.textContent || '').includes(probe)
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_REJECT
  })
  const node = walker.nextNode() as Text | null
  if (!node || !node.textContent) return null
  const idx = node.textContent.indexOf(probe)
  if (idx < 0) return null
  // 把命中片段从 Text 节点切出来，包进 <mark>
  const range = document.createRange()
  range.setStart(node, idx)
  range.setEnd(node, idx + probe.length)
  const mark = document.createElement('mark')
  mark.className = 'kb-hl-mark'
  try {
    range.surroundContents(mark)
  } catch {
    return null  // 跨节点时 surroundContents 会抛
  }
  return mark
}

const onIframeLoad = () => {
  const kw = keyword.value || ''
  const hlShort = highlight.value.slice(0, 30)
  const searchTerm = kw || hlShort
  if (!searchTerm) return
  const t = (doc.value?.type || '').toLowerCase()
  if (t === 'docx') {
    // docx iframe 没有标准搜索协议；告知用户使用浏览器查找
    locateHint.value = `请在浏览器内用 Ctrl/Cmd+F 搜索：${kw || hlShort}`
  } else if (t === 'pdf') {
    locateHint.value = targetPage.value
      ? `已跳至第 ${targetPage.value} 页 · 在 PDF 内查找：${kw || hlShort}`
      : `已在 PDF 内查找：${kw || hlShort}`
  }
}

onMounted(async () => {
  loading.value = true
  try {
    doc.value = await getDoc(docId.value)
    if (isBinary.value) await loadBlob()
  } catch {
    error.value = '后端不可达或文档不存在，无法加载文档内容'
  } finally {
    loading.value = false
  }
  // 文本类：等 DOM 渲染完成后再定位（keyword 或 hl 都可触发）
  if (doc.value && !isBinary.value && (keyword.value || highlight.value)) {
    await nextTick()
    locateInMarkdown()
  }
})

// 同页内换 query 也要重新定位（同 docId 不同 keyword/hl 时 Vue Router 不会重建组件）
watch([() => route.query.keyword, () => route.query.hl], async () => {
  if (!doc.value || isBinary.value) return
  if (!keyword.value && !highlight.value) return
  // 清掉旧高亮
  mdBodyRef.value?.querySelectorAll('mark.kb-hl-mark').forEach(el => {
    const parent = el.parentNode
    if (!parent) return
    while (el.firstChild) parent.insertBefore(el.firstChild, el)
    parent.removeChild(el)
    parent.normalize()
  })
  await nextTick()
  locateInMarkdown()
})

onBeforeUnmount(() => {
  // 释放 Blob URL，避免内存泄漏
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
})

const doExport = async (format: 'pdf' | 'md') => {
  if (!doc.value || exporting.value) return
  exporting.value = format
  try {
    await exportDoc(doc.value.id, format, doc.value.title)
    showToast({ type: 'success', message: `已导出 ${format.toUpperCase()}` })
  } catch {
    showFailToast('导出失败，请稍后重试')
  } finally {
    exporting.value = ''
  }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="flex-shrink-0 px-4 py-3 border-b border-border bg-card flex items-center gap-2">
      <button @click="router.back()" class="w-9 h-9 rounded-btn hover:bg-bg flex items-center justify-center">
        <ChevronLeft class="w-5 h-5" />
      </button>
      <div class="flex-1 min-w-0">
        <div class="text-xs text-text-2">知识库 / 文档预览</div>
        <div class="text-sm font-semibold truncate">{{ doc?.title || `doc-${docId}` }}</div>
      </div>
      <template v-if="doc && !loading && !error">
        <button class="h-9 px-3 rounded-btn border border-border flex items-center gap-1.5 text-sm disabled:opacity-60"
                :disabled="!!exporting" @click="doExport('md')">
          <Loader v-if="exporting === 'md'" class="w-4 h-4 animate-spin" />
          <FileDown v-else class="w-4 h-4" /> <span class="hidden sm:inline">Markdown</span>
        </button>
        <button class="h-9 px-3 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold flex items-center gap-1.5 text-sm disabled:opacity-60"
                :disabled="!!exporting" @click="doExport('pdf')">
          <Loader v-if="exporting === 'pdf'" class="w-4 h-4 animate-spin" />
          <Download v-else class="w-4 h-4" /> PDF
        </button>
      </template>
    </header>

    <!-- FIX7 续：定位提示条（从引用面板跳过来时） -->
    <div v-if="locateHint" class="flex-shrink-0 px-4 py-2 bg-accent/10 border-b border-accent/30 text-xs text-accent flex items-center gap-2">
      <Crosshair class="w-3.5 h-3.5 flex-shrink-0" />
      <span class="truncate">{{ locateHint }}</span>
    </div>

    <div class="flex-1 overflow-auto p-6 max-w-3xl mx-auto w-full space-y-4">
      <div v-if="loading" class="industrial-card p-12 text-center text-text-2">
        <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
        <div class="mt-2 text-sm">加载中…</div>
      </div>
      <template v-else-if="doc">
        <div class="industrial-card p-5">
          <div class="flex items-start gap-3">
            <div class="w-12 h-12 rounded-card bg-accent/10 text-accent flex items-center justify-center flex-shrink-0">
              <FileText class="w-6 h-6" />
            </div>
            <div class="flex-1 min-w-0">
              <h1 class="text-lg font-semibold">{{ doc.title }}</h1>
              <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-2">
                <span class="mono">#{{ doc.id }}</span>
                <span class="px-1.5 py-0.5 rounded mono uppercase bg-bg border border-border">{{ doc.type }}</span>
                <span v-if="doc.category" class="px-1.5 py-0.5 rounded bg-bg border border-border">{{ doc.category }}</span>
                <span class="px-1.5 py-0.5 rounded-pill border" :class="STATUS_CLS[doc.status] || 'bg-bg border-border'">{{ STATUS_LABEL[doc.status] || doc.status }}</span>
                <span class="mono opacity-70">{{ doc.created_at }}</span>
              </div>
            </div>
          </div>
        </div>
        <!-- FIX6 第 2 项：PDF / DOCX 用 iframe Blob URL 预览原始文件 -->
        <div v-if="isBinary" class="industrial-card overflow-hidden" style="height:75vh">
          <div v-if="blobErr" class="p-10 text-center text-text-2">
            <AlertTriangle class="w-8 h-8 mx-auto text-warning opacity-70" />
            <div class="mt-3 text-sm">{{ blobErr }}</div>
          </div>
          <div v-else-if="!blobUrl" class="p-10 text-center text-text-2">
            <Loader class="w-6 h-6 mx-auto animate-spin text-accent" />
            <div class="mt-2 text-sm">正在加载原始文件…</div>
          </div>
          <iframe v-else :src="iframeSrc" class="w-full h-full border-0" @load="onIframeLoad" />
        </div>
        <div v-else class="industrial-card p-5">
          <div ref="mdBodyRef" class="md-body" v-html="renderMarkdown(doc.content || '（暂无正文内容）')"></div>
        </div>
      </template>
      <div v-else class="industrial-card p-10 text-center text-text-2">
        <AlertTriangle class="w-8 h-8 mx-auto text-warning opacity-70" />
        <div class="mt-3 text-sm">{{ error || '文档不存在' }}</div>
      </div>
    </div>
  </div>
</template>

<style>
/* FIX7 续 + FIX9：引用定位高亮 —— 醒目黄底 + 两次闪动提示用户视线 */
.md-body mark.kb-hl-mark {
  background: #FFE066;
  color: inherit;
  padding: 1px 3px;
  border-radius: 3px;
  font-weight: 600;
  animation: kb-hl-flash 2s ease-out 1;
}
@keyframes kb-hl-flash {
  0%   { background: #FF4444; box-shadow: 0 0 8px 4px rgba(255, 68, 68, 0.7); }
  15%  { background: #FFE066; box-shadow: 0 0 6px 3px rgba(255, 224, 102, 0.6); }
  30%  { background: #FFD700; box-shadow: 0 0 0 0 rgba(255, 215, 0, 0); }
  45%  { background: #FFE066; box-shadow: 0 0 4px 2px rgba(255, 224, 102, 0.4); }
  60%  { background: #FFF3B0; box-shadow: 0 0 0 0 rgba(255, 224, 102, 0); }
  100% { background: #FFF3B0; }
}
/* 深色模式下高亮适配 */
[data-theme='dark'] .md-body mark.kb-hl-mark {
  background: #FFD700;
  color: #1A1A2E;
}
</style>
