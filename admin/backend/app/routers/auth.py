"""管理后台登录接口：/api/auth/login、/api/auth/me、/api/auth/change-password。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import (
    TOKEN_TTL_HOURS,
    create_token,
    get_current_admin,
    hash_password,
    verify_password,
)
from app.deps import get_db
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user.last_login = datetime.utcnow()
    db.commit()
    return {
        "token": create_token(user.username),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_HOURS * 3600,
        "username": user.username,
    }


@router.get("/me")
def me(user: User = Depends(get_current_admin)):
    return {
        "username": user.username,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True, "message": "密码已更新，请用新密码重新登录"}
