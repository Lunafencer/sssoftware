import os, shutil, uuid, re, json
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.db import get_db, SessionLocal
from app.core.config import settings
from app.core.security import get_current_user
from app.services.llm import vl_describe, chat_text_stream
from app.services.rag import (
    rag_retrieve, build_user_prompt, SYSTEM_PROMPT, _NO_HIT_ANSWER,
)
from app.models import QALog, Ticket, UserTicketProgress, User
from difflib import SequenceMatcher

router = APIRouter(prefix="/api/chat", tags=["chat"])


# FIX7 续：用提问中的关键字在 chunk 中定位"相关窗口"作为引用 snippet，
# 而不是粗暴截取 chunk[:150]——否则首句很可能是无关过渡文字，用户看了会觉得"引用与问题不搭边"
_STOPWORDS = {
    "的", "了", "和", "是", "在", "我", "你", "他", "她", "它", "怎么", "如何", "什么",
    "怎样", "为什么", "为何", "请问", "请", "吗", "吧", "啊", "也", "都", "就", "还",
    "有", "没", "没有", "不", "会", "能", "可以", "需要", "要"
}


def _extract_keywords(text: str) -> list[str]:
    """从提问里抽出关键词：中文 2 字及以上 + 英文/数字 token + 单字符编号（如 1、2）。"""
    if not text:
        return []
    cn = re.findall(r"[一-鿿]{2,}", text)
    en = re.findall(r"[A-Za-z0-9_\-]{2,}", text)
    # 图中编号类问题（如"1和2是什么"）需要保留单数字；
    # 使用前后非数字断言，避免在中文连续字符中无法提取（\b 对中文无效）。
    numbers = re.findall(r"(?<!\d)([1-9]|10)(?!\d)", text)
    keywords: list[str] = []
    seen: set[str] = set()
    for tok in cn + en + numbers:
        if tok in _STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        keywords.append(tok)
    return keywords[:10]


def _image_url(path: str) -> str:
    if not path:
        return ""
    name = os.path.basename(path)
    return f"/api/kb/image/{name}"


def _image_items(paths: list[str]) -> list[dict]:
    out = []
    for p in paths or []:
        name = os.path.basename(p) if p else ""
        url = f"/api/kb/image/{name}" if name else ""
        out.append({"path": p or "", "url": url, "name": name})
    return out


def _split_packed_table(line: str) -> list[str]:
    """把识别成连续一行的零件清单/表格拆回多行，同时保留表头和后续说明文字。

    例如：'序号 零件名称 数量 备注 1 曲轴连杆部装组件 1 2 平衡轴部装组件 1 提示...'
    → ['序号 零件名称 数量 备注', '1 曲轴连杆部装组件 1', '2 平衡轴部装组件 1', '提示...']
    """
    if not line:
        return []
    # 零件名称通常是不含空格、数字、点、斜杠的短中文词；用该限制避免把规格参数或页脚误拆成表格行。
    _table_name = r"[^\d\s\.\/a-zA-Z]{2,20}"
    pattern = re.compile(
        rf"(\d{{1,2}})\s+({_table_name})\s+(\d{{1,3}})"
        rf"(?=\s+(?:\d{{1,2}}\s+{_table_name}\s+\d{{1,3}})|[^\d\.]|$)"
    )
    matches = list(pattern.finditer(line))
    if len(matches) < 2:
        return [line]
    parts: list[str] = []
    last_end = 0
    for m in matches:
        prefix = line[last_end:m.start()].strip()
        if prefix:
            parts.append(prefix)
        parts.append(m.group(0).rstrip())
        last_end = m.end()
    # 保留最后一个表格行之后的说明文字
    suffix = line[last_end:].strip()
    if suffix:
        parts.append(suffix)
    return parts


def _normalize_snippet(text: str) -> str:
    """在语义边界处插入换行，使引用文本结构清晰、易于阅读。"""
    if not text:
        return text
    # 1. 统一空格
    text = re.sub(r"\s+", " ", text).strip()

    # 2. 表格头单独成行（前后都换行）
    text = re.sub(r"(^|\s+)(序号\s+零件名称\s+数量\s+备注)\s+", r"\n\2\n", text)

    # 3. 拆分表格行：序号 + 名称 + 数量 后面紧跟下一个序号时换行
    # 名称限制为不含空格/数字/点/斜杠/英文的短中文，避免误拆规格参数或页脚。
    _table_name = r"[^\d\s\.\/a-zA-Z]{2,20}"
    text = re.sub(
        rf"(\d{{1,2}}\s+{_table_name}\s+\d{{1,3}})(\s+)(?=\d{{1,2}}\s+{_table_name}\s+\d{{1,3}})",
        r"\1\n",
        text,
    )

    # 4. 在提示/注意/警告前换行
    text = re.sub(r"(^|\s+)(提示[：:])", r"\n\2", text)
    text = re.sub(r"(^|\s+)(注意[：:])", r"\n\2", text)
    text = re.sub(r"(^|\s+)(警告[：:])", r"\n\2", text)

    # 5. 在中文章节标题前换行（如 "九、曲轴与平衡轴"）
    text = re.sub(r"(^|\s+)([一二三四五六七八九十]+、)", r"\n\2", text)

    # 6. 在 "X.X " 编号（如 9.1、5.4）前换行
    text = re.sub(r"(^|\s+)(\d+\.\d+\s+)", r"\n\2", text)

    # 7. 在步骤编号 "（ X ）" 或 "( X )" 前换行（不带点的括号编号）
    text = re.sub(r"(^|\s+)(（\s*\d+\s*）|\(\s*\d+\s*\))", r"\n\2", text)

    # 8. 在步骤编号 "X. " 或 "X、" 前换行
    text = re.sub(r"(^|\s+)(\d+\.\s+|\d+、)", r"\n\2", text)

    # 9. 在冒号标记项（如 “L”：副轴左拨叉）前换行，保留完整引号+字母+冒号
    text = re.sub(r"(^|\s+)([“\"][A-Za-z][”\"]\s*[：:])", r"\n\2", text)

    # 10. 清理多余空行和行首空格
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip("\n")
    text = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    return text


def _clean_source_text(text: str) -> str:
    """清理引用文本：隐藏图片路径/文件名/识别元信息等技术噪音，规范表格格式。"""
    if not text:
        return ""
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        # 去除图片识别结果前缀，如 "[页包含 1 张内嵌图片/图表，以下为图片识别结果。]"
        s = re.sub(r"^.*?(?:页包含\s*\d+\s*张内嵌图片/图表，以下为图片识别结果。?]\s*)", "", s)
        # 去除行首残留的 ] ) ）等符号
        s = re.sub(r"^[\]\)）\s]+", "", s)
        if s.startswith("[图片文件]"):
            continue
        if "uploads" in s or "extracted_images" in s:
            continue
        if re.search(r"page-\d{3}-image-\d{2}\.(png|jpg|jpeg|webp)", s, re.I):
            continue
        if s.startswith("该图片来自原文档"):
            continue
        if re.search(r"^\[\s*第\s*\d+\s*页\s*图片\s*\d+\s*\]", s):
            continue
        # 去除末尾页脚页码（如 "摩托车发动机维修手册 No. 38 / 41"），只删页码部分
        s = re.sub(r"\s+No\.\s*\d+\s*/\s*\d+\s*$", "", s)
        lines.append(s)
    # 把可能挤成一行的零件清单/表格拆分为多行，并做整体结构规范化
    normalized: list[str] = []
    for ln in lines:
        split_lines = _split_packed_table(ln)
        for sl in split_lines:
            normalized.extend(_normalize_snippet(sl).splitlines())
    return "\n".join(normalized)


def _build_snippet(content: str, keywords: list[str], window: int = 40, max_len: int = 140) -> str:
    """围绕命中的关键词截取最相关的一句话/一行；找不到时退回清理后的首段。"""
    if not content:
        return ""
    text = _clean_source_text(content).strip()
    if not text:
        return ""

    lines = [ln for ln in text.splitlines() if ln.strip()]

    # 特殊场景：用户问图中编号（如"1和2是什么"），且命中内容包含零件清单表
    number_keywords = {kw for kw in keywords if kw.isdigit()}
    if number_keywords:
        header_idx = -1
        for i, ln in enumerate(lines):
            if re.search(r"序号\s+零件名称\s+数量\s+备注", ln):
                header_idx = i
                break
        if header_idx >= 0:
            selected: list[str] = [lines[header_idx]]
            for ln in lines:
                m = re.match(r"(\d{1,2})\s+", ln)
                if m and m.group(1) in number_keywords:
                    selected.append(ln)
                    if len(selected) >= 5:  # 最多返回表头 + 4 行
                        break
            if len(selected) > 1:
                return "\n".join(selected)

    # 按行拆分，优先找到包含最多关键词的那一行（适合零件清单、步骤表）
    best_line = ""
    best_score = -1
    for ln in lines:
        score = sum(1 for kw in keywords if kw in ln)
        if score > best_score:
            best_score = score
            best_line = ln.strip()

    if best_score > 0 and best_line:
        # 行较短直接返回，保持表格行/步骤行完整可读
        if len(best_line) <= max_len:
            return best_line
        # 行太长时，再截取关键词附近的上下文
        pos = -1
        for kw in keywords:
            idx = best_line.find(kw)
            if idx >= 0 and (pos < 0 or idx < pos):
                pos = idx
        if pos < 0:
            return best_line[:max_len] + "…"
        start = max(0, pos - window)
        end = min(len(best_line), pos + window + max_len // 3)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(best_line) else ""
        return f"{prefix}{best_line[start:end]}{suffix}"

    #  Fallback：按连续文本找第一个命中位置
    best_pos = -1
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0 and (best_pos < 0 or idx < best_pos):
            best_pos = idx
    if best_pos < 0:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    start = max(0, best_pos - window)
    end = min(len(text), best_pos + window + max_len // 3)
    chunk = text[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{chunk}{suffix}"


def _rank_hits(hits: list[dict], keywords: list[str]) -> list[dict]:
    """按关键词命中密度重排 hits，越相关越靠前。"""
    scored = []
    for h in hits:
        text = _clean_source_text(h.get("original_content") or h.get("content") or "")
        # 关键词命中次数作为首要排序依据；distance 作为次要依据
        hit_count = sum(1 for kw in keywords if kw in text)
        # 优先保留带图片的命中（用户问图中部件时，图文页更相关）
        has_image = 1 if h.get("image_paths") else 0
        distance = h.get("distance") if h.get("distance") is not None else 1.0
        scored.append((
            -hit_count,        # 命中越多越靠前（负值升序）
            -has_image,        # 有图优先
            distance,          # 向量距离越小越靠前
            h,
        ))
    scored.sort(key=lambda x: x[:3])
    return [x[3] for x in scored]


def _select_sources(hits: list[dict], keywords: list[str], max_sources: int = 2) -> list[dict]:
    """从 hits 中精选最相关的几条作为前端引用，避免无关引用刷屏。"""
    if not hits:
        return []
    ranked = _rank_hits(hits, keywords)
    return ranked[:max_sources]


def _recommend_tickets(db: Session, user_id: int, question: str, img_desc: str = ""):
    """在工单库中按相似度推荐工单（FIX5 第 13 项）。"""
    query = f"{question} {img_desc}".strip()
    if not query:
        return []
    tickets = db.query(Ticket).order_by(Ticket.id.desc()).limit(200).all()
    my_ids = {p.ticket_id for p in db.query(UserTicketProgress).filter(
        UserTicketProgress.user_id == user_id,
        UserTicketProgress.status != "deleted").all()}
    scored = []
    for t in tickets:
        target = f"{t.device} {t.fault}".strip()
        if not target:
            continue
        score = SequenceMatcher(None, query, target).ratio()
        for kw in (t.device or "", t.fault or ""):
            if kw and kw in query:
                score += 0.2
        if score >= 0.3:
            scored.append({
                "id": t.id,
                "device": t.device,
                "fault": t.fault,
                "summary": (t.fault or "")[:60],
                "added": t.id in my_ids,
                "score": round(min(score, 1.0), 3),
            })
    scored.sort(key=lambda x: -x["score"])
    return scored[:4]


def _extract_page_from_chunk(content: str) -> Optional[int]:
    """从 chunk 原文中提取页码信息。

    PDF 解析时每页开头会插入 `[第 X 页包含 ...]` 标记，
    找到最后一个页码标记即可推断该 chunk 覆盖的起始页。
    """
    if not content:
        return None
    # 匹配 "[第 N 页包含 ..." 或 "[第N页包含..."
    pages = re.findall(r"第\s*(\d+)\s*页", content)
    if pages:
        return int(pages[-1])
    # 兜底：匹配 "No. N / M" 页脚格式
    footer = re.search(r"No\.\s*(\d+)\s*/\s*\d+", content)
    if footer:
        return int(footer.group(1))
    return None


def _build_raw_snippet(content: str, keywords: list[str], window: int = 40, max_len: int = 140) -> str:
    """为跳转定位构造 hl 参数：从原始 chunk 文本中截取关键短语，不做格式化处理。

    与 _build_snippet 不同，这里不做 _clean_source_text / _normalize_snippet 处理，
    保留原文格式，确保在 Preview 页的 locateInMarkdown 中能搜到。
    """
    if not content:
        return ""
    # 只做最基本的清理：去掉图片路径行，保留其余原文
    lines = []
    for ln in content.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("[图片文件]"):
            continue
        if "uploads" in s or "extracted_images" in s:
            continue
        if re.search(r"page-\d{3}-image-\d{2}\.(png|jpg|jpeg|webp)", s, re.I):
            continue
        lines.append(s)
    text = " ".join(lines)
    if not text:
        return ""

    # 找包含最多关键词的短片段（优先保留原文中的关键短语）
    best_pos = -1
    best_score = 0
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            score = sum(1 for k in keywords if k in text[max(0, idx - 20):idx + 60])
            if score > best_score or (score == best_score and (best_pos < 0 or idx < best_pos)):
                best_score = score
                best_pos = idx
    if best_pos < 0:
        return text[:max_len]
    start = max(0, best_pos - window)
    end = min(len(text), best_pos + window + max_len // 3)
    return text[start:end]


# 多模态问题修复：纯图片查询（用户未输入文字）自动切换 VL 为文档识别模式
_PLACEHOLDER_PATTERNS = {"请描述设备图片中的故障", "请描述", "", " "}


def _sse(event: str, data: dict) -> str:
    """格式化一条 SSE 事件（event + data JSON）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/query")
async def query(
    question: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    img_desc = ""
    # 检测是否为纯图片查询（question 为空或仅含前端兜底占位符）
    q_trimmed = (question or "").strip()
    is_image_only = not q_trimmed or q_trimmed in _PLACEHOLDER_PATTERNS

    if image is not None:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        ext = image.filename.split(".")[-1]
        local = os.path.join(settings.UPLOAD_DIR, f"q_{uuid.uuid4().hex}.{ext}")
        with open(local, "wb") as f:
            shutil.copyfileobj(image.file, f)
        # 纯图片查询 → document 模式（OCR/文档识别）；有文字 → fault 模式（故障诊断）
        vl_mode = "document" if is_image_only else "fault"
        try:
            img_desc = vl_describe(f"file://{os.path.abspath(local)}", mode=vl_mode)
        except Exception as e:
            # VL 调用失败：如果有文字问题就用文字，没有就报错
            if not q_trimmed:
                raise HTTPException(500, f"图片识别失败：{e}")
            img_desc = ""

    # 纯图片查询时，用 VL 识别结果作为主查询主体（而非被占位符稀释语义）
    effective_question = img_desc if is_image_only and img_desc else q_trimmed
    if not effective_question:
        raise HTTPException(400, "请输入问题或上传图片")

    # FIX NEEDS「打字机流式」：先检索 + 组装 prompt，再流式生成。
    # 检索/推荐/引用在流式开始前用请求级 db 计算；QALog 在生成完成后用独立 session 写入
    # （StreamingResponse 生成器在 endpoint 返回后才执行，请求级 Depends session 已关闭）。
    try:
        _normalized, hits = rag_retrieve(effective_question, img_desc, image_only=is_image_only)
    except Exception as e:
        raise HTTPException(502, f"检索失败：{e}")
    # FIX7 续：用提问关键词定位 chunk 内的相关窗口作为 snippet，避免首段无关
    # FIX8-refine：引用只保留最相关的 1-2 条，避免无关来源刷屏
    keywords = _extract_keywords(f"{question} {img_desc}")
    selected = _select_sources(hits, keywords, max_sources=2)
    sources_payload = [
        {
            "index": i,
            "id": h.get("id", f"src-{i}"),
            "doc_id": h["metadata"].get("doc_id"),
            "title": h["metadata"].get("title"),
            "snippet": _build_snippet(h.get("original_content") or h["content"] or "", keywords),
            # 跳转定位专用：用原文关键短语而非格式化后的 snippet，确保 Preview 页能搜到
            "hl": _build_raw_snippet(h.get("original_content") or h["content"] or "", keywords),
            # 从 chunk 原文推断页码（PDF 场景下用于跳页定位）
            "page": _extract_page_from_chunk(h.get("original_content") or h["content"] or ""),
            "images": _image_items(h.get("image_paths") or []),
        }
        for i, h in enumerate(selected, start=1)
    ]
    recommended = _recommend_tickets(db, user.id, question, img_desc)
    user_id = user.id

    # 无命中：直接返回兜底文案（单次 token + meta + done）
    if not hits:
        def _gen_empty():
            yield _sse("token", {"delta": _NO_HIT_ANSWER})
            yield _sse("meta", {
                "qa_log_id": None,
                "answer": _NO_HIT_ANSWER,
                "image_observation": img_desc,
                "sources": [],
                "recommended_tickets": recommended,
            })
            yield _sse("done", {})
        return StreamingResponse(_gen_empty(), media_type="text/event-stream")

    user_prompt = build_user_prompt(question, img_desc, is_image_only, hits)

    def _gen():
        full: list[str] = []
        try:
            for delta in chat_text_stream(SYSTEM_PROMPT, user_prompt, temperature=0.1, top_p=0.7):
                full.append(delta)
                yield _sse("token", {"delta": delta})
        except Exception as e:
            yield _sse("error", {"message": f"AI 生成失败：{e}"})
            return
        answer = "".join(full)
        # 用独立 session 写 QALog（请求级 session 在 endpoint 返回后已关闭）
        qa_log_id = None
        _db = SessionLocal()
        try:
            log = QALog(question=question, answer=answer,
                        sources=[h["metadata"] for h in hits], user_id=user_id)
            _db.add(log); _db.commit(); _db.refresh(log)
            qa_log_id = log.id
        except Exception:
            pass
        finally:
            _db.close()
        yield _sse("meta", {
            "qa_log_id": qa_log_id,
            "answer": answer,
            "image_observation": img_desc,
            "sources": sources_payload,
            "recommended_tickets": recommended,
        })
        yield _sse("done", {})

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/correct")
async def correct_answer(
    qa_log_id: int = Form(...),
    corrected_answer: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存用户对 AI 问答结果的手动修正。"""
    log = db.query(QALog).filter(QALog.id == qa_log_id, QALog.user_id == user.id).first()
    if not log:
        raise HTTPException(404, "问答记录不存在")
    log.corrected_answer = corrected_answer
    db.commit()
    return {"ok": True}
