from typing import Optional, List
from datetime import datetime
from difflib import SequenceMatcher
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import get_current_user, _is_auditor
from app.models import Ticket, UserTicketProgress, TicketEvent, User
from app.services.llm import chat_text
from app.services.rag import search
import json, re

router = APIRouter(prefix="/api/ticket", tags=["ticket"])


class TicketStatusIn(BaseModel):
    status: str


class TicketIn(BaseModel):
    device: str
    fault: str


class ProgressIn(BaseModel):
    stepDone: Optional[List[str]] = None
    status: Optional[str] = None


class DeleteIn(BaseModel):
    reason: Optional[str] = None


class RecommendIn(BaseModel):
    device: str = ""
    fault: str = ""


# FIX4 第 2 项：返回大步骤+子步骤的结构化 JSON
SOP_SYSTEM = (
    "你是设备检修标准作业流程（SOP）专家。必须严格、只依据用户提供的【相关手册】生成工单。"
    "不得使用训练记忆或常识编造手册中没有的工具、参数、拆装步骤、验收标准。"
    "若手册依据不足，必须在对应步骤 description 或 safetyNote 中写明：手册依据不足，需要补充具体章节/参数。"
    "请按【风险预检 → 工具准备 → 检修步骤 → 验收标准】四段输出，"
    "每个大步骤可以含若干必须按顺序完成的子步骤；同时给出该步骤需要的工具清单。"
    "严格输出 **JSON 数组**（不要包含 markdown ``` 代码块包裹），每个元素如下：\n"
    "{\n"
    "  \"id\": \"step-1\",\n"
    "  \"title\": \"风险预检\",\n"
    "  \"description\": \"在开始拆卸之前完成的安全预检步骤的简介\",\n"
    "  \"safetyNote\": \"涉及电气、压力或腐蚀介质时的安全提醒（可选）\",\n"
    "  \"subSteps\": [\n"
    "    { \"id\": \"sub-1-1\", \"content\": \"具体子步骤 1（必须按顺序完成）\" },\n"
    "    { \"id\": \"sub-1-2\", \"content\": \"具体子步骤 2\" }\n"
    "  ],\n"
    "  \"tools\": [\"验电器\", \"挂牌锁具\"],\n"
    "  \"acceptance\": \"验收标准（仅最后一段需要，可选）\"\n"
    "}\n"
    "约束：\n"
    "1) JSON 必须是合法的、可被 json.loads 解析；不要在外层加任何说明文字或代码块标记；\n"
    "2) 至少返回 3 个大步骤；每个大步骤至少 2 个子步骤；\n"
    "3) tools 字段使用名词短语，只能来自手册或由手册明确支持；\n"
    "4) 每个关键子步骤末尾用（依据：[1]）形式标明来源编号；\n"
    "5) 一律使用中文。"
)


def _parse_steps(raw: str):
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    lb = s.find("[")
    rb = s.rfind("]")
    if lb >= 0 and rb > lb:
        s = s[lb: rb + 1]
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return data
    except Exception:
        return None
    return None


def _step_ids(t: Ticket) -> List[str]:
    steps = t.steps if isinstance(t.steps, list) else []
    return [str(s.get("id")) for s in steps if isinstance(s, dict) and s.get("id")]


def _add_event(db: Session, ticket_id: int, user_id: int, type_: str, detail=None):
    db.add(TicketEvent(ticket_id=ticket_id, user_id=user_id, type=type_, detail=detail))


def _progress(db: Session, ticket_id: int, user_id: int) -> Optional[UserTicketProgress]:
    return db.query(UserTicketProgress).filter(
        UserTicketProgress.ticket_id == ticket_id,
        UserTicketProgress.user_id == user_id,
    ).first()


def _creator_name_map(db: Session, tickets) -> dict:
    ids = {t.creator_id for t in tickets if t.creator_id}
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: u.username for u in rows}


def _summary(t: Ticket, prog: Optional[UserTicketProgress], creator_name: Optional[str]) -> dict:
    total = len(_step_ids(t))
    done = len(prog.step_done or []) if prog and isinstance(prog.step_done, list) else 0
    return {
        "id": t.id,
        "device": t.device,
        "fault": t.fault,
        "creatorId": t.creator_id,
        "creator": creator_name,
        "isCreator": bool(prog and prog.is_creator),
        "added": bool(prog and prog.status != "deleted"),
        "status": (prog.status if prog else "open"),
        "totalSteps": total,
        "doneSteps": done,
        "createdAt": t.created_at.isoformat() if t.created_at else None,
        "addedAt": prog.added_at.isoformat() if prog and prog.added_at else None,
        "completedAt": prog.completed_at.isoformat() if prog and prog.completed_at else None,
    }


def _build_manual_context(device: str, fault: str, k: int = 5) -> tuple[str, list[dict]]:
    """工单生成前先检索手册，禁止脱离知识库自由生成。"""
    query = f"{device} {fault}".strip()
    if not query:
        return "", []
    hits = search(query, k=k)
    context = "\n\n".join(
        f"[{i + 1}] {h['metadata'].get('title', '')}: {h['content']}"
        for i, h in enumerate(hits)
    )
    return context, hits


@router.post("")
def create(body: TicketIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    manual_context, manual_hits = _build_manual_context(body.device, body.fault, k=5)
    if not manual_hits:
        fallback_steps = [
            {
                "id": "step-1",
                "title": "手册依据不足",
                "description": "知识库未检索到与该设备/故障匹配的操作手册，不能可靠生成标准化检修方案。",
                "safetyNote": "请先上传或审核通过对应设备手册、故障代码表、维修步骤和验收参数后再生成工单。",
                "subSteps": [
                    {"id": "sub-1-1", "content": "补充对应设备型号、故障现象、维修章节或参数表。"},
                    {"id": "sub-1-2", "content": "由审查员审核手册入库后重新创建工单。"},
                ],
                "tools": [],
                "acceptance": "手册入库并能被知识库检索到后再生成可执行步骤。",
            }
        ]
        t = Ticket(device=body.device, fault=body.fault, steps=fallback_steps, creator_id=user.id)
        db.add(t); db.commit(); db.refresh(t)
        prog = UserTicketProgress(user_id=user.id, ticket_id=t.id, status="open",
                                  step_done=[], is_creator=True)
        db.add(prog)
        _add_event(db, t.id, user.id, "created", {"warning": "manual_context_empty"})
        db.commit()
        return {"id": t.id, "steps": t.steps, "manuals": []}

    prompt = (
        f"【相关手册】\n{manual_context}\n\n"
        f"【设备】\n{body.device}\n"
        f"【故障描述】\n{body.fault}\n\n"
        "请只依据【相关手册】生成标准化检修方案；按系统要求返回 JSON 数组。"
    )
    # FIX(健壮)：DashScope 异常时 chat_text 抛 RuntimeError，转 502 避免堆栈泄露
    try:
        raw = chat_text(SOP_SYSTEM, prompt, temperature=0.1, top_p=0.7)
    except Exception as e:
        raise HTTPException(502, f"AI 服务暂时不可用，无法生成检修方案：{e}")
    parsed = _parse_steps(raw)
    steps = parsed if parsed is not None else {"raw": raw}
    t = Ticket(device=body.device, fault=body.fault, steps=steps, creator_id=user.id)
    db.add(t); db.commit(); db.refresh(t)
    prog = UserTicketProgress(user_id=user.id, ticket_id=t.id, status="open",
                              step_done=[], is_creator=True)
    db.add(prog)
    _add_event(db, t.id, user.id, "created", {
        "manual_doc_ids": [h.get("metadata", {}).get("doc_id") for h in manual_hits]
    })
    db.commit()
    return {"id": t.id, "steps": t.steps, "manuals": _list_manuals_for(t)}


@router.get("")
def list_(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """返回 { mine, recommended }：
    - mine：我当前正在参与（progress.status != deleted）的工单。
    - recommended：
      * 一线员工：仅"我未参与/已删除"的工单（保持作业指引推荐语义）；
      * 审查员/管理员（FIX7 续）：列出**平台上的全部工单**——他们的职责是
        审核与抽查，需要不"添加到我的工单"就能查看任意工单的时间线，
        因此除了 mine 里的进度外，全部工单也回填到 recommended 列表。
    FIX6 第 3 项：用户软删除仅当前用户视图隐藏，工单仍为平台公共资源。
    """
    tickets = db.query(Ticket).order_by(Ticket.id.desc()).all()
    names = _creator_name_map(db, tickets)
    my_progs = {p.ticket_id: p for p in db.query(UserTicketProgress).filter(
        UserTicketProgress.user_id == user.id).all()}
    is_audit = _is_auditor(user.role)
    mine, recommended = [], []
    for t in tickets:
        prog = my_progs.get(t.id)
        if prog and prog.status != "deleted":
            mine.append(_summary(t, prog, names.get(t.creator_id)))
            # 审查员/管理员：mine 之外也把这条放进 recommended（标记 added=True 便于前端区分）
            if is_audit:
                recommended.append(_summary(t, prog, names.get(t.creator_id)))
        else:
            # 没有进度记录 或 仅做过删除标记 → 仍可被推荐
            recommended.append(_summary(t, prog if is_audit else None,
                                        names.get(t.creator_id)))
    return {"mine": mine, "recommended": recommended}


@router.post("/recommend")
def recommend(body: RecommendIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """工单创建前的相似推荐：对 device+fault 做相似度匹配。
    FIX6 第 3 项：仅排除用户当前正在参与（status != deleted）的工单；
    仅做过删除标记的工单仍参与推荐，不再永久屏蔽。"""
    query = f"{body.device} {body.fault}".strip()
    if not query:
        return []
    tickets = db.query(Ticket).order_by(Ticket.id.desc()).all()
    names = _creator_name_map(db, tickets)
    my_ids = {p.ticket_id for p in db.query(UserTicketProgress).filter(
        UserTicketProgress.user_id == user.id,
        UserTicketProgress.status != "deleted").all()}
    scored = []
    for t in tickets:
        if t.id in my_ids:
            continue
        target = f"{t.device} {t.fault}".strip()
        score = SequenceMatcher(None, query, target).ratio()
        # 关键词命中加权
        for kw in re.split(r"\s+", query):
            if kw and kw in target:
                score += 0.15
        if score >= 0.45:
            item = _summary(t, None, names.get(t.creator_id))
            item["score"] = round(min(score, 1.0), 3)
            scored.append(item)
    scored.sort(key=lambda x: -x["score"])
    return scored[:5]


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """个人中心-历史工单：我已完成或已删除的工单记录。"""
    progs = db.query(UserTicketProgress).filter(
        UserTicketProgress.user_id == user.id,
        UserTicketProgress.status.in_(["done", "deleted"]),
    ).order_by(UserTicketProgress.id.desc()).all()
    out = []
    for p in progs:
        t = db.query(Ticket).get(p.ticket_id)
        if not t:
            continue
        names = _creator_name_map(db, [t])
        item = _summary(t, p, names.get(t.creator_id))
        item["deletedAt"] = p.deleted_at.isoformat() if p.deleted_at else None
        item["deleteReason"] = p.delete_reason
        out.append(item)
    return out


@router.post("/{tid}/add")
def add_to_mine(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """把他人创建的工单添加到我的作业指引，进度从零开始。"""
    t = db.query(Ticket).get(tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    prog = _progress(db, tid, user.id)
    if prog and prog.status != "deleted":
        return {"ok": True, "id": tid}
    if prog:  # 之前删除过，重新添加：重置进度
        prog.status = "open"; prog.step_done = []; prog.added_at = datetime.utcnow()
        prog.completed_at = None; prog.deleted_at = None; prog.delete_reason = None
    else:
        prog = UserTicketProgress(user_id=user.id, ticket_id=tid, status="open",
                                  step_done=[], is_creator=(t.creator_id == user.id))
        db.add(prog)
    _add_event(db, tid, user.id, "added")
    db.commit()
    return {"ok": True, "id": tid}


@router.get("/{tid}")
def detail(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.query(Ticket).get(tid)
    if not t:
        raise HTTPException(404, detail="工单不存在")
    prog = _progress(db, tid, user.id)
    names = _creator_name_map(db, [t])
    return {
        "id": t.id, "device": t.device, "fault": t.fault, "steps": t.steps,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "creator": names.get(t.creator_id),
        "isCreator": bool(prog and prog.is_creator),
        "added": bool(prog and prog.status != "deleted"),
        "progress": {
            "status": prog.status if prog else "open",
            "stepDone": (prog.step_done or []) if prog else [],
            "addedAt": prog.added_at.isoformat() if prog and prog.added_at else None,
            "completedAt": prog.completed_at.isoformat() if prog and prog.completed_at else None,
        },
    }


def _ensure_progress(db: Session, tid: int, user: User) -> UserTicketProgress:
    prog = _progress(db, tid, user.id)
    if not prog or prog.status == "deleted":
        t = db.query(Ticket).get(tid)
        if not t:
            raise HTTPException(404, "工单不存在")
        if prog:
            prog.status = "open"; prog.step_done = []; prog.added_at = datetime.utcnow()
            prog.deleted_at = None; prog.delete_reason = None
        else:
            prog = UserTicketProgress(user_id=user.id, ticket_id=tid, status="open",
                                      step_done=[], is_creator=(t.creator_id == user.id))
            db.add(prog)
        _add_event(db, tid, user.id, "added")
    return prog


@router.patch("/{tid}/progress")
def update_progress(tid: int, body: ProgressIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    t = db.query(Ticket).get(tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    prog = _ensure_progress(db, tid, user)
    if body.stepDone is not None:
        prev = set(prog.step_done or [])
        new = [s for s in body.stepDone]
        prog.step_done = new
        step_ids = _step_ids(t)
        for sid in new:
            if sid not in prev:
                # FIX6 第 4 项：附带 stepIndex 便于前端按"第 N 步：标题"渲染
                try:
                    idx = step_ids.index(str(sid))
                except ValueError:
                    idx = None
                _add_event(db, tid, user.id, "step_completed",
                           {"stepId": sid, "stepIndex": idx})
        if prog.status == "open" and new:
            prog.status = "doing"
    if body.status:
        prog.status = body.status
        if body.status == "done":
            prog.completed_at = datetime.utcnow()
            _add_event(db, tid, user.id, "completed")
    db.commit()
    return {"ok": True, "status": prog.status}


@router.patch("/{tid}")
def update(tid: int, body: TicketStatusIn, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """兼容旧前端：PATCH /api/ticket/{id} {status:'done'} → 标记我的进度完成。"""
    return update_progress(tid, ProgressIn(status=body.status), db, user)


@router.delete("/{tid}")
def delete_mine(tid: int, body: DeleteIn = DeleteIn(), db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """删除我的工单：已完成默认理由"已完成"；未完成必须填写理由。完成记录永久保留。"""
    prog = _progress(db, tid, user.id)
    if not prog or prog.status == "deleted":
        raise HTTPException(404, "未找到该工单进度")
    if prog.status == "done":
        reason = (body.reason or "").strip() or "已完成"
    else:
        reason = (body.reason or "").strip()
        if not reason:
            raise HTTPException(400, "未完成工单删除必须填写理由")
    prog.status = "deleted"
    prog.deleted_at = datetime.utcnow()
    prog.delete_reason = reason
    _add_event(db, tid, user.id, "deleted", {"reason": reason})
    db.commit()
    return {"ok": True}


def _timeline_for(db: Session, tid: int, user_id: int) -> List[dict]:
    rows = db.query(TicketEvent).filter(
        TicketEvent.ticket_id == tid, TicketEvent.user_id == user_id
    ).order_by(TicketEvent.id.asc()).all()
    return [{"type": e.type, "detail": e.detail,
             "at": e.created_at.isoformat() if e.created_at else None} for e in rows]


@router.get("/{tid}/timeline")
def timeline(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    工单时间线：
    - 审查员/管理员：按用户分组返回**所有用户**对该工单的事件
      （包括 created/added/step_completed/completed/deleted）
    - 一线员工：仅自己的事件

    FIX7 续：响应同时回传 `viewer` 标识（`audit` / `self`）以及该工单的创建人
    （creator/creatorId），便于前端在分组标题上明确"这是所有用户的时间线"。
    """
    t = db.query(Ticket).get(tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    creator = db.query(User).filter(User.id == t.creator_id).first() if t.creator_id else None
    base = {
        "viewer": "audit" if _is_auditor(user.role) else "self",
        "creatorId": t.creator_id,
        "creator": creator.username if creator else None,
    }
    if _is_auditor(user.role):
        # 审查员/管理员：按用户分组展示所有人的时间线
        rows = db.query(TicketEvent).filter(TicketEvent.ticket_id == tid).order_by(TicketEvent.id.asc()).all()
        uids = {e.user_id for e in rows}
        names = {u.id: u.username for u in db.query(User).filter(User.id.in_(uids)).all()} if uids else {}
        grouped: dict = {}
        for e in rows:
            grouped.setdefault(e.user_id, []).append(
                {"type": e.type, "detail": e.detail,
                 "at": e.created_at.isoformat() if e.created_at else None})
        base["grouped"] = [{"userId": uid, "user": names.get(uid), "events": evs}
                           for uid, evs in grouped.items()]
        return base
    # 员工：只看自己
    base["events"] = _timeline_for(db, tid, user.id)
    return base


# ---- 工具清单 + 关联手册（同时挂 /api/ticket 与 /api/workflow）----
def _get_ticket_or_404(tid: int, db: Session):
    t = db.query(Ticket).get(tid)
    if not t:
        raise HTTPException(404, detail="工单不存在")
    return t


def _list_tools_for(t):
    out, seen = [], set()
    steps = t.steps if isinstance(t.steps, list) else []
    for st in steps:
        for name in (st.get("tools") or []):
            key = str(name).strip()
            if key and key not in seen:
                seen.add(key)
                out.append({"name": key, "qty": 1})
    return out


def _list_manuals_for(t):
    try:
        from app.services.rag import search
        query = f"{t.device} {t.fault}".strip() or t.fault
        hits = search(query, k=5)
    except Exception:
        return []
    out, seen = [], set()
    for h in hits:
        meta = h.get("metadata") or {}
        doc_id = meta.get("doc_id")
        if doc_id is None or doc_id in seen:
            continue
        seen.add(doc_id)
        dist = h.get("distance")
        score = max(0.0, 1.0 - dist) if isinstance(dist, (int, float)) else 0.0
        out.append({
            "docId": str(doc_id),
            "title": meta.get("title") or f"doc-{doc_id}",
            "matchedSection": (h.get("content") or "")[:80],
            "score": round(score, 3),
        })
    return out


@router.get("/{tid}/tools")
def list_tools(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _list_tools_for(_get_ticket_or_404(tid, db))


@router.get("/{tid}/manuals")
def list_manuals(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _list_manuals_for(_get_ticket_or_404(tid, db))


workflow_router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@workflow_router.get("/{tid}/tools")
def wf_list_tools(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _list_tools_for(_get_ticket_or_404(tid, db))


@workflow_router.get("/{tid}/manuals")
def wf_list_manuals(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _list_manuals_for(_get_ticket_or_404(tid, db))
