import os, shutil, io, mimetypes
from typing import Optional
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.db import get_db
from app.core.config import settings
from app.core.security import get_current_user, require_auditor, _is_auditor
from app.models import Document, User
from app.services.parser import read_any, parse_any
from app.services.rag import ingest_document, remove_document

router = APIRouter(prefix="/api/kb", tags=["knowledge"])

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.EXTRACTED_IMAGE_DIR, exist_ok=True)

# 允许上传的扩展名（FIX5 第 18 项：拒绝可执行文件）
ALLOWED_EXT = (".pdf", ".docx", ".txt", ".md")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB


def _doc_out(d: Document, uploader_name: Optional[str] = None) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "type": d.type,
        "category": d.category or "manual",
        "status": d.status,
        "reason": d.review_reason,
        "uploaderId": d.uploader_id,
        "uploader": uploader_name,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _uploader_name_map(db: Session, docs) -> dict:
    ids = {d.uploader_id for d in docs if d.uploader_id}
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: u.username for u in rows}


@router.post("/upload")
async def upload(file: UploadFile = File(...),
                 parent_id: Optional[int] = Form(None, description="FIX6 第 5 项：经验主条目 id"),
                 category: Optional[str] = Form(None, description="分类：manual / experience"),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    # FIX(安全)：仅取 basename，防止 file.filename 含 ../ 或绝对路径造成路径穿越
    fname = os.path.basename(file.filename or "") or f"upload_{uuid.uuid4().hex}.pdf"
    if not fname.lower().endswith(ALLOWED_EXT):
        raise HTTPException(400, "仅支持 PDF / DOCX / TXT / MD 文件")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件大小超过 50MB 限制")
    path = os.path.join(settings.UPLOAD_DIR, fname)
    with open(path, "wb") as f:
        f.write(data)
    parsed = parse_any(path)
    text = parsed.text
    # 校验 parent_id：必须为同一用户的同类条目
    parent: Optional[Document] = None
    if parent_id is not None:
        parent = db.query(Document).get(parent_id)
        if not parent:
            raise HTTPException(400, "关联的主条目不存在")
    # 管理员/审查员上传直接入库（approved）；员工上传进入待审（pending）
    approved = _is_auditor(user.role)
    doc = Document(
        title=fname, file_path=path, type=fname.split(".")[-1].lower(),
        category=category or "manual", content=text[:20000] if text else "",
        status="approved" if approved else "pending",
        uploader_id=user.id,
        parent_id=parent.id if parent else None,
    )
    db.add(doc); db.commit(); db.refresh(doc)
    n = 0
    if approved:
        n = ingest_document(doc.id, doc.title, text)
    return {"doc_id": doc.id, "chunks": n, "status": doc.status, "parent_id": doc.parent_id}


class TextDocIn(BaseModel):
    title: str
    content: str
    category: Optional[str] = "experience"


@router.post("/text")
def upload_text(body: TextDocIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """员工经验分享 / 文本知识录入。员工 → pending；审查员/管理员 → approved。"""
    title = (body.title or "").strip()
    content = (body.content or "").strip()
    if not title or not content:
        raise HTTPException(400, "标题和正文不能为空")
    approved = _is_auditor(user.role)
    # 员工只能创建经验分享类目；审查员/管理员可指定类目
    category = (body.category or "experience") if approved else "experience"
    doc = Document(
        title=title, file_path=None, type="experience",
        category=category, content=content,
        status="approved" if approved else "pending",
        uploader_id=user.id,
    )
    db.add(doc); db.commit(); db.refresh(doc)
    n = 0
    if approved:
        n = ingest_document(doc.id, doc.title, content)
    return {"doc_id": doc.id, "chunks": n, "status": doc.status}


# FIX6-resume O3：经验 + 附件原子提交端点
# 一次 multipart 请求带 title/content/category + files[]，事务内建 parent + children
# 客户端不再需要先 POST /text 拿 parent_id 再逐个 POST /upload
@router.post("/text-with-files")
async def upload_text_with_files(
    title: str = Form(...),
    content: str = Form(...),
    category: Optional[str] = Form("experience"),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    title = (title or "").strip()
    content = (content or "").strip()
    if not title or not content:
        raise HTTPException(400, "标题和正文不能为空")
    approved = _is_auditor(user.role)
    final_category = (category or "experience") if approved else "experience"

    # 预校验所有附件后再写库，避免主条目已提交、附件失败导致脏数据
    attach_buf: list[tuple[str, bytes]] = []
    for f in files or []:
        # FIX(安全)：仅取 basename，防止附件名含 ../ 或绝对路径造成路径穿越
        fname = os.path.basename(f.filename or "") or f"attach_{uuid.uuid4().hex}.pdf"
        if not fname.lower().endswith(ALLOWED_EXT):
            raise HTTPException(400, f"附件 {fname} 不支持的格式，仅支持 PDF / DOCX / TXT / MD")
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"附件 {fname} 超过 50MB 限制")
        attach_buf.append((fname, data))

    target_status = "approved" if approved else "pending"
    parent = Document(
        title=title, file_path=None, type="experience",
        category=final_category, content=content,
        status=target_status,
        uploader_id=user.id,
    )
    db.add(parent); db.flush()  # 拿到 parent.id 但不提交

    attachments_meta: list[dict] = []
    try:
        for fname, data in attach_buf:
            path = os.path.join(settings.UPLOAD_DIR, fname)
            with open(path, "wb") as fh:
                fh.write(data)
            parsed = parse_any(path)
            text = parsed.text
            child = Document(
                title=fname, file_path=path, type=fname.split(".")[-1].lower(),
                category="manual", content=text[:20000] if text else "",
                status=target_status,
                uploader_id=user.id,
                parent_id=parent.id,
            )
            db.add(child); db.flush()
            attachments_meta.append({"id": child.id, "title": fname})
        db.commit(); db.refresh(parent)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"提交失败：{e}")

    n_parent = 0
    n_attach_total = 0
    if approved:
        n_parent = ingest_document(parent.id, parent.title, content)
        for meta in attachments_meta:
            child = db.query(Document).get(meta["id"])
            if child and child.content:
                n_attach_total += ingest_document(child.id, child.title, child.content)
    return {
        "doc_id": parent.id,
        "chunks": n_parent,
        "status": parent.status,
        "attachments": attachments_meta,
        "attachment_chunks": n_attach_total,
    }


@router.get("/list")
def list_docs(status: Optional[str] = Query(None), uploader: Optional[str] = Query(None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Document)
    if uploader == "me":
        q = q.filter(Document.uploader_id == user.id)
    if status:
        q = q.filter(Document.status == status)
    # 普通员工浏览列表时仅可见已入库文档（除非查自己的上传）
    elif uploader != "me" and not _is_auditor(user.role):
        q = q.filter(Document.status.in_(["approved", "ready"]))
    docs = q.order_by(Document.id.desc()).all()
    names = _uploader_name_map(db, docs)
    # FIX6 第 5 项：主条目（parent_id IS NULL）下挂 attachments（parent_id = id）
    main_docs = [d for d in docs if d.parent_id is None]
    attach_map: dict[int, list[dict]] = {}
    for d in docs:
        if d.parent_id is not None:
            attach_map.setdefault(d.parent_id, []).append(_doc_out(d, names.get(d.uploader_id)))
    result = []
    for d in main_docs:
        item = _doc_out(d, names.get(d.uploader_id))
        ch = attach_map.get(d.id)
        if ch:
            item["attachments"] = ch
        result.append(item)
    return result


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = db.query(Document).get(doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    if d.status not in ("approved", "ready") and not _is_auditor(user.role) and d.uploader_id != user.id:
        raise HTTPException(403, "无权查看该文档")
    names = _uploader_name_map(db, [d])
    out = _doc_out(d, names.get(d.uploader_id))
    out["content"] = d.content or ""
    return out


class ReviewIn(BaseModel):
    action: str            # approve / reject / take_down
    reason: Optional[str] = None


@router.post("/review/{doc_id}")
def review_doc(doc_id: int, body: ReviewIn, db: Session = Depends(get_db),
               user: User = Depends(require_auditor)):
    d = db.query(Document).get(doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    action = (body.action or "").lower()
    target_status = ""
    if action == "approve":
        target_status = "approved"
        d.review_reason = None
        text = d.content or (read_any(d.file_path) if d.file_path else "")
        if text:
            # FIX(健壮)：审批入库失败转 502，避免 500 堆栈泄露；未 commit 故状态仍为 pending
            try:
                remove_document(d.id)
                ingest_document(d.id, d.title, text)
            except Exception as e:
                raise HTTPException(502, f"向量入库失败：{e}")
        # FIX6 第 5 项：同步通过附件
        for att in db.query(Document).filter(Document.parent_id == doc_id).all():
            att.status = "approved"; att.reviewer_id = user.id; att.reviewed_at = datetime.utcnow()
    elif action in ("reject", "take_down"):
        if not (body.reason or "").strip():
            raise HTTPException(400, "请填写理由")
        target_status = "rejected" if action == "reject" else "taken_down"
        d.status = target_status
        d.review_reason = body.reason.strip()
        remove_document(d.id)
        # FIX6 第 5 项：同步驳回附件
        for att in db.query(Document).filter(Document.parent_id == doc_id).all():
            setattr(att, "status", target_status); att.review_reason = body.reason.strip()
            remove_document(att.id)
    else:
        raise HTTPException(400, f"非法操作：{body.action}")
    d.status = target_status if target_status else d.status
    d.reviewer_id = user.id
    d.reviewed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": d.status}


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db), _user: User = Depends(require_auditor)):
    d = db.query(Document).get(doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    remove_document(d.id)
    db.delete(d); db.commit()
    return {"ok": True}


# FIX6 第 2 项：PDF 等原始文件下载/预览端点，inline 返回二进制以便前端 <iframe> 预览
@router.get("/image/{image_name}")
def get_extracted_image(image_name: str):
    """返回从 PDF/DOCX 中抽取出的图片，用于聊天答案展示图片证据。

    注意：此端点不需要登录认证。<img> 标签发出的 GET 请求不会携带
    Authorization 头，如果加 Depends(get_current_user) 会全部 401。
    /uploads/ 静态目录本身也是无认证的，此处保持一致。
    """
    safe_name = os.path.basename(image_name)
    abs_dir = os.path.abspath(settings.EXTRACTED_IMAGE_DIR)
    # 优先精确匹配文件名
    candidate = os.path.join(abs_dir, safe_name)
    if os.path.isfile(candidate):
        media_type = mimetypes.guess_type(candidate)[0] or "image/png"
        return FileResponse(candidate, media_type=media_type)
    # 兜底：遍历子目录（图片按文档名建了子目录）
    for root, _dirs, files in os.walk(abs_dir):
        if safe_name in files:
            path = os.path.join(root, safe_name)
            media_type = mimetypes.guess_type(path)[0] or "image/png"
            return FileResponse(path, media_type=media_type)
    raise HTTPException(404, "图片不存在或尚未从文档中抽取")


@router.get("/{doc_id}/download")
def download_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = db.query(Document).get(doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    if d.status not in ("approved", "ready") and not _is_auditor(user.role) and d.uploader_id != user.id:
        raise HTTPException(403, "无权查看该文档")
    if not d.file_path or not os.path.exists(d.file_path):
        raise HTTPException(404, "原始文件不存在")
    ext = (d.type or "").lower()
    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain; charset=utf-8",
        "md":  "text/markdown; charset=utf-8",
    }
    media_type = mime_map.get(ext) or mimetypes.guess_type(d.file_path)[0] or "application/octet-stream"
    safe_title = "".join(c for c in (d.title or "") if c not in '\\/:*?"<>|').strip() or f"doc-{d.id}"
    # FIX6-resume：HTTP header 必须 latin-1 编码，中文文件名要按 RFC 5987 做 percent-encoding
    # 否则 Starlette 在序列化响应头时 UnicodeEncodeError → 500
    fname_enc = _urlquote(safe_title, safe="")
    ascii_fallback = safe_title.encode("ascii", "replace").decode("ascii").replace("?", "_") or f"doc-{d.id}"
    return FileResponse(
        d.file_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{ascii_fallback}"; filename*=UTF-8\'\'{fname_enc}'},
    )


# FIX6 第 6 项：审查员 / 管理员可编辑知识库文档（含 AI 来源条目）
class KbUpdateIn(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None


@router.put("/{doc_id}")
def update_doc(doc_id: int, body: KbUpdateIn, db: Session = Depends(get_db),
               _user: User = Depends(require_auditor)):
    d = db.query(Document).get(doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    changed_text = False
    old_content = d.content
    old_title = d.title
    if body.title is not None:
        d.title = body.title.strip() or d.title
    if body.content is not None:
        d.content = body.content
        changed_text = True
    if body.category is not None:
        d.category = body.category.strip() or d.category
    if body.status is not None and body.status in ("pending", "approved", "rejected", "taken_down", "ready"):
        d.status = body.status
    # FIX(数据完整性)：向量重建必须在 commit 之前；失败时回滚本次编辑并尝试恢复旧向量，
    # 避免 status=approved 但 Chroma 零向量的静默不一致（旧实现 except:pass 静默吞错）。
    if changed_text and d.status in ("approved", "ready"):
        try:
            remove_document(d.id)
            ingest_document(d.id, d.title, d.content or "")
        except Exception as e:
            try:
                if old_content:
                    ingest_document(d.id, old_title or d.title, old_content)
            except Exception:
                pass
            db.rollback()
            raise HTTPException(500, f"向量重建失败，已回滚本次编辑：{e}")
    db.commit(); db.refresh(d)
    return {"ok": True, "id": d.id, "status": d.status}


def _doc_full_text(d: Document) -> str:
    if d.content:
        return d.content
    if d.file_path and os.path.exists(d.file_path):
        return read_any(d.file_path)
    return ""


@router.get("/{doc_id}/export")
def export_doc(doc_id: int, format: str = Query("md"), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    d = db.query(Document).get(doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    if d.status not in ("approved", "ready") and not _is_auditor(user.role) and d.uploader_id != user.id:
        raise HTTPException(403, "无权导出该文档")
    text = _doc_full_text(d)
    fmt = (format or "md").lower()
    safe_title = "".join(c for c in d.title if c not in '\\/:*?"<>|').strip() or f"doc-{d.id}"
    # FIX6-resume：同 download_doc，中文文件名必须 percent-encoding
    fname_enc = _urlquote(safe_title, safe="")
    ascii_fallback = safe_title.encode("ascii", "replace").decode("ascii").replace("?", "_") or f"doc-{d.id}"

    if fmt == "md":
        body = f"# {d.title}\n\n{text}\n"
        return StreamingResponse(
            io.BytesIO(body.encode("utf-8")),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{ascii_fallback}.md"; filename*=UTF-8\'\'{fname_enc}.md'},
        )
    if fmt == "pdf":
        try:
            pdf_bytes = _render_pdf(d.title, text)
        except Exception as e:
            raise HTTPException(500, f"PDF 生成失败：{e}")
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{ascii_fallback}.pdf"; filename*=UTF-8\'\'{fname_enc}.pdf'},
        )
    raise HTTPException(400, "format 仅支持 md / pdf")


def _render_pdf(title: str, text: str) -> bytes:
    """用 reportlab 生成 PDF；尝试 CJK 字体链以保证中文可显示。
    优先级：内置 CIDFont(STSong-Light) → 系统 NotoSansCJK / SimSun → Helvetica（纯 ASCII 兜底）。
    任何一级失败都不抛异常，最差降级到 ASCII。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    font_name = "Helvetica"
    # 1) 优先使用内置 CIDFont（无需外部字体文件）
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
    except Exception:
        # 2) 退到系统 CJK TTF
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/msyh.ttc",
        ]
        for path in candidates:
            try:
                if os.path.exists(path):
                    pdfmetrics.registerFont(TTFont("CJKFallback", path))
                    font_name = "CJKFallback"
                    break
            except Exception:
                continue

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CJKTitle", parent=styles["Title"], fontName=font_name, fontSize=18, leading=24)
    body_style = ParagraphStyle("CJKBody", parent=styles["Normal"], fontName=font_name, fontSize=11, leading=18)

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 若最终回退到 Helvetica，非 ASCII 字符无法渲染；用 ? 替换避免抛出
    def safe(s: str) -> str:
        if font_name == "Helvetica":
            return s.encode("ascii", errors="replace").decode("ascii")
        return s

    flow = [Paragraph(esc(safe(title)), title_style), Spacer(1, 8 * mm)]
    for line in (text or "").split("\n"):
        flow.append(Paragraph(esc(safe(line)) if line.strip() else "&nbsp;", body_style))
    doc.build(flow)
    return buf.getvalue()
