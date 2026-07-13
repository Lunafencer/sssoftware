from pydantic_settings import BaseSettings


import warnings

class Settings(BaseSettings):
    APP_NAME: str = "LoongChip-Maintain"
    DEBUG: bool = False

    # JWT
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MIN: int = 60 * 24
    # 开发/测试绕过默认 JWT_SECRET 强制校验（生产务必保持 false 并在 .env 设置强随机 JWT_SECRET）
    ALLOW_INSECURE_JWT: bool = False

    # DB
    DB_URL: str = "sqlite:///./loongchip.db"

    # CORS：逗号分隔的允许来源；默认仅放行本地开发前端，生产请在 .env 显式配置
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # DashScope (通义千问)
    DASHSCOPE_API_KEY: str = ""
    LLM_TEXT_MODEL: str = "qwen-plus"
    LLM_VL_MODEL: str = "qwen-vl-max"
    EMB_MODEL: str = "text-embedding-v3"

    # Vector DB
    CHROMA_DIR: str = "./chroma_db"
    COLLECTION: str = "maintenance_kb"

    UPLOAD_DIR: str = "./uploads"
    EXTRACTED_IMAGE_DIR: str = "./uploads/extracted_images"

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip() and o.strip() != "*"]


settings = Settings()

# 将相对路径目录统一解析为绝对路径（避免 CWD 不一致导致文件找不到）
# __file__ = backend/app/core/config.py → 往上 3 层到 backend/
import os as _os
_base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
for _key in ("UPLOAD_DIR", "EXTRACTED_IMAGE_DIR", "CHROMA_DIR"):
    _val = getattr(settings, _key, "")
    if isinstance(_val, str) and _val and not _os.path.isabs(_val):
        setattr(settings, _key, _os.path.abspath(_os.path.join(_base, _val)))
# DB_URL 用绝对路径 + 正斜杠（避免 Windows 反斜杠被 SQLAlchemy 误解析）
# 注意：旧实现 lstrip("./\\") 会把绝对路径的前导 / 也剥掉，导致绝对 DB_URL 静默失效——
# 这里只剥 "./" / ".\\" 前缀，绝对路径原样保留。
_val = settings.DB_URL
if _val.startswith("sqlite:///"):
    _path = _val[len("sqlite:///"):]
    if _path.startswith("./") or _path.startswith(".\\"):
        _path = _path[2:]
    if not _os.path.isabs(_path):
        _abs = _os.path.abspath(_os.path.join(_base, _path)).replace("\\", "/")
        settings.DB_URL = f"sqlite:///{_abs}"

# 生产环境安全检查
if settings.JWT_SECRET == "change-me-in-prod":
    _msg = (
        "\n❌  拒绝启动：JWT_SECRET 仍为默认值 'change-me-in-prod'。\n"
        "   生产部署前请在 .env 设置强随机 JWT_SECRET：\n"
        "   python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "   （开发/测试可设 ALLOW_INSECURE_JWT=true 或 DEBUG=true 绕过）\n"
    )
    if settings.ALLOW_INSECURE_JWT or settings.DEBUG:
        warnings.warn(_msg, RuntimeWarning)
    else:
        raise SystemExit(_msg)
if settings.DEBUG:
    import logging
    logging.warning("DEBUG 模式已开启，生产环境请设置 DEBUG=false")
