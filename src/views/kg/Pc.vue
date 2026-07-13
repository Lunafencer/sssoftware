<script setup lang="ts">
/**
 * 知识图谱 · PC（FIX3 第 5 项 / FIX6 第 6 项 + 第 8 项）
 * - 数据来源：已审入库的文档 → /api/kg/graph?doc_ids=...
 * - 严禁硬编码 mock 节点；图谱为空时显示空态
 * - 节点详情面板拉取真实原文片段（GET /api/kb/{docId}/chunk/{chunkId}）
 * - FIX6 第 6 项：审查员/管理员对节点 label/desc 做修正、删除节点或边
 * - FIX6 第 8 项：节点弹窗展示 source_docs 关联文档；侧栏支持按文档筛选
 */
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  getGraph, getChunk, updateNode, deleteNode, updateEdge, deleteEdge,
  type KGGraph, type KGNode, type KGType, type ChunkContent, type KGEdge
} from '@/api/kg'
import { listDocs, type KbDoc, isApprovedStatus } from '@/api/kb'
import { useUserStore } from '@/stores/user'
import { useTheme } from '@/composables/useTheme'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import { Search, RotateCcw, Download, Box, ExternalLink, Loader, AlertTriangle, Edit3, Trash2, FileText } from 'lucide-vue-next'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([GraphChart, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const router = useRouter()
const userStore = useUserStore()
const { theme } = useTheme()
const canEdit = computed(() => userStore.isAuditor)   // auditor 或 admin

// 主题感知：canvas 内的文字 / 线条颜色不能走 CSS 变量，需要根据 theme 手动取值
const isDark = computed(() => theme.value === 'dark')
const labelColor = computed(() => isDark.value ? '#E5E7EB' : '#1F2937')
const labelColorDim = computed(() => isDark.value ? '#94A3B8' : '#6B7280')
const lineColor = computed(() => isDark.value ? '#3B5577' : '#C2C9D6')

const graph = ref<KGGraph | null>(null)
const loading = ref(false)
const errorMsg = ref('')
const selected = ref<KGNode | null>(null)
const selectedEdge = ref<KGEdge | null>(null)
const chunkLoading = ref(false)
const chunk = ref<ChunkContent | null>(null)
// FIX7 续：追踪原文片段实际来自哪个关联文档（随案例/手册筛选联动 / 单击切换）
const activeChunkDoc = ref<NonNullable<KGNode['source_docs']>[number] | null>(null)

// FIX8 + FIX10 + FIX11 v2：原文片段格式全局优化
// 把编号项及其续行合并成结构化块，解析出 名称/数量/工具/扭矩，
// 让 BOM/零件清单类文本更可读；标题/bullet/普通段落保持分层渲染。
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

/** 解析 "12 M8×110 六角法兰面... 2 8# T 杆或套筒 / 20 ± 2 N·m" */
const parseNumLine = (s: string) => {
  const m = s.match(/^(\d{1,3})\s+(.*)$/)
  if (!m) return { num: '', name: s, quantity: '', tool: '', torque: '' }
  const num = m[1]
  const rest = m[2].trim()
  // 名称 数量(或 —) 可能还有内联工具/扭矩
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

/** 把续行里的 tool / torque 解析出来 */
const parseExtraLine = (s: string) => {
  const parts = s.split(/\s*\/\s*/)
  if (parts.length === 2) return { tool: parts[0].trim(), torque: parts[1].trim() }
  return { tool: '', torque: '' }
}

const formatSnippet = (text: string, label: string, max = 18): SnippetLine[] => {
  if (!text) return []
  const lines = text.split('\n')
  // 以关键词所在行为中心取窗口
  let ci = -1
  lines.forEach((ln, i) => { if (ci < 0 && ln.includes(label)) ci = i })
  if (ci < 0) {
    const norm = label.replace(/\s+/g, '')
    lines.forEach((ln, i) => { if (ci < 0 && ln.replace(/\s+/g, '').includes(norm)) ci = i })
  }
  if (ci < 0) ci = 0
  const from = Math.max(0, ci - 6), to = Math.min(lines.length, from + max)

  // 1. 先分组：编号项开头 + 紧跟的短续行（工具/扭矩）合并为同一个块
  type Block =
    | { type: 'num'; lines: string[] }
    | { type: 'other'; line: string }
  const blocks: Block[] = []

  for (let i = from; i < to; i++) {
    const s = lines[i].trim()
    if (!s) continue
    // 跳过图片/路径行
    if (/^\[图片/.test(s) || /page-\d{3}-image-\d{2}\.(png|jpg|jpeg|webp)/i.test(s)) continue
    if (/^!?\[.*?\]\(/.test(s) || /^uploads\//i.test(s) || /^extracted_images\//i.test(s)) continue

    if (/^\d{1,3}\s/.test(s)) {
      blocks.push({ type: 'num', lines: [s] })
    } else if (blocks.length) {
      const last = blocks[blocks.length - 1]
      if (last.type === 'num') {
        // 仅把短且像工具/扭矩说明的续行合并到上一个编号项
        const isShort = s.length <= 70
        const isToolLike = /[\/±]/.test(s) || /^\d+#/.test(s) || /N[·.]?m/.test(s) || /杆|套筒|扳手|扭力/.test(s)
        if (isShort && isToolLike) { last.lines.push(s); continue }
      }
      blocks.push({ type: 'other', line: s })
    } else {
      blocks.push({ type: 'other', line: s })
    }
  }

  // 2. 渲染块
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

const snippetLines = computed<SnippetLine[]>(() => {
  if (!chunk.value?.text || !selected.value) return []
  return formatSnippet(chunk.value.text, selected.value.label)
})

// FIX6-resume O1：实体过滤组 + 文档类型过滤组，两个独立的多选过滤器，都影响图谱节点
type EntityType = 'device' | 'part' | 'fault' | 'method'
type DocType = 'case' | 'manual'
const filterEntity = ref<'all' | EntityType>('all')
const filterDocType = ref<'all' | DocType>('all')
const filterDocId = ref<number | undefined>(undefined)   // FIX6 第 8 项：按文档筛选
const docOptions = ref<KbDoc[]>([])
const q = ref('')
const chartRef = ref<HTMLDivElement>()
let inst: echarts.ECharts | null = null

// FIX6 第 6 项：编辑对话框状态
const showEditNode = ref(false)
const editNodeLabel = ref('')
const editNodeDesc = ref('')
const showEditEdge = ref(false)
const editEdgeRel = ref('')

const TYPE_META: Record<KGType, { name: string; color: string; symbol: string }> = {
  device: { name: '设备', color: '#0B2545', symbol: 'roundRect' },
  part:   { name: '部件', color: '#00B7C2', symbol: 'circle' },
  fault:  { name: '故障', color: '#F26B1F', symbol: 'diamond' },
  method: { name: '处理', color: '#2E7D32', symbol: 'triangle' },
  case:   { name: '案例', color: '#15315F', symbol: 'rect' },
  manual: { name: '手册', color: '#94A3B8', symbol: 'pin' }
}

// 仅展示 4 种实体类型的图例（case/manual 是文档类型，不会作为节点出现）
const ENTITY_TYPES: KGType[] = ['device', 'part', 'fault', 'method']
const CATEGORIES = ENTITY_TYPES.map(k => ({
  name: TYPE_META[k].name,
  itemStyle: { color: TYPE_META[k].color }
}))

const filteredNodes = computed(() => {
  if (!graph.value) return []
  const ENTITY_SET: KGType[] = ['device', 'part', 'fault', 'method']
  return graph.value.nodes.filter(n => {
    // 实体类型过滤（节点的 type 永远是 device/part/fault/method 四种实体之一）
    const entityOk = ENTITY_SET.includes(n.type) && (
      filterEntity.value === 'all' || n.type === filterEntity.value
    )
    // FIX7 续：文档归属过滤——后端节点 type 没有 case/manual，
    // 节点的"案例/手册"归属来自 source_docs[].doc_type：
    //   experience → 案例（员工经验分享）
    //   pdf/docx/txt/md/其它 → 手册
    // 仅依据"来源文档里是否包含目标类型"判定，至少有一个匹配即放行
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

const visibleEdges = computed(() => {
  if (!graph.value) return []
  const ids = new Set(filteredNodes.value.map(n => n.id))
  return graph.value.edges.filter(e => ids.has(e.source) && ids.has(e.target))
})

// 右侧文档下拉框根据"案例/手册"筛选器过滤：
// experience 类型视为案例，其他（pdf/docx/txt/md 等）视为手册
const filteredDocOptions = computed(() => {
  if (filterDocType.value === 'all') return docOptions.value
  return docOptions.value.filter(d => {
    const isCase = (d.type || '').toLowerCase() === 'experience'
    return filterDocType.value === 'case' ? isCase : !isCase
  })
})

// FIX7 续：右侧「关联文档」面板应随当前案例/手册筛选器同步过滤
const filteredSourceDocs = computed(() => {
  if (!selected.value?.source_docs) return []
  if (filterDocType.value === 'all') return selected.value.source_docs
  return selected.value.source_docs.filter(sd => {
    const isCase = (sd.doc_type || '').toLowerCase() === 'experience'
    return filterDocType.value === 'case' ? isCase : !isCase
  })
})

const renderChart = () => {
  if (!inst || !graph.value) return
  const cats = ENTITY_TYPES
  const isLarge = filteredNodes.value.length > 200
  const nodeCount = filteredNodes.value.length || 1

  // 根据节点数量自适应斥力和边长，避免节点少时太散、节点多时太挤
  const repulsion = nodeCount < 30 ? 320 : nodeCount < 80 ? 420 : 520
  const edgeLen = nodeCount < 30 ? [100, 160] : nodeCount < 80 ? [90, 150] : [70, 130]

  const nodes = filteredNodes.value.map((n, i) => {
    const angle = (i / nodeCount) * Math.PI * 2
    return {
      id: n.id,
      name: n.label,
      value: n.weight,
      x: Math.cos(angle) * 200,
      y: Math.sin(angle) * 200,
      // 节点大小更均匀：20~36，避免大节点遮挡小节点
      symbolSize: 20 + Math.min(n.weight, 16),
      symbol: TYPE_META[n.type].symbol,
      category: cats.indexOf(n.type),
      itemStyle: { color: TYPE_META[n.type].color, opacity: 0.92 },
      label: {
        show: !isLarge,
        position: 'right',
        color: labelColor.value,
        fontSize: 11,
        textBorderColor: isDark.value ? '#0B1B33' : '#F5F7FA',
        textBorderWidth: 2,
        distance: 4
      },
      raw: n
    }
  })
  const links = visibleEdges.value.map(e => ({
    source: e.source, target: e.target, value: e.rel,
    label: { show: false, formatter: e.rel, fontSize: 9, color: labelColorDim.value },
    lineStyle: { color: lineColor.value, curveness: 0.15, width: 1 },
    raw: e
  }))
  inst.setOption({
    // 只保留初始渐现动画，关闭布局迭代过程动画，避免节点"乱飞+摇晃"
    animation: true,
    animationDuration: 450,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 0,
    animationEasingUpdate: 'linear',
    tooltip: {
      backgroundColor: isDark.value ? 'rgba(21,49,95,0.95)' : 'rgba(255,255,255,0.95)',
      borderColor: isDark.value ? '#234373' : '#E4E7ED',
      textStyle: { color: labelColor.value },
      formatter: (p: any) => {
        if (p.dataType === 'edge') return `<div style="font-weight:600">${p.data.value}</div>`
        const n: KGNode = p.data.raw
        const lines = [
          `<div style="font-weight:600;margin-bottom:4px">${n.label}</div>`,
          `<div style="color:${labelColorDim.value};font-size:12px">类型: ${TYPE_META[n.type].name}</div>`,
          `<div style="color:${labelColorDim.value};font-size:12px">关联: ${n.weight} 条</div>`
        ]
        if (n.desc) lines.push(`<div style="margin-top:4px;font-size:12px">${n.desc}</div>`)
        return lines.join('')
      }
    },
    legend: [{
      data: CATEGORIES.map(c => c.name),
      bottom: 8,
      icon: 'circle',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: labelColorDim.value, fontSize: 11 }
    }],
    series: [{
      type: 'graph',
      layout: 'force',
      data: nodes,
      links,
      categories: CATEGORIES,
      roam: true,
      draggable: true,
      large: isLarge,
      focusNodeAdjacency: true,
      force: {
        repulsion,
        edgeLength: edgeLen,
        gravity: 0.04,
        friction: 0.9,
        // 关闭布局迭代动画：force 算法在后台静默收敛后才渲染，用户只看到最终稳定结果
        layoutAnimation: false,
        initLayout: 'circular'
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 2.5, color: '#F26B1F' },
        label: { show: true, fontWeight: 700, color: labelColor.value }
      },
      lineStyle: { width: 1, opacity: 0.5 }
      // 不设 animationDelay：整体一次性淡入，避免逐节点闪烁
    }]
  }, { notMerge: true })
}

const setup = () => {
  if (!chartRef.value) return
  const reused = echarts.getInstanceByDom(chartRef.value)
  inst = reused || echarts.init(chartRef.value)
  inst.off('click')
  // FIX7 第 2 项：监听首次 rendered 事件，强制 resize 一次消除节点/线初始错位
  let resized = false
  inst.off('rendered')
  inst.on('rendered', () => {
    if (resized) return
    resized = true
    inst?.resize()
  })
  inst.on('click', (p: any) => {
    if (p.dataType === 'node') {
      const n = p.data.raw as KGNode
      selected.value = n
      selectedEdge.value = null
      chunk.value = null
      activeChunkDoc.value = null
      // FIX7 续：根据当前案例/手册筛选器，从 source_docs 中选取匹配的关联文档拉取 chunk
      // 不再总是用 n.docId/n.chunkId（那是节点创建时的首个来源文档，可能指向手册）
      const srcs = n.source_docs || []
      const matched = (() => {
        if (filterDocType.value === 'all') return srcs[0]   // 全部：取第一个
        return srcs.find(sd => {
          const isCase = (sd.doc_type || '').toLowerCase() === 'experience'
          return filterDocType.value === 'case' ? isCase : !isCase
        })
      })()
      const docId = matched ? String(matched.id) : n.docId
      const chunkId = matched?.chunk_id || n.chunkId
      if (docId && chunkId) {
        activeChunkDoc.value = matched || null
        chunkLoading.value = true
        getChunk(docId, chunkId)
          .then(c => { chunk.value = c })
          .finally(() => { chunkLoading.value = false })
      }
    } else if (p.dataType === 'edge') {
      const e = p.data.raw as KGEdge
      selectedEdge.value = e
      selected.value = null
    }
  })
  renderChart()
}

const resetView = () => {
  filterEntity.value = 'all'
  filterDocType.value = 'all'
  filterDocId.value = undefined
  q.value = ''
  selected.value = null
  selectedEdge.value = null
  chunk.value = null
  reload()
}

const exportImg = () => {
  if (!inst) return
  const url = inst.getDataURL({ pixelRatio: 2, backgroundColor: '#fff' })
  const a = document.createElement('a')
  a.href = url
  a.download = `知识图谱-${Date.now()}.png`
  a.click()
}

// FIX7 续 + FIX9：从 chunk 文本中构造 hl 参数，用于 Preview 页精准定位
// 核心原则同后端 _build_kg_snippet：hl 必须以 keyword 开头，必须是单行内截取的自然子串
// 不做 space-join（跨行拼接在 markdown 渲染后因换行而断裂，无法匹配）
const buildHl = (text: string, keyword: string): string => {
  if (!text) return ''
  // 找包含 keyword 的行，从 keyword 位置截取（keyword 在 hl 开头）
  for (const ln of text.split('\n')) {
    const s = ln.trim()
    if (!s || s.startsWith('[图片文件]')) continue
    const idx = s.indexOf(keyword)
    if (idx >= 0) return s.slice(idx, idx + 120)
  }
  // keyword 不在单行内 → fallback：取第一行非空内容
  for (const ln of text.split('\n')) {
    const s = ln.trim()
    if (s && !s.startsWith('[图片文件]')) return s.slice(0, 120)
  }
  return ''
}

// FIX8：单击关联文档时，切换下方原文片段到该文档对应 chunk
const loadChunkFromDoc = async (sd: NonNullable<KGNode['source_docs']>[number]) => {
  if (!selected.value) return
  activeChunkDoc.value = sd
  chunk.value = null
  const docId = String(sd.id)
  const chunkId = sd.chunk_id
  if (docId && chunkId) {
    chunkLoading.value = true
    try { chunk.value = await getChunk(docId, chunkId) }
    finally { chunkLoading.value = false }
  }
}

// FIX7 续：双击关联文档时，携带 keyword / hl / page 跳转到 Preview 页
// keyword 优先用于精准定位（节点 label），hl 作为 fallback 上下文
const jumpToDoc = async (sd: NonNullable<KGNode['source_docs']>[number]) => {
  const keyword = selected.value?.label || ''
  const hl = sd.hl || (activeChunkDoc.value?.id === sd.id && chunk.value?.text && selected.value
    ? buildHl(chunk.value.text, keyword) : '')
  await router.push({
    path: `/kb/preview/${sd.id}`,
    query: { ...(keyword ? { keyword } : {}), ...(hl ? { hl } : {}), ...(sd.page ? { page: String(sd.page) } : {}) }
  })
}

// FIX7 续：从原文片段跳到文档详情，跳转到当前实际展示片段的文档（而非节点固定的 docId）
// keyword 优先用于精准定位（节点 label），hl 作为 fallback 上下文
const jumpToPrimaryDoc = async () => {
  const keyword = selected.value?.label || ''
  // 优先使用 activeChunkDoc（随筛选/单击切换的文档），其 hl/page 最精准
  if (activeChunkDoc.value) {
    await jumpToDoc(activeChunkDoc.value)
    return
  }
  // fallback：没有 source_docs 信息时，用节点原始 docId
  if (!selected.value?.docId) return
  const c = chunk.value
  if (c?.text) {
    const hl = buildHl(c.text, keyword)
    await router.push({
      path: `/kb/preview/${selected.value.docId}`,
      query: { ...(keyword ? { keyword } : {}), ...(hl ? { hl } : {}), ...(c.page ? { page: String(c.page) } : {}) }
    })
  } else {
    await router.push(`/kb/preview/${selected.value.docId}`)
  }
}

const reload = async () => {
  loading.value = true
  errorMsg.value = ''
  try {
    const g = await getGraph(undefined, filterDocId.value)
    graph.value = g
    if (!g.nodes.length) {
      errorMsg.value = filterDocId.value
        ? '所选文档暂无可视化的图谱实体。'
        : '暂无可视化的图谱数据。请先在「知识上传」补充已审通过的文档，或确认后端 /api/kg/graph 已实现。'
    }
  } catch (e: any) {
    graph.value = { nodes: [], edges: [] }
    errorMsg.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
  await nextTick()
  setup()
}

const loadDocOptions = async () => {
  try {
    const docs = await listDocs()
    docOptions.value = docs.filter(d => isApprovedStatus(d.status))
  } catch {
    docOptions.value = []
  }
}

const onResize = () => inst?.resize()
let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  await loadDocOptions()
  await reload()
  window.addEventListener('resize', onResize)
  // FIX7 第 2 项：监听容器尺寸变化，确保父容器过渡动画结束后图谱能正确渲染
  if (chartRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(chartRef.value)
  }
})

// FIX(内存)：导航离开时释放 ECharts 实例与监听，避免长班次运行累积内存
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  resizeObserver?.disconnect()
  resizeObserver = null
  inst?.dispose()
  inst = null
})

watch([filterEntity, filterDocType, q], () => {
  // 当"案例/手册"筛选器变化时，若当前选中的文档已不在过滤后的列表中，则重置
  if (filterDocType.value !== 'all') {
    const currentDoc = docOptions.value.find(d => d.id === filterDocId.value)
    if (currentDoc) {
      const isCase = (currentDoc.type || '').toLowerCase() === 'experience'
      const mismatch = (filterDocType.value === 'case' && !isCase) || (filterDocType.value === 'manual' && isCase)
      if (mismatch) filterDocId.value = undefined
    }
  }
  renderChart()
})
watch(filterDocId, () => reload())
watch(theme, () => renderChart())   // 主题切换时重绘图谱，使标签/连线/tooltip 颜色同步

// FIX7 续：当案例/手册筛选器切换时，重新拉取当前选中节点的 chunk，使原文片段随筛选联动
watch(filterDocType, () => {
  if (!selected.value) return
  chunk.value = null
  activeChunkDoc.value = null
  const n = selected.value
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
  if (docId && chunkId) {
    activeChunkDoc.value = matched || null
    chunkLoading.value = true
    getChunk(docId, chunkId)
      .then(c => { chunk.value = c })
      .finally(() => { chunkLoading.value = false })
  }
})

// ============ FIX6 第 6 项：编辑节点 / 删除节点 ============
const openEditNode = () => {
  if (!selected.value) return
  editNodeLabel.value = selected.value.label
  editNodeDesc.value = selected.value.desc || ''
  showEditNode.value = true
}

const submitEditNode = async () => {
  if (!selected.value) return
  try {
    await updateNode(selected.value.id, {
      label: editNodeLabel.value,
      desc: editNodeDesc.value
    })
    showToast({ type: 'success', message: '已更新节点' })
    showEditNode.value = false
    await reload()
  } catch {
    showFailToast('节点更新失败')
  }
}

const removeNode = async () => {
  if (!selected.value) return
  try {
    await showConfirmDialog({
      title: '删除节点',
      confirmButtonText: '删除',
      confirmButtonColor: '#E5484D',
      message: `确认从图谱中移除节点「${selected.value.label}」？仅图谱视图受影响，原始文档不变。`
    })
  } catch { return }
  try {
    await deleteNode(selected.value.id)
    showToast({ type: 'success', message: '已删除节点' })
    selected.value = null
    await reload()
  } catch {
    showFailToast('节点删除失败')
  }
}

// ============ FIX6 第 6 项：编辑边 / 删除边 ============
const edgeKey = (e: KGEdge) => {
  const a = e.source, b = e.target
  return a < b ? `${a}|${b}` : `${b}|${a}`
}

const openEditEdge = () => {
  if (!selectedEdge.value) return
  editEdgeRel.value = selectedEdge.value.rel
  showEditEdge.value = true
}

const submitEditEdge = async () => {
  if (!selectedEdge.value) return
  try {
    await updateEdge(edgeKey(selectedEdge.value), { rel: editEdgeRel.value })
    showToast({ type: 'success', message: '已更新关系' })
    showEditEdge.value = false
    await reload()
  } catch {
    showFailToast('关系更新失败')
  }
}

const removeEdge = async () => {
  if (!selectedEdge.value) return
  try {
    await showConfirmDialog({
      title: '删除关系',
      confirmButtonText: '删除',
      confirmButtonColor: '#E5484D',
      message: `确认从图谱中移除关系「${selectedEdge.value.rel}」？仅图谱视图受影响。`
    })
  } catch { return }
  try {
    await deleteEdge(edgeKey(selectedEdge.value))
    showToast({ type: 'success', message: '已删除关系' })
    selectedEdge.value = null
    await reload()
  } catch {
    showFailToast('关系删除失败')
  }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="flex-shrink-0 px-6 py-3 bg-card border-b border-border flex items-center gap-3 flex-wrap">
      <div class="relative flex-1 max-w-md">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
        <input v-model="q" placeholder="搜索实体名称…"
               class="w-full h-9 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent" />
      </div>
      <!-- FIX6-resume O1：实体类型组 -->
      <div class="flex p-0.5 bg-bg rounded-btn border border-border text-xs">
        <button v-for="t in [
                  { k: 'all',    l: '全部' },
                  { k: 'device', l: '设备' },
                  { k: 'part',   l: '部件' },
                  { k: 'fault',  l: '故障' },
                  { k: 'method', l: '处理' }
                ]"
                :key="t.k" @click="filterEntity = t.k as any"
                :class="['px-3 h-7 rounded font-medium', filterEntity === t.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
          {{ t.l }}
        </button>
      </div>
      <!-- FIX6-resume O1：文档类型组（独立过滤器） -->
      <div class="flex p-0.5 bg-bg rounded-btn border border-border text-xs">
        <button v-for="t in [
                  { k: 'all',    l: '全部' },
                  { k: 'case',   l: '案例' },
                  { k: 'manual', l: '手册' }
                ]"
                :key="t.k" @click="filterDocType = t.k as any"
                :class="['px-3 h-7 rounded font-medium', filterDocType === t.k ? 'bg-card shadow-card text-accent' : 'text-text-2']">
          {{ t.l }}
        </button>
      </div>
      <!-- FIX6 第 8 项：按文档筛选 -->
      <select v-model="filterDocId"
              class="h-9 px-2 rounded-btn border border-border bg-bg text-sm outline-none focus:border-accent">
        <option :value="undefined">全部文档</option>
        <option v-for="d in filteredDocOptions" :key="d.id" :value="d.id">#{{ d.id }} · {{ d.title }}</option>
      </select>
      <div class="ml-auto flex items-center gap-2">
        <button class="h-9 px-3 rounded-btn border border-border flex items-center gap-1 text-sm hover:bg-bg" @click="resetView" title="重置视图">
          <RotateCcw class="w-4 h-4" /> 重置
        </button>
        <button class="h-9 px-3 rounded-btn border border-border flex items-center gap-1 text-sm hover:bg-bg" @click="exportImg" title="导出图片">
          <Download class="w-4 h-4" /> 导出
        </button>
      </div>
    </header>

    <div class="flex-1 grid grid-cols-12 overflow-hidden">
      <main class="col-span-9 relative bg-bg overflow-hidden">
        <div ref="chartRef" class="w-full h-full"></div>

        <div v-if="loading"
             class="absolute inset-0 flex items-center justify-center bg-bg/80 backdrop-blur-sm">
          <div class="text-text-2">
            <Loader class="w-8 h-8 mx-auto animate-spin text-accent" />
            <div class="mt-2 text-sm">加载图谱数据…</div>
          </div>
        </div>
        <div v-else-if="!graph?.nodes.length"
             class="absolute inset-0 flex items-center justify-center bg-bg/80 backdrop-blur-sm">
          <div class="industrial-card p-8 text-center max-w-md">
            <AlertTriangle class="w-10 h-10 mx-auto text-warning opacity-70" />
            <div class="mt-3 text-sm font-semibold">暂无可视化的图谱数据</div>
            <div class="mt-2 text-xs text-text-2">{{ errorMsg }}</div>
          </div>
        </div>

        <div class="absolute top-3 left-3 industrial-card px-3 py-2 text-xs space-y-1">
          <div class="font-semibold mb-1">操作提示</div>
          <div class="text-text-2">· 拖拽 / 滚轮缩放</div>
          <div class="text-text-2">· 点击节点 / 边查看详情</div>
          <div v-if="canEdit" class="text-text-2">· 审查员可编辑 / 删除</div>
        </div>
      </main>

      <aside class="col-span-3 border-l border-border bg-card overflow-auto">
        <!-- 节点详情 -->
        <div v-if="selected" class="p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="text-xs uppercase mono px-2 py-0.5 inline-block rounded text-white"
                 :style="{ background: TYPE_META[selected.type].color }">
              {{ TYPE_META[selected.type].name }}
            </div>
            <!-- FIX6 第 6 项：节点编辑操作 -->
            <div v-if="canEdit" class="flex items-center gap-1">
              <button class="h-7 w-7 rounded hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent"
                      title="编辑节点" @click="openEditNode">
                <Edit3 class="w-3.5 h-3.5" />
              </button>
              <button class="h-7 w-7 rounded hover:bg-danger/10 flex items-center justify-center text-text-2 hover:text-danger"
                      title="删除节点" @click="removeNode">
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <h3 class="text-lg font-bold mt-2">{{ selected.label }}</h3>
          <div class="text-xs text-text-2 mt-1">关联 <span class="mono">{{ selected.weight }}</span> 条</div>
          <p v-if="selected.desc" class="text-sm mt-3 text-text-2 leading-relaxed">{{ selected.desc }}</p>

          <!-- FIX6 第 8 项：关联文档列表 -->
          <div class="mt-4">
            <div class="text-xs font-semibold mb-2 text-text">关联文档</div>
            <ul v-if="filteredSourceDocs.length" class="space-y-1.5">
              <li v-for="sd in filteredSourceDocs" :key="sd.id">
                <button class="w-full text-left h-8 px-2 rounded-btn border border-border text-xs flex items-center gap-1.5 hover:border-accent hover:text-accent select-none"
                        @click="loadChunkFromDoc(sd)"
                        @dblclick="jumpToDoc(sd)"
                        title="单击切换原文片段，双击打开文档">
                  <FileText class="w-3.5 h-3.5 flex-shrink-0" />
                  <span class="truncate">#{{ sd.id }} · {{ sd.title }}</span>
                </button>
              </li>
            </ul>
            <div v-else class="text-xs text-text-2 italic">当前筛选下暂无关联文档</div>
          </div>

          <div class="mt-4">
            <div class="text-xs font-semibold mb-2 text-text">
              原文片段
              <span v-if="activeChunkDoc" class="text-text-2 ml-1">来自 #{{ activeChunkDoc.id }} · {{ activeChunkDoc.title }}</span>
            </div>
            <div v-if="chunkLoading" class="text-xs text-text-2 flex items-center gap-1.5">
              <Loader class="w-3.5 h-3.5 animate-spin" /> 加载中…
            </div>
            <div v-else-if="snippetLines.length" class="bg-bg rounded-btn border border-border p-3 max-h-72 overflow-auto sn-panel">
              <div v-if="chunk?.title" class="font-semibold text-text mb-1 text-xs">{{ chunk.title }}</div>
              <div v-if="chunk?.page" class="mono text-[10px] text-text-2 mb-2">页码 {{ chunk.page }}</div>
              <div class="sn-body">
                <div v-for="(line, i) in snippetLines" :key="i"
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
            <div v-else class="text-xs text-text-2 italic">
              当前筛选下暂无匹配的原文片段。
            </div>

            <button v-if="chunk" class="mt-3 w-full h-9 rounded-btn border border-border text-sm flex items-center justify-center gap-1 hover:border-accent hover:text-accent"
                    @click="jumpToPrimaryDoc">
              <ExternalLink class="w-4 h-4" /> 跳到文档详情
            </button>
          </div>
        </div>

        <!-- 边详情 -->
        <div v-else-if="selectedEdge" class="p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="text-xs px-2 py-0.5 inline-block rounded bg-bg border border-border">关系</div>
            <div v-if="canEdit" class="flex items-center gap-1">
              <button class="h-7 w-7 rounded hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent"
                      title="编辑关系" @click="openEditEdge">
                <Edit3 class="w-3.5 h-3.5" />
              </button>
              <button class="h-7 w-7 rounded hover:bg-danger/10 flex items-center justify-center text-text-2 hover:text-danger"
                      title="删除关系" @click="removeEdge">
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <h3 class="text-lg font-bold mt-2">{{ selectedEdge.rel }}</h3>
          <div class="text-xs text-text-2 mt-1 break-all">{{ selectedEdge.source }} → {{ selectedEdge.target }}</div>
        </div>

        <div v-else class="text-center text-text-2 text-sm py-12 px-4">
          <Box class="w-10 h-10 mx-auto mb-2 opacity-50" />
          <div>点击节点 / 边查看详情</div>
          <div class="mt-1 text-xs">详情面板会展示节点对应的真实原文片段</div>
        </div>
      </aside>
    </div>

    <!-- 节点编辑对话框 -->
    <div v-if="showEditNode" class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
         @click.self="showEditNode = false">
      <div class="industrial-card w-full max-w-md bg-card overflow-hidden">
        <header class="px-5 py-3 border-b border-border flex items-center gap-2">
          <Edit3 class="w-4 h-4 text-accent" />
          <span class="font-semibold flex-1">编辑节点</span>
        </header>
        <div class="p-5 space-y-3">
          <div>
            <div class="text-sm text-text-2 mb-1">名称</div>
            <input v-model="editNodeLabel"
                   class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent" />
          </div>
          <div>
            <div class="text-sm text-text-2 mb-1">描述（可选）</div>
            <textarea v-model="editNodeDesc" rows="3"
                      class="w-full px-3 py-2 rounded-btn border border-border bg-bg outline-none focus:border-accent text-sm"></textarea>
          </div>
        </div>
        <footer class="px-5 py-3 border-t border-border flex justify-end gap-2">
          <button class="h-9 px-4 rounded-btn border border-border" @click="showEditNode = false">取消</button>
          <button class="h-9 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold"
                  @click="submitEditNode">保存</button>
        </footer>
      </div>
    </div>

    <!-- 边编辑对话框 -->
    <div v-if="showEditEdge" class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
         @click.self="showEditEdge = false">
      <div class="industrial-card w-full max-w-md bg-card overflow-hidden">
        <header class="px-5 py-3 border-b border-border flex items-center gap-2">
          <Edit3 class="w-4 h-4 text-accent" />
          <span class="font-semibold flex-1">编辑关系</span>
        </header>
        <div class="p-5">
          <div class="text-sm text-text-2 mb-1">关系名</div>
          <input v-model="editEdgeRel"
                 class="w-full h-10 px-3 rounded-btn border border-border bg-bg outline-none focus:border-accent" />
        </div>
        <footer class="px-5 py-3 border-t border-border flex justify-end gap-2">
          <button class="h-9 px-4 rounded-btn border border-border" @click="showEditEdge = false">取消</button>
          <button class="h-9 px-5 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold"
                  @click="submitEditEdge">保存</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* FIX10+FIX11 v2：原文片段格式——结构化展示，标题/编号列表/bullet列表/元信息分层 */
.sn-panel { line-height: 1.6; }
.sn-body { font-size: 12px; }
.sn-line { color: var(--color-text-2); margin-bottom: 4px; }
.sn-h { font-weight: 600; color: var(--color-text); margin-top: 8px; margin-bottom: 4px; }
.sn-list { display: flex; align-items: baseline; }
.sn-dot { color: var(--color-accent); }
/* 编号项：徽章 + 名称 + 元信息 */
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
