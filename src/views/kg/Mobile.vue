<script setup lang="ts">
/**
 * 知识图谱 · 移动端（FIX3 第 5.3 项）
 * - 用 van-collapse 风格的卡片流
 * - 顶部"已选文档"筛选器（多选已审文档）
 * - 节点详情展开时拉取真实原文片段
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getGraph, getChunk, type KGGraph, type KGNode, type KGType, type ChunkContent } from '@/api/kg'
import { listDocs, type KbDoc } from '@/api/kb'
import { Search, ChevronDown, Loader, AlertTriangle, ExternalLink, Filter } from 'lucide-vue-next'

const router = useRouter()
const graph = ref<KGGraph | null>(null)
const loading = ref(false)
const errorMsg = ref('')
const q = ref('')
// FIX6-resume O1：两个独立过滤器，都影响图谱节点
type EntityType = 'device' | 'part' | 'fault' | 'method'
type DocType = 'case' | 'manual'
const filterEntity = ref<'all' | EntityType>('all')
const filterDocType = ref<'all' | DocType>('all')
const expanded = ref<Set<string>>(new Set())
const chunks = ref<Record<string, ChunkContent | null>>({})
// FIX7 续：追踪每个节点原文片段来自哪个关联文档（随案例/手册筛选联动）
const activeChunkDocs = ref<Record<string, NonNullable<KGNode['source_docs']>[number] | null>>({})

const docs = ref<KbDoc[]>([])
const selectedDocs = ref<Set<string>>(new Set())
const showDocFilter = ref(false)

const TYPE_META: Record<KGType, { name: string; cls: string }> = {
  device: { name: '设备', cls: 'bg-primary text-white' },
  part:   { name: '部件', cls: 'bg-ai text-white' },
  fault:  { name: '故障', cls: 'bg-accent text-white' },
  method: { name: '处理', cls: 'bg-success text-white' },
  case:   { name: '案例', cls: 'bg-primary-2 text-white' },
  manual: { name: '手册', cls: 'bg-text-2 text-white' }
}

const ENTITY_FILTERS: Array<{ k: 'all' | EntityType; l: string }> = [
  { k: 'all', l: '全部' },
  { k: 'device', l: '设备' },
  { k: 'part',   l: '部件' },
  { k: 'fault',  l: '故障' },
  { k: 'method', l: '处理' }
]
const DOC_FILTERS: Array<{ k: 'all' | DocType; l: string }> = [
  { k: 'all', l: '全部' },
  { k: 'case',   l: '案例' },
  { k: 'manual', l: '手册' }
]

const filtered = computed(() => {
  if (!graph.value) return []
  const ENTITY_SET: KGType[] = ['device', 'part', 'fault', 'method']
  return graph.value.nodes.filter(n => {
    const entityOk = ENTITY_SET.includes(n.type) && (
      filterEntity.value === 'all' || n.type === filterEntity.value
    )
    // FIX7 续：文档归属过滤——节点 type 没有 case/manual，归属来自 source_docs[].doc_type
    const docOk = (() => {
      if (filterDocType.value === 'all') return true
      const srcs = n.source_docs || []
      if (!srcs.length) return false
      return srcs.some(sd => {
        const isCase = (sd.doc_type || '').toLowerCase() === 'experience'
        return filterDocType.value === 'case' ? isCase : !isCase
      })
    })()
    return entityOk && docOk && (!q.value || n.label.includes(q.value))
  })
})

const reload = async () => {
  loading.value = true
  errorMsg.value = ''
  try {
    const g = await getGraph(selectedDocs.value.size ? Array.from(selectedDocs.value) : undefined)
    graph.value = g
    if (!g.nodes.length) errorMsg.value = '暂无可视化的图谱数据'
  } catch {
    graph.value = { nodes: [], edges: [] }
    errorMsg.value = '加载失败'
  } finally {
    loading.value = false
  }
}

const toggle = async (n: KGNode) => {
  const s = new Set(expanded.value)
  if (s.has(n.id)) s.delete(n.id)
  else {
    s.add(n.id)
    // FIX7 续：根据当前案例/手册筛选器，从 source_docs 中选取匹配的关联文档拉取 chunk
    if (chunks.value[n.id] === undefined) {
      const srcs = n.source_docs || []
      const matched = (() => {
        if (filterDocType.value === 'all') return srcs[0]
        return srcs.find(sd => {
          const isCase = (sd.doc_type || '').toLowerCase() === 'experience'
          return filterDocType.value === 'case' ? isCase : !isCase
        })
      })()
      const docId = matched ? String(matched.id) : n.docId
      const chunkId = matched?.chunk_id || n.chunkId
      activeChunkDocs.value[n.id] = matched || null
      chunks.value[n.id] = null  // 占位，避免重复请求
      if (docId && chunkId) {
        try { chunks.value[n.id] = await getChunk(docId, chunkId) }
        catch { chunks.value[n.id] = null }
      }
    }
  }
  expanded.value = s
}

const toggleDoc = (id: string) => {
  const s = new Set(selectedDocs.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selectedDocs.value = s
}

const applyDocFilter = async () => {
  showDocFilter.value = false
  await reload()
}

// FIX7 续 + FIX9：移动端跳到文档详情时同样携带 keyword / hl / page 精准定位
// hl 构造原则同 Pc.vue / 后端 _build_kg_snippet：keyword 在 hl 开头，单行内截取
const buildHl = (text: string, keyword: string): string => {
  if (!text) return ''
  for (const ln of text.split('\n')) {
    const s = ln.trim()
    if (!s || s.startsWith('[图片文件]')) continue
    const idx = s.indexOf(keyword)
    if (idx >= 0) return s.slice(idx, idx + 120)
  }
  for (const ln of text.split('\n')) {
    const s = ln.trim()
    if (s && !s.startsWith('[图片文件]')) return s.slice(0, 120)
  }
  return ''
}

// FIX8 + FIX10 + FIX11 v2：原文片段格式全局优化
// 把编号项及其续行合并成结构化块，解析名称/数量/工具/扭矩
interface SnippetLine {
  text: string
  html: string
  type: 'h' | 'list' | 'num' | 'para'
  indent: number
  num?: string
  name?: string
  quantity?: string
  tool?: string
  torque?: string
}

const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const highlightLine = (text: string, label: string): string => {
  if (!label) return escapeHtml(text)
  const safe = escapeHtml(text)
  const esc = escapeHtml(label)
  const i = safe.indexOf(esc)
  if (i < 0) return safe
  return safe.slice(0, i) + `<mark class="sn-hl">${esc}</mark>` + safe.slice(i + esc.length)
}

const parseNumLine = (s: string) => {
  const m = s.match(/^(\d{1,3})\s+(.*)$/)
  if (!m) return { num: '', name: s, quantity: '', tool: '', torque: '' }
  const num = m[1]
  const rest = m[2].trim()
  const r = rest.match(/^(.+?)\s+(\d+|—)\b(?:\s+(.*))?$/)
  if (!r) return { num, name: rest, quantity: '', tool: '', torque: '' }
  const name = r[1].trim()
  const quantity = r[2]
  const extra = r[3] ? r[3].trim() : ''
  let tool = '', torque = ''
  if (extra) {
    const parts = extra.split(/\s*\/\s*/)
    if (parts.length === 2) { tool = parts[0].trim(); torque = parts[1].trim() }
  }
  return { num, name, quantity, tool, torque }
}

const parseExtraLine = (s: string) => {
  const parts = s.split(/\s*\/\s*/)
  if (parts.length === 2) return { tool: parts[0].trim(), torque: parts[1].trim() }
  return { tool: '', torque: '' }
}

const formatSnippet = (text: string, label: string, max = 14): SnippetLine[] => {
  if (!text) return []
  const lines = text.split('\n')
  let ci = -1
  lines.forEach((ln, i) => { if (ci < 0 && ln.includes(label)) ci = i })
  if (ci < 0) {
    const norm = label.replace(/\s+/g, '')
    lines.forEach((ln, i) => { if (ci < 0 && ln.replace(/\s+/g, '').includes(norm)) ci = i })
  }
  if (ci < 0) ci = 0
  const from = Math.max(0, ci - 5), to = Math.min(lines.length, from + max)

  type Block =
    | { type: 'num'; lines: string[] }
    | { type: 'other'; line: string }
  const blocks: Block[] = []

  for (let i = from; i < to; i++) {
    const s = lines[i].trim()
    if (!s) continue
    if (/^\[图片/.test(s) || /page-\d{3}-image-\d{2}\.(png|jpg|jpeg|webp)/i.test(s)) continue
    if (/^!?\[.*?\]\(/.test(s) || /^uploads\//i.test(s) || /^extracted_images\//i.test(s)) continue

    if (/^\d{1,3}\s/.test(s)) {
      blocks.push({ type: 'num', lines: [s] })
    } else if (blocks.length) {
      const last = blocks[blocks.length - 1]
      if (last.type === 'num') {
        const isShort = s.length <= 70
        const isToolLike = /[\/±]/.test(s) || /^\d+#/.test(s) || /N[·.]?m/.test(s) || /杆|套筒|扳手|扭力/.test(s)
        if (isShort && isToolLike) { last.lines.push(s); continue }
      }
      blocks.push({ type: 'other', line: s })
    } else {
      blocks.push({ type: 'other', line: s })
    }
  }

  const out: SnippetLine[] = []
  for (const b of blocks) {
    if (b.type === 'num') {
      const main = b.lines[0]
      const p = parseNumLine(main)
      const extras = b.lines.slice(1)
      let tool = p.tool, torque = p.torque
      for (const ex of extras) {
        const e = parseExtraLine(ex)
        if (e.tool) { tool = e.tool; torque = e.torque }
      }
      out.push({
        text: p.name,
        html: highlightLine(p.name, label),
        type: 'num',
        indent: 0,
        num: p.num,
        name: p.name,
        quantity: p.quantity,
        tool,
        torque
      })
    } else {
      const s = b.line
      const indent = (s.length - s.trimStart().length) * 3
      let type: SnippetLine['type'] = 'para'
      if (/^(第[一二三四五六七八九十百千\d]+章|\d+(\.\d+)+[\s、.·])/.test(s)) type = 'h'
      else if (/^(\s*[·•\-–—*+])/.test(s)) type = 'list'
      const clean = type === 'list' ? s.replace(/^\s*[·•\-–—*+]\s*/, '').trim() : s.trim()
      out.push({ text: clean, html: highlightLine(clean, label), type, indent })
    }
  }
  return out
}

// FIX7 续：移动端跳到文档详情时，优先跳到当前筛选对应的关联文档
// keyword 优先用于精准定位（节点 label），hl 作为 fallback 上下文
const jumpToDoc = async (n: KGNode) => {
  const keyword = n.label || ''
  const matched = activeChunkDocs.value[n.id]
  if (matched) {
    await router.push({
      path: `/kb/preview/${matched.id}`,
      query: { ...(keyword ? { keyword } : {}), ...(matched.hl ? { hl: matched.hl } : {}), ...(matched.page ? { page: String(matched.page) } : {}) }
    })
    return
  }
  // fallback：没有 source_docs 信息时，用节点原始 docId
  if (!n.docId) return
  const c = chunks.value[n.id]
  if (c?.text) {
    const hl = buildHl(c.text, keyword)
    await router.push({
      path: `/kb/preview/${n.docId}`,
      query: { ...(keyword ? { keyword } : {}), ...(hl ? { hl } : {}), ...(c.page ? { page: String(c.page) } : {}) }
    })
  } else {
    await router.push(`/kb/preview/${n.docId}`)
  }
}

// FIX7 续：当案例/手册筛选器切换时，清除已有 chunk 缓存，下次展开时重新拉取对应类型的片段
watch(filterDocType, () => {
  // 清空 chunk 缓存，让 toggle 重新拉取
  chunks.value = {}
  activeChunkDocs.value = {}
})

onMounted(async () => {
  try { docs.value = (await listDocs()).filter(d => d.status === 'ready') } catch {}
  await reload()
})
</script>

<template>
  <div class="p-3 space-y-3">
    <!-- 搜索 + 类型筛选 -->
    <div class="space-y-2">
      <div class="flex gap-2">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
          <input v-model="q" placeholder="搜索实体…"
                 class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-card text-base" />
        </div>
        <button @click="showDocFilter = !showDocFilter"
                class="h-11 px-3 rounded-btn bg-card border border-border flex items-center gap-1 text-sm"
                :class="selectedDocs.size ? 'text-accent border-accent' : 'text-text-2'">
          <Filter class="w-4 h-4" />
          <span>{{ selectedDocs.size ? `已选 ${selectedDocs.size}` : '文档' }}</span>
        </button>
      </div>
      <!-- FIX6-resume O1：实体类型组 -->
      <div class="flex gap-2 overflow-x-auto hide-scrollbar -mx-1 px-1">
        <button v-for="f in ENTITY_FILTERS" :key="f.k" @click="filterEntity = f.k"
                :class="['px-4 h-8 rounded-pill text-sm flex-shrink-0',
                         filterEntity === f.k ? 'bg-accent text-white' : 'bg-card border border-border text-text-2']">
          {{ f.l }}
        </button>
      </div>
      <!-- FIX6-resume O1：文档类型组 -->
      <div class="flex gap-2 overflow-x-auto hide-scrollbar -mx-1 px-1">
        <button v-for="f in DOC_FILTERS" :key="f.k" @click="filterDocType = f.k"
                :class="['px-4 h-8 rounded-pill text-sm flex-shrink-0',
                         filterDocType === f.k ? 'bg-primary-2 text-white' : 'bg-card border border-border text-text-2']">
          {{ f.l }}
        </button>
      </div>
    </div>

    <!-- 文档筛选下拉 -->
    <div v-if="showDocFilter" class="industrial-card p-3 max-h-64 overflow-auto">
      <div class="text-xs text-text-2 mb-2">勾选要查看的文档（默认全部已审通过）</div>
      <div v-if="!docs.length" class="text-center text-xs text-text-2 py-4">尚无已审通过的文档</div>
      <label v-for="d in docs" :key="d.id" class="flex items-center gap-2 px-1 py-1.5 active:bg-bg rounded">
        <input type="checkbox" :checked="selectedDocs.has(String(d.id))"
               @change="toggleDoc(String(d.id))" class="accent-accent" />
        <span class="text-sm flex-1 truncate">{{ d.title }}</span>
        <span class="mono text-[10px] text-text-2">#{{ d.id }}</span>
      </label>
      <div class="flex gap-2 mt-3">
        <button class="flex-1 h-9 rounded-btn border border-border text-sm" @click="selectedDocs = new Set(); applyDocFilter()">
          全部
        </button>
        <button class="flex-1 h-9 rounded-btn bg-accent text-white text-sm font-semibold" @click="applyDocFilter">
          应用
        </button>
      </div>
    </div>

    <div class="text-xs text-text-2 px-1">共 {{ filtered.length }} 个实体</div>

    <div v-if="loading" class="industrial-card p-8 text-center text-text-2">
      <Loader class="w-5 h-5 mx-auto animate-spin text-accent" />
      <div class="mt-2 text-sm">加载中…</div>
    </div>

    <!-- 卡片列表（FIX5 第 14 项：分层渐入，避免一次性渲染产生视觉噪音） -->
    <div v-else-if="filtered.length" class="space-y-2">
      <div v-for="(n, idx) in filtered" :key="n.id"
           class="industrial-card overflow-hidden kg-card-fade"
           :style="{ animationDelay: `${Math.min(idx, 14) * 35}ms` }">
        <button class="w-full px-4 py-3 flex items-start gap-3 active:bg-bg" @click="toggle(n)">
          <span class="w-10 h-10 rounded-card flex-shrink-0 flex items-center justify-center text-xs font-bold" :class="TYPE_META[n.type].cls">
            {{ TYPE_META[n.type].name }}
          </span>
          <div class="flex-1 min-w-0 text-left">
            <div class="font-semibold text-base">{{ n.label }}</div>
            <div class="text-xs text-text-2 mt-0.5 truncate">
              <span v-if="n.desc">{{ n.desc }}</span>
              <span v-else>关联 {{ n.weight }} 条</span>
            </div>
          </div>
          <ChevronDown class="w-4 h-4 text-text-2 mt-1 transition-transform"
                       :class="expanded.has(n.id) ? 'rotate-180' : ''" />
        </button>

        <transition name="collapse">
          <div v-if="expanded.has(n.id)" class="border-t border-border p-3 bg-bg/50 space-y-2">
            <div class="text-xs text-text-2 mono">
              来源文档 #{{ activeChunkDocs[n.id]?.id || n.docId }}
              <span v-if="activeChunkDocs[n.id]?.title" class="ml-1">· {{ activeChunkDocs[n.id]!.title }}</span>
            </div>
            <div v-if="chunks[n.id] === null && !activeChunkDocs[n.id] && !n.docId" class="text-xs text-text-2 italic">
              当前筛选下暂无匹配的原文片段
            </div>
            <div v-else-if="!chunks[n.id] && n.docId" class="text-xs text-text-2 italic">
              暂无原文片段（可能后端未实现 /api/kb/{docId}/chunk/{chunkId}）
            </div>
            <div v-else-if="chunks[n.id]" class="bg-card rounded-btn p-3 sn-panel">
              <div v-if="chunks[n.id]!.page" class="mono text-[10px] text-text-2 mb-1">页码 {{ chunks[n.id]!.page }}</div>
              <div class="sn-body">
                <div v-for="(line, i) in formatSnippet(chunks[n.id]!.text, n.label)" :key="i"
                     :class="['sn-line', `sn-${line.type}`]"
                     :style="{ paddingLeft: `${line.indent}px` }">
                  <template v-if="line.type === 'num'">
                    <div class="sn-num">
                      <span class="sn-badge">{{ line.num }}</span>
                      <div class="sn-num-body">
                        <div class="sn-num-name" v-html="line.html"></div>
                        <div v-if="line.quantity && line.quantity !== '—' || line.tool || line.torque" class="sn-num-meta">
                          <span v-if="line.quantity && line.quantity !== '—'">数量 {{ line.quantity }}</span>
                          <span v-if="line.tool">工具 {{ line.tool }}</span>
                          <span v-if="line.torque">扭矩 {{ line.torque }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                  <template v-else>
                    <span v-if="line.type === 'list'" class="sn-dot">· </span>
                    <span v-html="line.html"></span>
                  </template>
                </div>
              </div>
            </div>
            <button v-if="activeChunkDocs[n.id] || n.docId" class="w-full h-9 rounded-btn border border-border text-xs flex items-center justify-center gap-1"
                    @click="jumpToDoc(n)">
              <ExternalLink class="w-3.5 h-3.5" /> 跳到文档详情
            </button>
          </div>
        </transition>
      </div>
    </div>

    <div v-else class="industrial-card p-8 text-center">
      <AlertTriangle class="w-8 h-8 mx-auto text-warning opacity-70" />
      <div class="mt-2 text-sm text-text-2">{{ errorMsg || '无符合条件的实体' }}</div>
    </div>
  </div>
</template>

<style scoped>
.collapse-enter-active, .collapse-leave-active { transition: opacity .2s, max-height .25s ease; max-height: 600px; overflow: hidden; }
.collapse-enter-from, .collapse-leave-to { opacity: 0; max-height: 0; }
.rotate-180 { transform: rotate(180deg); }

/* FIX5 第 14 项：移动端卡片分层渐入 */
.kg-card-fade {
  animation: kgFadeIn 480ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes kgFadeIn {
  0%   { opacity: 0; transform: translateY(8px) scale(0.98); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* FIX10+FIX11 v2：原文片段格式——结构化展示 */
.sn-panel { line-height: 1.6; }
.sn-body { font-size: 12px; }
.sn-line { color: var(--color-text-2); margin-bottom: 4px; }
.sn-h { font-weight: 600; color: var(--color-text); margin-top: 8px; margin-bottom: 4px; }
.sn-list { display: flex; align-items: baseline; }
.sn-dot { color: var(--color-accent); }
.sn-num { display: flex; align-items: flex-start; gap: 8px; }
.sn-num-body { flex: 1; min-width: 0; }
.sn-num-name { color: var(--color-text); word-break: break-word; }
.sn-num-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  color: var(--color-text-2);
  margin-top: 4px;
}
.sn-num-meta span {
  background: var(--color-bg);
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--color-border);
  white-space: nowrap;
}
.sn-badge {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  font-size: 11px;
  color: var(--color-accent);
  flex-shrink: 0;
  line-height: 1.5;
}
.sn-hl { background: rgba(255,193,7,0.35); color: var(--color-text); padding: 1px 2px; border-radius: 2px; font-weight: 600; }
[data-theme='dark'] .sn-hl { background: rgba(255,215,0,0.4); }
[data-theme='dark'] .sn-badge { background: var(--color-card); }
[data-theme='dark'] .sn-num-meta span { background: var(--color-card); }
</style>
