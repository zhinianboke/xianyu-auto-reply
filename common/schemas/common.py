"""
通用Schema定义

功能：
1. 定义统一的API响应格式（ApiResponse）
2. 提供时间戳Schema基类
3. 定义健康检查响应格式
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class TimestampSchema(BaseModel):
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str


class ApiResponse(BaseModel):
    """统一接口响应模型。

    - success: 业务是否成功，HTTP 状态码固定为 200
    - code: 业务状态码，成功固定为 200，失败由具体接口返回业务错误码
    - message: 提示信息，前端用于 toast 显示
    - data: 业务数据，可为 dict、list 或 None；为兼容历史调用，允许任意 JSON 结构
    """

    success: bool
    code: int = 200
    message: str | None = None
    data: Any | None = None

    @model_validator(mode="before")
    @classmethod
    def fill_default_code(cls, values: Any) -> Any:
        """兼容旧调用点：未显式传业务码时按成功状态补齐默认码。"""
        if isinstance(values, dict) and values.get("code") is None:
            normalized = dict(values)
            normalized["code"] = 200 if normalized.get("success") else 40001
            return normalized
        return values

