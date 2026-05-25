from __future__ import annotations

from pydantic import BaseModel


class SystemSettingUpdate(BaseModel):
    value: str
    description: str | None = None

