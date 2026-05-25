"""
推广返佣系统 - 安全模块

功能：
1. 密码哈希和验证（支持bcrypt和pbkdf2_sha256）
2. JWT令牌生成和解析
3. 访问令牌/刷新令牌创建
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Union

import bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if hashed_password.startswith("$2") and len(hashed_password) >= 4:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, Dict[str, Any]],
    expires_delta: timedelta | None = None,
) -> str:
    """创建访问令牌"""
    settings = get_settings()
    if isinstance(subject, str):
        to_encode: Dict[str, Any] = {"sub": subject}
    else:
        to_encode = subject.copy()
        to_encode.setdefault("sub", subject.get("sub"))

    expires_delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expire = datetime.now(tz=timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    subject: Union[str, Dict[str, Any]],
    expires_delta: timedelta | None = None,
) -> str:
    """创建刷新令牌"""
    settings = get_settings()
    if isinstance(subject, str):
        to_encode: Dict[str, Any] = {"sub": subject, "type": "refresh"}
    else:
        to_encode = subject.copy()
        to_encode.setdefault("sub", subject.get("sub"))
        to_encode["type"] = "refresh"

    expires_delta = expires_delta or timedelta(minutes=settings.refresh_token_expire_minutes)
    expire = datetime.now(tz=timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    """解码令牌"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    return payload
