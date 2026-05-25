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

from pydantic import BaseModel, ConfigDict


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

    - success: 业务是否成功，固定按用户全局规则统一返回 200 状态码
    - message: 提示信息，前端用于 toast 显示
    - data: 业务数据，可为 dict、list 或 None；为兼容历史调用，允许任意 JSON 结构
    """

    success: bool
    message: str | None = None
    data: Any | None = None

