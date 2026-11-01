from __future__ import annotations

from pydantic import BaseModel


class SystemSettingUpdate(BaseModel):
    value: str
    description: str | None = None


class SystemSettingsBatchUpdate(BaseModel):
    """同一事务中批量更新多个系统设置。"""

    settings: dict[str, SystemSettingUpdate]


class RemoteTokenTestRequest(BaseModel):
    remote_url: str
    remote_secret_key: str


class RemotePasswordLoginTestRequest(BaseModel):
    remote_url: str
    remote_secret_key: str

