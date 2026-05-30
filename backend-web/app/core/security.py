"""
安全模块（backend-web 薄封装层）

实现统一收敛到 ``common.utils.security``，本模块仅做两件事：
1. 密码哈希/校验：直接复用 common 实现（无配置依赖）。
2. JWT 令牌签发/解析：委托 common 实现，但显式注入 **backend-web 自身的配置实例**
   （``app.core.config.get_settings()``）——该实例的 ``jwt_secret_key`` 在服务启动时
   由 ``jwt_secret_service.ensure_jwt_secret_key`` 从数据库托管写回，必须使用它才能保证
   签名/验签密钥与数据库一致。

> 注意：不要改回直接用 common 的 ``get_settings()``，那是另一个配置实例（BaseConfig），
> 不会被数据库密钥写回，会导致 JWT 签名密钥错误、用户登录态全部失效。
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Union

from app.core.config import get_settings
from common.utils import security as _common_security

# 密码相关函数无配置依赖，直接复用 common 实现
verify_password = _common_security.verify_password
get_password_hash = _common_security.get_password_hash


def create_access_token(
    subject: Union[str, Dict[str, Any]],
    expires_delta: timedelta | None = None,
) -> str:
    """创建访问令牌（使用 backend-web 配置实例，密钥由数据库托管）"""
    return _common_security.create_access_token(
        subject, expires_delta=expires_delta, settings=get_settings()
    )


def create_refresh_token(
    subject: Union[str, Dict[str, Any]],
    expires_delta: timedelta | None = None,
) -> str:
    """创建刷新令牌（使用 backend-web 配置实例，密钥由数据库托管）"""
    return _common_security.create_refresh_token(
        subject, expires_delta=expires_delta, settings=get_settings()
    )


def decode_token(token: str) -> Dict[str, Any]:
    """解析令牌（使用 backend-web 配置实例，密钥由数据库托管）"""
    return _common_security.decode_token(token, settings=get_settings())
