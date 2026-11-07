"""公开在线安装的访客范围：无需登录，用随机浏览器会话标识隔离任务日志。"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException


async def get_online_install_scope(
    session_id: Annotated[UUID | None, Header(alias="X-Install-Session")] = None,
) -> str:
    """返回本次浏览器会话独立的任务范围，不读取登录令牌或用户数据库。

    Args:
        session_id: 页面为浏览器会话生成的随机 UUID，提交和日志读取时保持一致。
    Returns:
        访客任务范围字符串；缺失标识时返回中文业务错误。
    """
    if session_id is None:
        raise HTTPException(status_code=400, detail="安装会话标识缺失，请刷新在线安装页面后重试")
    return f"visitor:{session_id}"
