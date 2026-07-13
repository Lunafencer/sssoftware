"""RAG 服务：文档切片→嵌入→Chroma 入库；问答检索。"""
from typing import List, Tuple
import os
import re
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import settings
from app.services.llm import embed, chat_text


_client = chromadb.PersistentClient(path=settings.CHROMA_DIR, settings=ChromaSettings(allow_reset=False))
_col = _client.get_or_create_collection(settings.COLLECTION, metadata={"hnsw:space": "cosine"})


def _split_sentences(paragraph: str) -> List[str]:
    """按中文/英文句末标点切句，保留句末标点，避免从句中间硬切。"""
    paragraph = re.sub(r"\s+", " ", paragraph.strip())
    if not paragraph:
        return []
    parts = re.split(r"(?<=[。！？；;.!?])\s*", paragraph)
    return [p.strip() for p in parts if p.strip()]


def split_text(text: str, size: int = 900, overlap: int = 180) -> List[str]:
    """语义边界优先切片。

    原实现是 500/50 的纯字符滑窗，容易切断标题、步骤、参数表。
    这里优先按段落/句子聚合，单段过长时再按句子拆分，并用更高 overlap
    保留相邻上下文，改善检修手册步骤连续性。
    """
    text = (text or "").strip()
    if not text:
        return []

    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    units: List[str] = []
    for block in blocks:
        if len(block) <= size:
            units.append(block)
        else:
            units.extend(_split_sentences(block))

    chunks: List[str] = []
    current = ""
    for unit in units:
        sep = "\n\n" if current else ""
        if current and len(current) + len(sep) + len(unit) > size:
            chunks.append(current.strip())
            carry = current[-overlap:].strip() if overlap > 0 else ""
            current = f"{carry}\n\n{unit}" if carry else unit
        elif len(unit) > size:
            # 极端长句/表格行兜底切分，但仍保留 overlap。
            step = max(size - overlap, 1)
            for i in range(0, len(unit), step):
                part = unit[i:i + size].strip()
                if part:
                    chunks.append(part)
            current = ""
        else:
            current = f"{current}{sep}{unit}" if current else unit
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _extract_image_paths(text: str) -> list[str]:
    paths: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("[图片文件]"):
            p = line.replace("[图片文件]", "", 1).strip()
            if p:
                paths.append(p)
    return paths


def ingest_document(doc_id: int, title: str, full_text: str):
    chunks = split_text(full_text)
    if not chunks:
        return 0
    vecs = embed(chunks)
    ids = [f"d{doc_id}_c{i}" for i in range(len(chunks))]
    total = len(chunks)
    metas = []
    for i, chunk in enumerate(chunks):
        image_paths = _extract_image_paths(chunk)
        meta = {"doc_id": doc_id, "title": title, "idx": i, "total": total}
        if image_paths:
            meta["image_paths"] = "|".join(image_paths)
        metas.append(meta)
    _col.add(ids=ids, documents=chunks, embeddings=vecs, metadatas=metas)
    return len(chunks)


def remove_document(doc_id: int) -> None:
    """从向量库移除某文档的全部切片（驳回 / 下架 / 删除时调用）。"""
    try:
        _col.delete(where={"doc_id": doc_id})
    except Exception:
        pass


# 多模态问题修复（第4项）：相似度阈值
# cosine distance > MAX_SEARCH_DISTANCE 的结果视为不相关，不返回
MAX_SEARCH_DISTANCE = 0.65


def _fetch_neighbor(doc_id: int, idx: int) -> tuple[str, dict]:
    """读取命中 chunk 的相邻切片，给模型补足上下文。"""
    if idx < 0:
        return "", {}
    cid = f"d{doc_id}_c{idx}"
    try:
        res = _col.get(ids=[cid])
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        return (docs[0] if docs else ""), (metas[0] if metas else {})
    except Exception:
        return "", {}


def search(query: str, k: int = 5, include_neighbors: bool = True) -> List[dict]:
    """向量检索，返回 Top-k 结果。

    - 过滤掉 distance > MAX_SEARCH_DISTANCE 的低质量匹配；
    - 默认把命中 chunk 的前后相邻 chunk 拼入 context，缓解切片导致的上下文断裂。
    - 图片只取主 chunk 的，不收集相邻 chunk 的图片（避免返回大量无关图）。
    """
    query = (query or "").strip()
    if not query:
        return []
    q_vec = embed([query])[0]
    res = _col.query(query_embeddings=[q_vec], n_results=k)
    out = []
    for i in range(len(res["ids"][0])):
        dist = res["distances"][0][i] if res.get("distances") else None
        # 相似度阈值过滤：cosine distance 过大说明语义不相关
        if dist is not None and dist > MAX_SEARCH_DISTANCE:
            continue
        original_content = res["documents"][0][i]  # 主 chunk 原文（不合并邻居）
        meta = res["metadatas"][0][i] or {}
        # 图片只取主 chunk 的，不收集邻居的
        image_paths = _extract_image_paths(original_content)
        if meta.get("image_paths"):
            image_paths.extend(str(meta.get("image_paths")).split("|"))
        image_paths = list(dict.fromkeys([p for p in image_paths if p]))
        # 邻居合并只用于 LLM context，不影响 snippet 和 images
        content = original_content
        if include_neighbors:
            doc_id = meta.get("doc_id")
            idx = meta.get("idx")
            if isinstance(doc_id, int) and isinstance(idx, int):
                before, _ = _fetch_neighbor(doc_id, idx - 1)
                after, _ = _fetch_neighbor(doc_id, idx + 1)
                parts = [p for p in [before, original_content, after] if p]
                content = "\n\n".join(parts)
        out.append({
            "id": res["ids"][0][i],
            "content": content,
            "original_content": original_content,
            "metadata": meta,
            "distance": dist,
            "image_paths": image_paths,
        })
    return out


SYSTEM_PROMPT = (
    "你是企业设备检修助手龙芯智修。必须严格、只依据用户提供的【检修知识】回答。"
    "硬性规则："
    "1) 不得使用常识或训练记忆补全手册中没有的步骤、参数、故障原因；"
    "2) 只回答用户明确提出的问题，严禁主动输出'图像观察'、'设备状态分析'、'可能故障'、'建议'等用户未要求的内容；"
    "3) 如果用户上传了图片但问题非常宽泛（如'这是什么'、'这个在干嘛'、'分析一下'、'介绍一下'），"
    "   应默认理解为询问图片中展示的设备/部件/操作，并直接基于【检修知识】回答，不得以'未指明对象'为由拒绝；"
    "4) 如果【检修知识】中包含与用户问题相关的图片（[图片文件]标记），"
    "   必须结合图片内容和对应文字描述来回答，不能因为缺少编号标注就说不知道；"
    "5) 回答中的关键判断、参数、步骤必须附带对应来源编号，如 [1]、[2]；"
    "6) 每个主要结论后尽量引用原文关键句，格式为：原文依据：\"...\"；"
    "7) 不得编造工具、零件型号、数值、验收标准；"
    "8) 当用户问图中某个部件是什么时，直接根据手册中的零件清单、部件名称给出答案，并说明依据来源页码。"
    "   不要描述用户没有问的设备状态，不要推测故障，不要把系统识别结果说成是用户的描述；"
    "9) 回答应简洁，抓住要点，不过度展开。"
    "回答使用中文。"
)


def _is_vague_question(question: str) -> bool:
    """判断问题是否为宽泛询问，需要结合图片才能明确意图。"""
    if not question:
        return False
    q = question.strip().lower()
    q = re.sub(r"[\s?？]+$", "", q)
    vague_set = {
        "这是什么", "这个是什么", "这什么", "这玩意是什么",
        "这是什么在干嘛", "这是什么在做什么", "这个在干嘛", "这个在做什么",
        "在干嘛", "在做什么", "做什么", "是什么",
        "分析一下", "分析", "介绍一下", "介绍", "说明一下", "说明",
        "看看", "帮我看看", "看一下", "", "?", "？",
    }
    if q in vague_set:
        return True
    # 短问题（<=4 字符）且包含宽泛动词，也视为宽泛
    if len(q) <= 4 and any(v in q for v in ("什么", "干嘛", "分析", "介绍", "看", "说")):
        return True
    return False


def _normalize_vague_question(question: str, image_desc: str) -> str:
    """把宽泛问句转化为明确的图片内容询问，用于检索和生成。"""
    return "请根据图片和【检修知识】说明图中展示的是什么设备/部件，以及正在进行什么操作"


_NO_HIT_ANSWER = (
    "知识库未检索到足够依据，不能可靠回答该问题。请补充或上传对应设备手册、故障代码表、"
    "维修步骤、参数表或更清晰的现场/文档图片后再试。"
)


def rag_retrieve(question: str, image_desc: str = "", image_only: bool = False) -> tuple[str, list[dict]]:
    """检索知识库（含关键词兜底），返回 (normalized_question, hits)。

    多模态问题修复（第2项）：
    - 当 question 为空但 image_desc 非空时，以 image_desc 作为检索主查询
    - 有文字问题时，拼接格式保持原有逻辑
    - 当问题宽泛且上传了图片时，自动将其转化为对图片内容的询问，避免模型拒绝回答
    """
    # 对宽泛问句进行归一化，使检索和生成都有明确意图
    normalized_question = question
    if image_desc and _is_vague_question(question):
        normalized_question = _normalize_vague_question(question, image_desc)

    if not question and image_desc:
        # 纯图片查询：VL 输出已包含文档识别结果，直接作为查询主体
        enriched = image_desc
    elif image_desc:
        enriched = f"{normalized_question}\n（图片观察：{image_desc}）"
    else:
        enriched = normalized_question

    # 纯图片查询保持上一版能力：检索时允许邻居补充上下文，避免因为主chunk只含图片路径而答不出来。
    # 注意：search() 已经限制 images/snippet 只来自主chunk，不会影响引用展示。
    hits = search(enriched, k=5, include_neighbors=True)
    # 关键词兜底：嵌入向量可能因术语偏差("曲轴箱分解图" vs "曲轴连杆部装组件")不匹配
    # 提取短关键词逐一检索，合并命中结果
    if not hits:
        kws = re.findall(r'[\u4e00-\u9fff]{2,4}', enriched)
        seen_ids: set[str] = set()
        for kw in kws[:6]:
            for h in search(kw, k=3):
                hid = h.get("id", "")
                if hid not in seen_ids:
                    seen_ids.add(hid)
                    hits.append(h)
        if len(hits) > 5:
            hits.sort(key=lambda x: x.get("distance", 1.0))
            hits = hits[:5]
    return normalized_question, hits


def build_user_prompt(question: str, image_desc: str, image_only: bool, hits: list[dict]) -> str:
    """依据检索结果组装给 LLM 的 user prompt（FIX8-refine：分离系统识别结果与用户原始问题）。"""
    context = "\n\n".join([f"[{i+1}] {h['metadata'].get('title','')}: {h['content']}" for i, h in enumerate(hits)])
    user = f"【检修知识】\n{context}\n\n【用户问题】\n{question or '(用户仅上传图片，未输入文字)'}"
    if image_desc and _is_vague_question(question):
        user += (
            "\n\n【问题补充说明】\n"
            "用户上传了图片，但问题比较宽泛。请默认理解为：请根据图片和手册说明图中展示的设备/部件/操作。"
            "直接回答，不要以'未指明对象'或'无法确定'为由拒绝。"
        )
    if image_desc:
        user += (
            f"\n\n【系统图片识别参考】\n{image_desc}\n"
            "（注意：以上是系统自动识别结果，仅用于辅助检索和交叉验证；"
            "回答必须严格基于【检修知识】，且不得把它复述为'用户描述'或'图像观察'。）"
        )
    if image_only and image_desc:
        user += (
            "\n\n【重要补充】\n"
            "用户上传图片并询问图片内容。请直接基于【检修知识】回答用户问题，"
            "不要主动描述图片、不要分析设备状态、不要推测故障。"
            "只有当【检修知识】确实无法支撑时才说明不确定。"
        )
    return user


def rag_answer(question: str, image_desc: str = "", image_only: bool = False) -> Tuple[str, List[dict]]:
    """RAG 问答：基于问题（+ 可选图片描述）检索知识库并生成回答（非流式，保留供兼容/测试）。"""
    _normalized, hits = rag_retrieve(question, image_desc, image_only)
    if not hits:
        return _NO_HIT_ANSWER, []
    user = build_user_prompt(question, image_desc, image_only, hits)
    answer = chat_text(SYSTEM_PROMPT, user, temperature=0.1, top_p=0.7)
    return answer, hits
