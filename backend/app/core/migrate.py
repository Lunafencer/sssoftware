"""
轻量级启动迁移：SQLite 在 create_all 时只会新建缺失的表，不会为已存在的表补列。
这里对已存在的表做 ADD COLUMN，保证旧库平滑升级（FIX5）。
新表（user_ticket_progress / ticket_events）由 Base.metadata.create_all 创建。
"""
from sqlalchemy import inspect, text
from app.core.db import engine

# 表 -> {列名: SQL 列定义}
_ADD_COLUMNS = {
    "users": {
        "is_default_admin": "BOOLEAN DEFAULT 0",
        # FIX6 第 10 项：单点登录会话版本号
        "token_version": "INTEGER DEFAULT 1",
    },
    "documents": {
        "category": "VARCHAR(32) DEFAULT 'manual'",
        "content": "TEXT",
        "review_reason": "TEXT",
        "reviewer_id": "INTEGER",
        "reviewed_at": "DATETIME",
        # FIX6 第 5 项：经验分享附件关联主条目
        "parent_id": "INTEGER",
    },
    "tickets": {
        "creator_id": "INTEGER",
    },
    "qa_logs": {
        # 赛题要求：支持手动标注与修正大模型输出结果
        "corrected_answer": "TEXT",
    },
}


def run_migrations() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _ADD_COLUMNS.items():
            if table not in existing_tables:
                continue  # 新库由 create_all 直接建出完整结构
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        # 旧库 tickets 表有 owner_id 列，迁移为 creator_id 数据
        if "tickets" in existing_tables:
            have = {c["name"] for c in insp.get_columns("tickets")}
            if "owner_id" in have:
                conn.execute(text(
                    "UPDATE tickets SET creator_id = owner_id "
                    "WHERE creator_id IS NULL AND owner_id IS NOT NULL"
                ))
        # 旧文档默认状态是 ready，归一到 approved 语义保持可检索
        if "documents" in existing_tables:
            conn.execute(text("UPDATE documents SET status='approved' WHERE status='ready'"))
