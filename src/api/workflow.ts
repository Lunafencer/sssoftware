import { rawCall, request } from './request'
import {
  listTickets, getTicket, completeTicket, updateProgress,
  type TicketSummary, type TicketDetail, type TicketStatus
} from './ticket'

export interface ToolItem {
  name: string
  spec?: string
  qty: number
  imageUrl?: string
}

/** 子步骤（FIX4 第 2 项） */
export interface SubStep {
  id: string
  content: string
}

export interface SopStep {
  id: string
  index?: number
  name: string
  desc: string
  estMinutes: number
  hazardous?: boolean
  safetyNote?: string
  tools?: string[]
  toolItems?: ToolItem[]
  materials?: string[]
  manualRef?: string
  acceptance?: string
  checkPoints: string[]
  subSteps?: SubStep[]
}

export interface SopFlow {
  id: string
  name: string
  deviceModel: string
  level: 1 | 2 | 3
  steps: SopStep[]
  // FIX7 续：后端权威的进度状态——避免 localStorage 跨工单/跨实例污染
  stepDone?: string[]
  status?: 'open' | 'doing' | 'done' | 'deleted'
}

export type WorkItemStatus = '待办' | '已完成'

export interface WorkItem {
  id: string                 // 形如 't-12'
  ticketId: number
  name: string
  deviceModel: string
  difficulty: '初级' | '中级' | '高级'
  estimatedMinutes: number
  status: WorkItemStatus
  level: 1 | 2 | 3
  hazardous?: boolean
  updatedAt: number
  workshop?: string
  // FIX5：共享/推荐 + 进度
  added: boolean
  isCreator: boolean
  creator?: string | null
  totalSteps: number
  doneSteps: number
}

function ticketToWorkItem(t: TicketSummary): WorkItem {
  return {
    id: 't-' + t.id,
    ticketId: t.id,
    name: t.fault || `工单 #${t.id}`,
    deviceModel: t.device || '未指定',
    difficulty: '中级',
    estimatedMinutes: 60,
    status: t.status === 'done' ? '已完成' : '待办',
    level: 2,
    updatedAt: Date.now(),
    workshop: t.creator ? `创建人 · ${t.creator}` : 'AI 工单',
    added: t.added,
    isCreator: t.isCreator,
    creator: t.creator,
    totalSteps: t.totalSteps,
    doneSteps: t.doneSteps
  }
}

const SECTION_HEADERS = ['风险预检', '工具准备', '检修步骤', '验收标准']

function parseTicketSteps(raw: unknown): SopStep[] {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw.map((s: any, i: number) => {
      const rawSubs = s.subSteps || s.sub_steps || s.substeps
      const subSteps: SubStep[] | undefined = Array.isArray(rawSubs) && rawSubs.length
        ? rawSubs.map((ss: any, j: number) => ({
            id: String(ss.id || `sub-${i + 1}-${j + 1}`),
            content: String(ss.content || ss.text || ss.title || ss.desc || ss.description || ss)
          })).filter((ss: SubStep) => ss.content && ss.content !== 'undefined')
        : undefined
      return {
        id: String(s.id || 's' + (i + 1)),
        index: i + 1,
        name: s.name || s.title || SECTION_HEADERS[i] || `步骤 ${i + 1}`,
        desc: typeof s === 'string' ? s : (s.desc || s.description || s.content || ''),
        estMinutes: Number(s.estMinutes || s.minutes || 15),
        hazardous: s.hazardous,
        safetyNote: s.safetyNote || s.safety_note,
        tools: s.tools || [],
        toolItems: s.toolItems || s.tool_items,
        materials: s.materials || [],
        manualRef: s.manualRef || s.ref,
        acceptance: s.acceptance,
        checkPoints: s.checkPoints || s.checks || [],
        subSteps
      }
    })
  }

  if (typeof raw === 'string') {
    const trimmed = raw.trim()
    try {
      const parsed = JSON.parse(trimmed)
      if (Array.isArray(parsed)) return parseTicketSteps(parsed)
    } catch { /* not JSON */ }

    const segments: { name: string; body: string }[] = []
    const headerRe = new RegExp(`(?:【|\\[|\\d+[\\.、])?\\s*(${SECTION_HEADERS.join('|')})\\s*(?:】|\\])?[:：\\s]*`, 'g')
    let lastIdx = 0
    let lastName = ''
    let m: RegExpExecArray | null
    while ((m = headerRe.exec(trimmed))) {
      if (lastName) segments.push({ name: lastName, body: trimmed.slice(lastIdx, m.index).trim() })
      lastName = m[1]
      lastIdx = headerRe.lastIndex
    }
    if (lastName) segments.push({ name: lastName, body: trimmed.slice(lastIdx).trim() })

    if (segments.length) {
      return segments.map((seg, i) => ({
        id: 's' + (i + 1),
        index: i + 1,
        name: seg.name,
        desc: seg.body || '（暂无内容）',
        estMinutes: 15,
        hazardous: seg.name === '风险预检',
        tools: [],
        materials: [],
        checkPoints: seg.body
          .split(/\n|[；;]/)
          .map(s => s.replace(/^[\s\-•·\d\.、]+/, '').trim())
          .filter(s => s.length >= 4)
          .slice(0, 5)
      }))
    }

    return [{
      id: 's1', index: 1, name: 'AI 生成的检修方案',
      desc: trimmed, estMinutes: 30,
      tools: [], materials: [],
      checkPoints: ['人工复核 AI 输出', '按方案完成检修', '记录处理结果']
    }]
  }

  if (typeof raw === 'object') {
    const r = raw as any
    if (typeof r.raw === 'string') return parseTicketSteps(r.raw)
    if (Array.isArray(r.steps)) return parseTicketSteps(r.steps)
  }
  return []
}

function ticketToFlow(t: TicketDetail): SopFlow {
  return {
    id: 't-' + t.id,
    name: t.fault || `工单 #${t.id}`,
    deviceModel: t.device || '未指定',
    level: 2,
    steps: parseTicketSteps(t.steps),
    // FIX7 续：后端进度作为唯一权威源（之前丢弃 progress 导致 localStorage 污染显示"全部完成"）
    stepDone: (t.progress?.stepDone || []).map(String),
    status: t.progress?.status || 'open',
  }
}

/** 列表：我的工单 + 推荐工单（其他人创建、我未添加） */
export interface FlowsResult {
  mine: WorkItem[]
  recommended: WorkItem[]
}

export const listFlows = async (): Promise<FlowsResult> => {
  const { mine, recommended } = await listTickets()
  return {
    mine: (mine || []).map(ticketToWorkItem),
    recommended: (recommended || []).map(ticketToWorkItem)
  }
}

/** 详情：仅支持真实工单（t- 前缀）。失败时抛错由 UI 处理。 */
export const getFlow = async (id?: string): Promise<SopFlow> => {
  if (!id || !id.startsWith('t-')) throw new Error('无效的工单编号')
  const tid = id.slice(2)
  const detail = await getTicket(tid)
  return ticketToFlow(detail)
}

/** 同步步骤完成进度到后端（按用户维度） */
export const syncStepProgress = (id: string, stepDone: string[]) => {
  const tid = id.startsWith('t-') ? id.slice(2) : id
  return updateProgress(tid, { stepDone })
}

export interface ManualRef {
  docId: string
  title: string
  matchedSection?: string
  score: number
}

export const getWorkflowTools = async (id: string): Promise<ToolItem[]> => {
  if (!id || !id.startsWith('t-')) return []
  const tid = id.slice(2)
  return rawCall<ToolItem[]>(() => request.get<ToolItem[]>(`/workflow/${tid}/tools`))
}

export const getWorkflowManuals = async (id: string): Promise<ManualRef[]> => {
  if (!id || !id.startsWith('t-')) return []
  const tid = id.slice(2)
  return rawCall<ManualRef[]>(() => request.get<ManualRef[]>(`/workflow/${tid}/manuals`))
}

export { createTicket, completeTicket, type TicketStatus } from './ticket'
