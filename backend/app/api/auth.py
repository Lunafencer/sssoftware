from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import hash_password, verify_password, create_token, get_current_user
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

MIN_PASSWORD_LEN = 6


def _check_password(pw: str) -> None:
    if not pw or len(pw) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"密码长度不少于 {MIN_PASSWORD_LEN} 位")


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    role: str
    username: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/register", response_model=TokenOut)
def register(body: LoginIn, db: Session = Depends(get_db)):
    """FIX5：注册一律创建员工账户（worker），忽略前端传入的任何角色字段。"""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "用户名已存在")
    _check_password(body.password)
    u = User(username=body.username, password_hash=hash_password(body.password), role="worker", token_version=1)
    db.add(u); db.commit(); db.refresh(u)
    return TokenOut(access_token=create_token(u.username, u.role, u.token_version or 1), role=u.role, username=u.username)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == body.username).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "账号或密码错误")
    # FIX6 第 10 项：每次登录递增 token_version，使其他设备上的 token 立即失效（单点登录）
    u.token_version = (u.token_version or 1) + 1
    db.commit(); db.refresh(u)
    return TokenOut(access_token=create_token(u.username, u.role, u.token_version), role=u.role, username=u.username)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    """根据 token 回填当前用户信息（前端不再把用户资料写入 localStorage）。"""
    return {"id": user.id, "username": user.username, "role": user.role,
            "isDefaultAdmin": bool(user.is_default_admin)}


@router.put("/change-password")
def change_password(body: ChangePasswordIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    # FIX6 第 11 项：先校验旧密码，再按 id 精确锁定目标用户，避免误覆盖
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码不正确")
    _check_password(body.new_password)
    target = db.query(User).filter(User.id == user.id).first()
    if not target:
        raise HTTPException(404, "用户不存在")
    target.password_hash = hash_password(body.new_password)
    # FIX6 第 10 项：改密后递增 token_version，强制其他端重新登录
    target.token_version = (target.token_version or 1) + 1
    db.commit()
    import logging
    logging.getLogger(__name__).info(
        "[change-password] user_id=%s username=%s", target.id, target.username
    )
    return {"ok": True}
