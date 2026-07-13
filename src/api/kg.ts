import { request, rawCall } from './request'
import { listDocs, isApprovedStatus } from './kb'

/**
 * 知识图谱（基于已审通过的真实文档，无 mock）
 * FIX6 第 8 项：节点增加 source_docs 字段
 * FIX6 第 6 项：审核员/管理员可编辑节点/边
 */
export type KGType = 'device' | 'part' | 'fault' | 'method' | 'case' | 'manual'

export interface KGNode {
  id: string
  label: string
  type: KGType
  weight: number
  desc?: string
  status?: string
  manualRef?: string
  docId?: string
  chunkId?: string
  // FIX6 第 8 项：来源文档列表
  source_docs?: { id: number; title: string; doc_type: string; chunk_id?: string; page?: number; hl?: string }[]
}
export interface KGEdge { source: string; target: string; rel: string }
export interface KGGraph { nodes: KGNode[]; edges: KGEdge[] }

const EMPTY_GRAPH: KGGraph = { nodes: [], edges: [] }

/**
 * 拉取图谱：把已审通过的 doc_ids 传给后端。
 * 缺省入参时自动取 status=approved/ready 的文档；无文档则返回空图（不触发请求）。
 */
export const getGraph = async (docIds?: string[], filterDocId?: number): Promise<KGGraph> => {
  let ids = docIds
  if (!ids) {
    const docs = await listDocs()
    ids = docs.filter(d => isApprovedStatus(d.status)).map(d => String(d.id))
  }
  if (!ids.length) return EMPTY_GRAPH
  return rawCall<KGGraph>(() =>
    request.get<KGGraph>('/kg/graph', {
      params: {
        doc_ids: ids!.join(','),
        filter_doc_id: filterDocId || undefined
      }
    }))
}

/** 节点对应原文片段 GET /api/kb/{docId}/chunk/{chunkId} */
export interface ChunkContent {
  docId: string
  chunkId: string
  text: string
  page?: number
  title?: string
}
export const getChunk = (docId: string, chunkId: string) =>
  rawCall<ChunkContent>(() => request.get<ChunkContent>(`/kb/${docId}/chunk/${chunkId}`))

// ---- FIX6 第 6 项：图谱编辑 ----

/** 更新节点 label/desc */
export const updateNode = (nodeId: string, body: { label?: string; desc?: string }) =>
  rawCall<{ ok: boolean }>(() => request.put<{ ok: boolean }>(`/kg/node/${encodeURIComponent(nodeId)}`, body))

/** 删除节点 */
export const deleteNode = (nodeId: string) =>
  rawCall<{ ok: boolean }>(() => request.delete<{ ok: boolean }>(`/kg/node/${encodeURIComponent(nodeId)}`))

/** 更新边关系 */
export const updateEdge = (edgeId: string, body: { rel: string }) =>
  rawCall<{ ok: boolean }>(() => request.put<{ ok: boolean }>(`/kg/edge/${encodeURIComponent(edgeId)}`, body))

/** 删除边 */
export const deleteEdge = (edgeId: string) =>
  rawCall<{ ok: boolean }>(() => request.delete<{ ok: boolean }>(`/kg/edge/${encodeURIComponent(edgeId)}`))