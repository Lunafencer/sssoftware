from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db

security = HTTPBearer(auto_error=False)


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(p: str, hashed: str) -> bool:
    return bcrypt.checkpw(p.encode("utf-8"), hashed.encode("utf-8"))


def create_token(sub: str, role: str, token_version: int = 1) -> str:
    """FIX6 第 10 项：payload 中嵌入 token_version，配合 User.token_version 实现单点登录。"""
    payload = {
        "sub": sub,
        "role": role,
        "tv": token_version,
        "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MIN),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security), db: Session = Depends(get_db)):
    if creds is None:
        raise HTTPException(401, "未登录")
    try:
        payload = decode_token(creds.credentials)
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(401, "Token 无效")
    except JWTError:
        raise HTTPException(401, "Token 无效或已过期")
    from app.models import User
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(401, "用户不存在")
    # FIX6 第 10 项：单点登录 —— 校验 token_version 与当前用户记录是否一致
    token_tv = payload.get("tv")
    current_tv = getattr(user, "token_version", 1) or 1
    # 兼容旧 token（无 tv 字段）：视作版本 1
    if token_tv is None:
        token_tv = 1
    if int(token_tv) != int(current_tv):
        raise HTTPException(401, "账号已在其他设备登录，请重新登录")
    return user


# 后端角色：worker / leader / auditor / admin。auditor 与 leader 等价（审核员）。
def _is_auditor(role: str) -> bool:
    return role in ("auditor", "leader", "admin")


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


def require_auditor(user=Depends(get_current_user)):
    """审核员或管理员可访问。"""
    if not _is_auditor(user.role):
        raise HTTPException(403, "需要审核员或管理员权限")
    return user
