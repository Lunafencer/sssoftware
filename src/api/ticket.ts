import { request, rawCall } from './request'

/** 用户维度的工单状态 */
export type TicketStatus = 'open' | 'doing' | 'done' | 'deleted'

/** 列表项 / 摘要（含当前用户的进度） */
export interface TicketSummary {
  id: number
  device: string
  fault: string
  creatorId?: number
  creator?: string | null
  isCreator: boolean
  added: boolean
  status: TicketStatus
  totalSteps: number
  doneSteps: number
  createdAt?: string | null
  addedAt?: string | null
  completedAt?: string | null
  score?: number
}

/** 历史工单记录 */
export interface TicketHistoryItem extends TicketSummary {
  deletedAt?: string | null
  deleteReason?: string | null
}

/** 工单详情 */
export interface TicketDetail {
  id: number
  device: string
  fault: string
  steps: { raw: string } | Record<string, unknown> | unknown[] | null
  created_at: string | null
  creator?: string | null
  isCreator: boolean
  added: boolean
  progress: {
    status: TicketStatus
    stepDone: string[]
    addedAt?: string | null
    completedAt?: string | null
  }
}

export interface TicketCreateResult {
  id: number
  steps: { raw: string } | Record<string, unknown> | unknown[] | null
}

export interface TicketListResult {
  mine: TicketSummary[]
  recommended: TicketSummary[]
}

/** 时间线事件 */
export interface TicketEvent {
  type: 'created' | 'added' | 'step_completed' | 'completed' | 'deleted' | string
  // FIX6 第 4 项：扩展事件 detail 字段，覆盖后端 _add_event 的所有附加信息
  detail?: {
    stepId?: string
    stepIndex?: number | null
    reason?: string
    from?: string
    [k: string]: any
  } | null
  at: string | null
}
export interface TimelineResult {
  /** FIX7 续：后端明示当前视角 —— audit=审查员/管理员（grouped），self=员工（events） */
  viewer?: 'audit' | 'self'
  creator?: string | null
  creatorId?: number | null
  events?: TicketEvent[]
  grouped?: { userId: number; user: string | null; events: TicketEvent[] }[]
}

export const createTicket = (body: { device: string; fault: string }) =>
  rawCall<TicketCreateResult>(() =>
    request.post<TicketCreateResult>('/ticket', body, { timeout: 60_000 }))

/** 列表：{ mine, recommended } */
export const listTickets = () =>
  rawCall<TicketListResult>(() => request.get<TicketListResult>('/ticket'))

/** 创建前的相似工单推荐 */
export const recommendTickets = (body: { device: string; fault: string }) =>
  rawCall<TicketSummary[]>(() => request.post<TicketSummary[]>('/ticket/recommend', body))

/** 历史工单（已完成 / 已删除） */
export const listTicketHistory = () =>
  rawCall<TicketHistoryItem[]>(() => request.get<TicketHistoryItem[]>('/ticket/history'))

/** 把他人工单添加到我的作业指引 */
export const addTicketToMine = (id: number | string) =>
  rawCall<{ ok: boolean; id: number }>(() => request.post(`/ticket/${id}/add`, {}))

export const getTicket = (id: number | string) =>
  rawCall<TicketDetail>(() => request.get<TicketDetail>(`/ticket/${id}`))

/** 更新我的进度（步骤完成 / 状态） */
export const updateProgress = (id: number | string, body: { stepDone?: string[]; status?: TicketStatus }) =>
  rawCall<{ ok: boolean; status: TicketStatus }>(() =>
    request.patch(`/ticket/${id}/progress`, body))

/** 完成工单 */
export const completeTicket = (id: number | string) => updateProgress(id, { status: 'done' })

/** 兼容旧调用 */
export const updateTicketStatus = (id: number | string, status: TicketStatus) =>
  updateProgress(id, { status })

/**
 * 删除我的工单：
 * - 已完成：无需理由（后端默认"已完成"）
 * - 未完成：必须传 reason
 */
export const deleteTicket = (id: number | string, reason?: string) =>
  rawCall<{ ok: boolean }>(() =>
    request.delete(`/ticket/${id}`, { data: reason ? { reason } : {} }))

/** 工单时间线 */
export const getTimeline = (id: number | string) =>
  rawCall<TimelineResult>(() => request.get<TimelineResult>(`/ticket/${id}/timeline`))
