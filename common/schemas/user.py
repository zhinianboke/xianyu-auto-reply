from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from common.models.user import UserRole, UserStatus
from common.schemas.common import TimestampSchema


class UserBase(BaseModel):
    username: str = Field(max_length=64)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=32)


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)
    verification_code: Optional[str] = Field(default=None, max_length=6, description="邮箱验证码")


class AdminUserCreate(UserBase):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.MEMBER
    status: UserStatus = UserStatus.ACTIVE
    account_limit: Optional[int] = Field(default=None, ge=1)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=32)
    status: Optional[UserStatus] = None
    role: Optional[UserRole] = None


class AdminUserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=64)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=32)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    status: Optional[UserStatus] = None
    role: Optional[UserRole] = None
    account_limit: Optional[int] = Field(default=None, ge=1)


class UserPublic(TimestampSchema, UserBase):
    id: int
    role: UserRole
    status: UserStatus
    account_limit: Optional[int] = None
    external_id: Optional[str] = None
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
