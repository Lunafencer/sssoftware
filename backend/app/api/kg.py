"""
知识图谱 API（FIX4 第 3 项 / FIX6 第 6 项 / FIX6 第 8 项）

约束：
- 图谱必须基于已审核（status=ready/approved）的真实文档构建，禁止 mock。
- 节点附 doc_id / chunk_id，前端点击节点会调 /api/kb/{doc_id}/chunk/{chunk_id} 取真实文本。
- 实体抽取使用 **关键字+正则** 的轻量启发式（设备 / 部件 / 故障 / 维修方法），
  在演示环境无 LLM 调用成本，且可控。
- 边由"同一切片内共现"自动生成；同一关系对会按出现次数累计权重，超过阈值才落入图。
- FIX6 第 6 项：审查员 / 管理员可以对节点 label/desc 做修正、删除节点或边；
  改动持久化在 kg_overrides 表，在每次构图后叠加。
- FIX6 第 8 项：节点回填 source_docs（来源文档列表）+ 支持按文档筛选。
"""

from __future__ import annotations
import re
from typing import Iterable, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_current_user, require_auditor
from app.models import Document, KGOverride, User
from app.services.rag import _col  # 直接复用 Chroma 集合

router = APIRouter(tags=["kg"])

# ---------- 实体词典（按类型）----------
# 选词原则：常见中文设备检修语境下的高频名词；保持精炼，避免歧义
_DEVICE_WORDS = [
    "离心泵", "水泵", "电机", "异步电机", "同步电机", "齿轮箱", "减速机",
    "压缩机", "鼓风机", "风机", "变频器", "PLC", "传感器", "阀门",
    "锅炉", "换热器", "冷却塔", "管道", "液压站", "液压泵", "油泵",
]
_PART_WORDS = [
    "轴承", "齿轮", "轴", "联轴器", "机械密封", "密封圈", "O 形圈", "O型圈",
    "皮带", "叶轮", "蜗壳", "电磁阀", "继电器", "接触器", "保险丝",
    "导线", "电缆", "端子", "管路", "法兰", "螺栓", "螺母", "滤芯", "油封",
]
_FAULT_WORDS = [
    "异响", "振动", "振动超标", "过热", "过流", "过载", "短路", "断路",
    "漏油", "漏水", "渗漏", "泄漏", "卡死", "抱死", "磨损", "断裂", "腐蚀",
    "氧化", "锈蚀", "结垢", "堵塞", "压力波动", "压力过低", "压力过高",
    "电压不稳", "频率异常", "温度异常", "故障代码",
]
_METHOD_WORDS = [
    "更换", "拆卸", "清洗", "润滑", "加注", "紧固", "校准", "复位",
    "测试", "测量", "标定", "调试", "维护", "保养", "巡检", "校验",
    "充氮", "排气", "对中", "找正", "动平衡", "重启", "复电", "断电",
]

_CATEGORY_LABEL = {
    "device": "设备",
    "part":   "部件",
    "fault":  "故障",
    "method": "维修方法",
}


# FIX7 续 + FIX9：为图谱来源文档构造 hl 定位片段
# 核心原则：hl 必须以 keyword 开头、必须是文档原文中的自然子串（单行内截取，不跨行 space-join）
# 这样 Preview 页 locateInMarkdown 搜索 hl.slice(0,N) 时，短子串也从 keyword 开始，
# 能精准命中关键词本身，而非 keyword 前 40 字上下文（上下文在 markdown 渲染后因换行而断裂）
_STOP_TOKENS = {"[图片文件]", "uploads", "extracted_images"}


def _build_kg_snippet(text: str, keyword: str, max_len: int = 120) -> str:
    """返回包含 keyword 的那行原文，从 keyword 位置截取（keyword 在 hl 开头），不跨行 space-join。

    这样 hl 是文档原文中的自然连续子串，Preview 页 locateInMarkdown 能在 markdown 渲染结果里找到。
    """
    if not text or not keyword:
        return ""
    # 找包含 keyword 的行（保留原文格式，不做 space-join）
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("[图片文件]"):
            continue
        if "uploads" in s or "extracted_images" in s:
            continue
        if re.search(r"page-\d{3}-image-\d{2}\.(png|jpg|jpeg|webp)", s, re.I):
            continue
        idx = s.find(keyword)
        if idx >= 0:
            # 从 keyword 位置截取，keyword 在 hl 开头
            return s[idx:idx + max_len]
    # keyword 不在任何单行内 → fallback：取第一行非空内容
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith("[图片文件]") and "uploads" not in s and "extracted_images" not in s:
            if re.search(r"page-\d{3}-image-\d{2}\.(png|jpg|jpeg|webp)", s, re.I):
                continue
            return s[:max_len]
    return ""


def _build_pattern(words: Iterable[str]) -> re.Pattern:
    # 直接 OR；中文无需 \b 边界
    parts = sorted({w for w in words if w}, key=len, reverse=True)
    return re.compile("|".join(re.escape(w) for w in parts))


_PATTERNS = {
    "device": _build_pattern(_DEVICE_WORDS),
    "part":   _build_pattern(_PART_WORDS),
    "fault":  _build_pattern(_FAULT_WORDS),
    "method": _build_pattern(_METHOD_WORDS),
}

# 同一切片内出现两两实体即建边；权重 < 阈值则丢弃，避免噪声
_EDGE_MIN_WEIGHT = 1
_MAX_NODES = 200  # 兜底裁剪


def _extract_entities(text: str) -> dict[str, set[str]]:
    """从一段文本中按类别抽取实体短语。返回 {category: {entity, ...}}"""
    out: dict[str, set[str]] = {}
    for cat, pat in _PATTERNS.items():
        out[cat] = set(pat.findall(text or ""))
    return out


def _rel_label(a_cat: str, b_cat: str) -> str:
    """根据两端类别给一个语义化的关系名"""
    pair = frozenset([a_cat, b_cat])
    if pair == frozenset(["device", "part"]):   return "包含"
    if pair == frozenset(["device", "fault"]):  return "故障"
    if pair == frozenset(["part", "fault"]):    return "故障"
    if pair == frozenset(["fault", "method"]):  return "处置"
    if pair == frozenset(["device", "method"]): return "操作"
    if pair == frozenset(["part", "method"]):   return "操作"
    return "相关"


def _query_doc_chunks(doc_id: int, limit: int = 200):
    """
    从 Chroma 拉指定 doc_id 的全部切片。
    chromadb get(where={...}) 返回 ids/documents/metadatas 三个数组。
    """
    try:
        res = _col.get(where={"doc_id": doc_id}, limit=limit)
    except Exception:
        return []
    ids = res.get("ids") or []
    docs = res.get("documents") or []
    metas = res.get("metadatas") or []
    rows = []
    for i in range(len(ids)):
        rows.append({
            "id": ids[i],
            "content": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
        })
    return rows


def _approved_doc_ids(db: Session, requested: list[int]) -> list[int]:
    """只返回数据库里已存在并被视为可见的 doc_id（status in ready/approved）"""
    if not requested:
        return []
    docs = db.query(Document).filter(Document.id.in_(requested)).all()
    out = []
    for d in docs:
        # 兼容两种 schema：旧版用 ready，FIX3 后切到 approved
        if d.status in ("ready", "approved"):
            out.append(d.id)
    return out


def _load_overrides(db: Session):
    """加载所有图谱编辑覆盖：返回 {target_id: {op, payload}} 和 deleted_target_ids 集合。"""
    rows = db.query(KGOverride).all()
    node_updates: dict[str, dict] = {}
    deleted_nodes: set[str] = set()
    edge_updates: dict[str, dict] = {}
    deleted_edges: set[tuple[str, str]] = set()
    for r in rows:
        if r.kind == "node":
            if r.op == "delete":
                deleted_nodes.add(r.target_id)
            elif r.op == "update" and r.payload:
                node_updates[r.target_id] = r.payload
        elif r.kind == "edge":
            if r.op == "delete":
                a, b = r.target_id.split("|", 1)
                deleted_edges.add((a, b))
            elif r.op == "update" and r.payload:
                edge_updates[r.target_id] = r.payload
    return node_updates, deleted_nodes, edge_updates, deleted_edges


@router.get("/api/kg/graph")
def get_graph(
    doc_ids: str = Query("", description="逗号分隔的已审 doc_id 列表"),
    filter_doc_id: Optional[int] = Query(None, description="FIX6 第 8 项：按文档筛选"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    GET /api/kg/graph?doc_ids=1,2,3&filter_doc_id=5
    返回基于已审文档的 { nodes, edges }。
    无文档 / 无实体时返回空图。
    FIX6 第 8 项：节点回填 source_docs（来源文档列表）。
    FIX6 第 6 项：叠加人工编辑覆盖层。
    """
    raw_ids: list[int] = []
    for s in (doc_ids or "").split(","):
        s = s.strip()
        if not s:
            continue
        try:
            raw_ids.append(int(s))
        except ValueError:
            continue
    if not raw_ids:
        return {"nodes": [], "edges": []}

    valid_ids = _approved_doc_ids(db, raw_ids)
    if not valid_ids:
        return {"nodes": [], "edges": []}

    node_overrides, deleted_nodes, edge_overrides, deleted_edges = _load_overrides(db)

    # node_id 用 "{cat}:{label}"，保证跨文档同名实体合并
    node_meta: dict[str, dict] = {}        # node_id -> { label, type, docId, chunkId, weight, sourceDocs }
    pair_count: dict[tuple[str, str], dict] = {}  # (a,b) -> { rel, weight }

    for did in valid_ids:
        chunks = _query_doc_chunks(did)
        for ch in chunks:
            ents_by_cat = _extract_entities(ch["content"])
            flat: list[tuple[str, str]] = []
            for cat, names in ents_by_cat.items():
                for n in names:
                    flat.append((cat, n))
            # 注册节点 + 跟踪来源文档（chunk_id / page / 文本片段）
            meta = ch.get("metadata") or {}
            chunk_info = {"chunk_id": ch["id"], "page": meta.get("page"), "text": (ch["content"] or "")[:800]}
            for cat, name in flat:
                nid = f"{cat}:{name}"
                if nid not in node_meta:
                    node_meta[nid] = {
                        "id": nid,
                        "label": name,
                        "type": cat,
                        "docId": str(did),
                        "chunkId": ch["id"],
                        "weight": 1,
                        "sourceDocs": {did: chunk_info},
                    }
                else:
                    node_meta[nid]["weight"] += 1
                    node_meta[nid]["sourceDocs"].setdefault(did, chunk_info)
            # 共现成边
            seen_pair: set[tuple[str, str]] = set()
            for i in range(len(flat)):
                for j in range(i + 1, len(flat)):
                    a = f"{flat[i][0]}:{flat[i][1]}"
                    b = f"{flat[j][0]}:{flat[j][1]}"
                    if a == b:
                        continue
                    key = (a, b) if a < b else (b, a)
                    if key in seen_pair:
                        continue
                    seen_pair.add(key)
                    rec = pair_count.setdefault(key, {
                        "rel": _rel_label(flat[i][0], flat[j][0]),
                        "weight": 0,
                    })
                    rec["weight"] += 1

    # 应用人工编辑覆盖（FIX6 第 6 项）
    for nid, p in node_overrides.items():
        if nid in node_meta:
            if "label" in p:
                node_meta[nid]["label"] = p["label"]
            if "desc" in p:
                node_meta[nid]["desc"] = p["desc"]

    # 节点裁剪 + 排序
    nodes = sorted(
        [n for n in node_meta.values() if n["id"] not in deleted_nodes],
        key=lambda x: -x["weight"]
    )[:_MAX_NODES]
    keep_ids = {n["id"] for n in nodes}

    edges = []
    for (a, b), rec in pair_count.items():
        if rec["weight"] < _EDGE_MIN_WEIGHT:
            continue
        if a not in keep_ids or b not in keep_ids:
            continue
        if (a, b) in deleted_edges or (b, a) in deleted_edges:
            continue
        edge_key = f"{a}|{b}" if a < b else f"{b}|{a}"
        rel = rec["rel"]
        if edge_key in edge_overrides and "rel" in edge_overrides[edge_key]:
            rel = edge_overrides[edge_key]["rel"]
        edges.append({
            "source": a,
            "target": b,
            "rel": rel,
            "weight": rec["weight"],
        })

    # FIX6 第 8 项：按文档筛选
    if filter_doc_id is not None:
        keep_ids = {n["id"] for n in nodes if filter_doc_id in n.get("sourceDocs", {})}
        nodes = [n for n in nodes if n["id"] in keep_ids]
        edges = [e for e in edges if e["source"] in keep_ids and e["target"] in keep_ids]

    # FIX6 第 8 项：构建 source_docs 列表；FIX7 续：附带 chunk_id/page/hl 用于精准跳转
    all_doc_ids = set()
    for n in nodes:
        all_doc_ids.update(n.get("sourceDocs", {}).keys())
    if all_doc_ids:
        doc_map = {}
        for d in db.query(Document).filter(Document.id.in_(list(all_doc_ids))).all():
            doc_map[d.id] = {"id": d.id, "title": d.title, "doc_type": d.type or "unknown"}
        for n in nodes:
            source_docs = []
            for did, info in sorted(n.get("sourceDocs", {}).items()):
                if did not in doc_map:
                    continue
                doc = doc_map[did]
                hl = _build_kg_snippet(info.get("text", ""), n["label"])
                source_docs.append({
                    "id": doc["id"],
                    "title": doc["title"],
                    "doc_type": doc["doc_type"],
                    "chunk_id": info.get("chunk_id"),
                    "page": info.get("page"),
                    "hl": hl,
                })
            n["source_docs"] = source_docs
            # 移除内部集合，不暴露给前端
            n.pop("sourceDocs", None)

    return {"nodes": nodes, "edges": edges}


# ==================== FIX6 第 6 项：图谱节点/边人工编辑端点 ====================

class NodeUpdateIn(BaseModel):
    label: Optional[str] = None
    desc: Optional[str] = None


class EdgeUpdateIn(BaseModel):
    rel: Optional[str] = None


@router.put("/api/kg/node/{node_id}")
def update_node(node_id: str, body: NodeUpdateIn, db: Session = Depends(get_db),
                user: User = Depends(require_auditor)):
    """修改节点 label / 描述。只存储覆盖层，不修改原始 chunk。"""
    payload = {}
    if body.label is not None:
        payload["label"] = body.label.strip()
    if body.desc is not None:
        payload["desc"] = body.desc.strip()
    if not payload:
        raise HTTPException(400, "至少提供 label 或 desc")
    # Upsert
    existing = db.query(KGOverride).filter(
        KGOverride.kind == "node", KGOverride.target_id == node_id, KGOverride.op == "update"
    ).first()
    if existing:
        existing.payload = {**existing.payload, **payload} if existing.payload else payload
        existing.operator_id = user.id
    else:
        db.add(KGOverride(kind="node", target_id=node_id, op="update", payload=payload, operator_id=user.id))
    db.commit()
    return {"ok": True}


@router.delete("/api/kg/node/{node_id}")
def delete_node(node_id: str, db: Session = Depends(get_db),
                user: User = Depends(require_auditor)):
    """标记删除节点（从图谱中移除，原始 chunk 不受影响）。"""
    existing = db.query(KGOverride).filter(
        KGOverride.kind == "node", KGOverride.target_id == node_id, KGOverride.op == "delete"
    ).first()
    if not existing:
        db.add(KGOverride(kind="node", target_id=node_id, op="delete", payload=None, operator_id=user.id))
    db.commit()
    return {"ok": True}


@router.put("/api/kg/edge/{edge_id}")
def update_edge(edge_id: str, body: EdgeUpdateIn, db: Session = Depends(get_db),
                user: User = Depends(require_auditor)):
    """修改边的关系名。"""
    if not (body.rel or "").strip():
        raise HTTPException(400, "rel 不能为空")
    existing = db.query(KGOverride).filter(
        KGOverride.kind == "edge", KGOverride.target_id == edge_id, KGOverride.op == "update"
    ).first()
    if existing:
        existing.payload = {"rel": body.rel.strip()}
        existing.operator_id = user.id
    else:
        db.add(KGOverride(kind="edge", target_id=edge_id, op="update",
                         payload={"rel": body.rel.strip()}, operator_id=user.id))
    db.commit()
    return {"ok": True}


@router.delete("/api/kg/edge/{edge_id}")
def delete_edge(edge_id: str, db: Session = Depends(get_db),
                user: User = Depends(require_auditor)):
    """标记删除边。"""
    existing = db.query(KGOverride).filter(
        KGOverride.kind == "edge", KGOverride.target_id == edge_id, KGOverride.op == "delete"
    ).first()
    if not existing:
        db.add(KGOverride(kind="edge", target_id=edge_id, op="delete", payload=None, operator_id=user.id))
    db.commit()
    return {"ok": True}


@router.get("/api/kb/{doc_id}/chunk/{chunk_id}")
def get_chunk(
    doc_id: str,
    chunk_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    GET /api/kb/{doc_id}/chunk/{chunk_id}
    取节点对应的原文切片（FIX4 第 3 项 / FIX3 第 5.2 项联动）。
    """
    try:
        d_id = int(doc_id)
    except ValueError:
        raise HTTPException(400, "doc_id 必须为整数")

    doc = db.query(Document).get(d_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    try:
        res = _col.get(ids=[chunk_id])
    except Exception as e:
        raise HTTPException(500, f"知识库不可用：{e}")

    ids = res.get("ids") or []
    if not ids:
        raise HTTPException(404, "切片不存在")

    docs = res.get("documents") or []
    metas = res.get("metadatas") or []
    text = docs[0] if docs else ""
    meta = metas[0] if metas else {}

    return {
        "docId": str(d_id),
        "chunkId": chunk_id,
        "text": text,
        "title": meta.get("title") or doc.title,
        "page": meta.get("page"),
    }
