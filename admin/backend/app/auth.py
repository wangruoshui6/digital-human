"""管理后台鉴权：bcrypt 密码哈希 + JWT 签发校验 + 默认管理员初始化。

设计要点：
- 密码用 bcrypt 加盐哈希存库，数据库里看不到明文
- 登录成功签发 HS256 JWT，有效期 8 小时，前端放 localStorage
- JWT 密钥首次启动随机生成，存 admin/backend/data/jwt_secret.txt（该目录已在 .gitignore）
- 管理接口通过 FastAPI 依赖注入统一鉴权，未认证返回 401
"""
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.deps import get_db
from app.models import User

# ── 路径与密钥 ──
_BASE_DIR = Path(__file__).resolve().parent.parent      # admin/backend
_DATA_DIR = _BASE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_SECRET_FILE = _DATA_DIR / "jwt_secret.txt"
_CRED_FILE = _DATA_DIR / "admin_credentials.txt"

TOKEN_TTL_HOURS = 8
ALGORITHM = "HS256"


def _load_secret() -> str:
    if _SECRET_FILE.exists():
        s = _SECRET_FILE.read_text(encoding="utf-8").strip()
        if s:
            return s
    s = secrets.token_hex(32)
    _SECRET_FILE.write_text(s, encoding="utf-8")
    return s


JWT_SECRET = _load_secret()


# ── 密码哈希 ──
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ──
def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])


# ── 依赖注入：要求有效管理员身份 ──
def get_current_admin(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或凭据缺失",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的登录凭据")

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="账号不存在或已被移除")
    return user


# ── 首次启动初始化默认管理员 ──
def ensure_default_admin(username: str = "admin") -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        password = secrets.token_urlsafe(12)      # 约 16 位随机强密码
        db.add(User(username=username, password_hash=hash_password(password)))
        db.commit()
        _CRED_FILE.write_text(
            "管理后台初始账号（仅本次生成，登录后可改）\n"
            f"用户名：{username}\n"
            f"密码：{password}\n"
            "文件位置：admin/backend/data/admin_credentials.txt（已加入 .gitignore，不会上传 Git）\n",
            encoding="utf-8",
        )
        print("=" * 56, flush=True)
        print("[AUTH] 已生成默认管理员账号", flush=True)
        print(f"[AUTH] 用户名: {username}", flush=True)
        print(f"[AUTH] 密码  : {password}", flush=True)
        print(f"[AUTH] 已写入 {_CRED_FILE}", flush=True)
        print("=" * 56, flush=True)
    finally:
        db.close()
