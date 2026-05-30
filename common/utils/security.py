"""
安全工具模块

功能：
1. 密码哈希和验证（支持bcrypt和pbkdf2_sha256）
2. JWT令牌生成和解析
3. 访问令牌创建
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Union

import bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext

from common.core.config import get_settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# 秘钥生成可用字符集：大小写字母 + 数字
_SECRET_KEY_ALPHABET = string.ascii_letters + string.digits


def generate_secret_key(length: int = 32) -> str:
    """生成随机分销/提货秘钥（大小写字母+数字）

    使用 secrets 保证密码学随机性，全局唯一性由数据库 UNIQUE 约束 + 生成端重试保证。

    Args:
        length: 秘钥长度，默认 32 位

    Returns:
        随机秘钥字符串
    """
    return ''.join(secrets.choice(_SECRET_KEY_ALPHABET) for _ in range(length))


# 已知的弱/占位 JWT 密钥（与 deploy.sh / update.sh 中的 WEAK_JWT_KEYS 保持一致）。
# 命中其一、或为空、或长度过短，均视为不安全，需要自动替换为随机值。
WEAK_JWT_SECRETS: frozenset[str] = frozenset({
    "change-me",
    "change-me-in-production-please",
    "your-secret-key",
    "your-secret-key-change-me-to-a-random-string",
    "changeme",
    "secret",
})

# 低于该长度的密钥视为过弱
_MIN_JWT_SECRET_LENGTH = 16


def is_weak_jwt_secret(secret: str | None) -> bool:
    """判断 JWT 密钥是否为弱/默认值。

    Args:
        secret: 待校验的密钥字符串

    Returns:
        True 表示密钥为空、过短或命中已知占位值（不安全）；False 表示为可接受的强密钥。
    """
    if not secret or len(secret) < _MIN_JWT_SECRET_LENGTH:
        return True
    return secret in WEAK_JWT_SECRETS


def generate_jwt_secret() -> str:
    """生成一个强随机 JWT 密钥（64位十六进制，等价于 32 字节熵）。"""
    return secrets.token_hex(32)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if hashed_password.startswith("$2") and len(hashed_password) >= 4:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, Dict[str, Any]],
    expires_delta: timedelta | None = None,
    settings: Any = None,
) -> str:
    """创建访问令牌

    Args:
        subject: 令牌主体（字符串或包含 sub 的字典）
        expires_delta: 过期时长，默认取配置的 access_token_expire_minutes
        settings: 配置实例。默认用 common 配置；backend-web 等服务应传入各自的
            配置实例（其 jwt_secret_key 在启动时已由数据库托管写回），以保证签名密钥一致。
    """
    settings = settings or get_settings()
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
    settings: Any = None,
) -> str:
    """创建刷新令牌

    Args:
        subject: 令牌主体（字符串或包含 sub 的字典）
        expires_delta: 过期时长，默认取配置的 refresh_token_expire_minutes
        settings: 配置实例。默认用 common 配置；backend-web 等服务应传入各自的配置实例。
    """
    settings = settings or get_settings()
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


def decode_token(token: str, settings: Any = None) -> Dict[str, Any]:
    """解析令牌

    Args:
        token: 待解析的 JWT 字符串
        settings: 配置实例。默认用 common 配置；backend-web 等服务应传入各自的配置实例。
    """
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    return payload
