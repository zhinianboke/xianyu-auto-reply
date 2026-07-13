"""
协议化账号密码登录服务模块（backend-web）

提供纯 API（不依赖浏览器）的账号密码登录：直接成功 / 触发人脸出二维码 / 登录失败给原因，
过滑块委托远程或 websocket 本机真实鼠标；滑块失败时继续协议链路重试。
"""
from __future__ import annotations

from app.services.password_login.manager import (
    SESSION_PREFIX,
    PasswordLoginManager,
    password_login_manager,
)

__all__ = ["PasswordLoginManager", "password_login_manager", "SESSION_PREFIX"]
