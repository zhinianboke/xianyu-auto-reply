from __future__ import annotations

from pydantic import BaseModel


class SystemSettingUpdate(BaseModel):
    value: str
    description: str | None = None


class RemoteTokenTestRequest(BaseModel):
    remote_url: str
    remote_secret_key: str


class RemotePasswordLoginTestRequest(BaseModel):
    remote_url: str
    remote_secret_key: str

