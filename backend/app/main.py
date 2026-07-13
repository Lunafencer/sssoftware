from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as _sql_text
from app.core.db import Base, engine, SessionLocal
from app.core.config import settings
from app.api import auth, kb, chat, ticket, kg, admin
from app import models  # noqa: register
from app.core.migrate import run_migrations

Base.metadata.create_all(bind=engine)
# 旧库平滑升级：为已存在的表补充 FIX5 新增列
run_migrations()

# 启动时确保有默认 admin 账号（admin / 123456，不可删除）
def _seed_default_admin():
    db = SessionLocal()
    try:
        admin.ensure_default_admin(db)
    finally:
        db.close()
_seed_default_admin()

app = FastAPI(title=settings.APP_NAME)
# CORS：本应用使用 Bearer token（非 cookie），故不带 credentials——
# 这样 allow_headers=["*"] 可直接覆盖 Authorization，浏览器不会因 credentials 拒绝。
# 仅当显式配置 CORS_ORIGINS=* 时退化为完全开放模式。
_cors_origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(ticket.router)
app.include_router(ticket.workflow_router)
app.include_router(kg.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    """深度健康检查：DB / Chroma / DashScope 三项依赖逐项探活。

    旧实现恒返回 ok=true，DashScope 不可达或 Chroma 损坏时编排器仍报健康。
    """
    checks: dict = {}
    # DB
    try:
        _db = SessionLocal()
        try:
            _db.execute(_sql_text("SELECT 1"))
            checks["db"] = "ok"
        finally:
            _db.close()
    except Exception as e:
        checks["db"] = f"fail: {e}"
    # Chroma
    try:
        from app.services.rag import _col
        _col.count()
        checks["chroma"] = "ok"
    except Exception as e:
        checks["chroma"] = f"fail: {e}"
    # DashScope：仅检查 key 是否配置，避免每次探活产生计费调用
    checks["dashscope"] = "ok" if settings.DASHSCOPE_API_KEY else "fail: no api key"
    ok = all(v == "ok" for v in checks.values())
    return {"ok": ok, "app": settings.APP_NAME, **checks}
