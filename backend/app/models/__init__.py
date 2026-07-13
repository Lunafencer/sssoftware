from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean, UniqueConstraint
from app.core.db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default="worker")  # worker / leader / auditor / admin
    is_default_admin = Column(Boolean, default=False)  # FIX5：默认管理员账户不可删除
    token_version = Column(Integer, default=1)  # FIX6 第 10 项：用于单点登录会话失效
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False)
    file_path = Column(String(512))            # 文件类文档的本地路径；纯文本经验分享可为空
    type = Column(String(16))                  # pdf / docx / txt / md / experience
    category = Column(String(32), default="manual")  # manual / experience（员工经验分享）
    content = Column(Text)                      # 文本知识 / 经验分享正文，用于预览与导出
    # ready/approved 视为已入库可检索；pending 待审；rejected 驳回；taken_down 已下架
    status = Column(String(16), default="pending")
    review_reason = Column(Text)               # 驳回 / 下架理由
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    uploader_id = Column(Integer, ForeignKey("users.id"))
    parent_id = Column(Integer, ForeignKey("documents.id"))  # FIX6 第 5 项：附件关联主条目
    created_at = Column(DateTime, default=datetime.utcnow)


class Ticket(Base):
    """工单为平台级资源：所有人可见，进度按用户维度独立记录在 UserTicketProgress。"""
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    device = Column(String(128))
    fault = Column(String(512))
    steps = Column(JSON)
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class UserTicketProgress(Base):
    """每个用户对某工单的独立进度。"""
    __tablename__ = "user_ticket_progress"
    __table_args__ = (UniqueConstraint("user_id", "ticket_id", name="uq_user_ticket"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), index=True)
    status = Column(String(16), default="open")     # open / doing / done / deleted
    step_done = Column(JSON, default=list)           # 已完成步骤 id 列表
    is_creator = Column(Boolean, default=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    deleted_at = Column(DateTime)
    delete_reason = Column(String(256))


class TicketEvent(Base):
    """工单时间线事件（按用户维度）。"""
    __tablename__ = "ticket_events"
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    # created / added / step_completed / completed / deleted
    type = Column(String(24))
    detail = Column(JSON)                            # 如 {"stepId": "step-1", "reason": "..."}
    created_at = Column(DateTime, default=datetime.utcnow)


class QALog(Base):
    __tablename__ = "qa_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question = Column(Text)
    answer = Column(Text)
    sources = Column(JSON)
    corrected_answer = Column(Text, nullable=True)  # 用户手动修正后的回答
    created_at = Column(DateTime, default=datetime.utcnow)


# FIX6 第 6 项：审查员 / 管理员对图谱节点/边的人工修正与删除
class KGOverride(Base):
    """图谱编辑覆盖层：人工修正的节点/边在动态构图后叠加。"""
    __tablename__ = "kg_overrides"
    id = Column(Integer, primary_key=True)
    kind = Column(String(8))                   # 'node' / 'edge'
    target_id = Column(String(128), index=True)  # node_id 或 "{source}|{target}"
    op = Column(String(8))                     # 'update' / 'delete'
    payload = Column(JSON)                     # 更新内容（label/desc/rel 等）
    operator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
