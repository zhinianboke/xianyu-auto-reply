"""
认证相关Schema定义

功能：
1. 定义JWT令牌格式（Token）
2. 定义登录请求和响应格式
3. 定义令牌验证响应格式
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class RefreshToken(BaseModel):
    refresh_token: str
    expires_at: datetime


class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    verification_code: Optional[str] = Field(default=None, min_length=4, max_length=64)
    # 极验滑动验证码参数
    geetest_challenge: Optional[str] = None
    geetest_validate: Optional[str] = None
    geetest_seccode: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    is_admin: Optional[bool] = None
    account_limit: Optional[int] = None


class VerifyResponse(BaseModel):
    authenticated: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    is_admin: Optional[bool] = None
    account_limit: Optional[int] = None

