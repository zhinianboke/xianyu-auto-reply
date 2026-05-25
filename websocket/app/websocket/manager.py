"""
WebSocket连接管理器

功能：
1. 管理WebSocket连接的注册和注销
2. 支持单播和广播消息发送
3. 维护活跃连接集合
"""
from __future__ import annotations

from typing import Set

from fastapi import WebSocket


class ConnectionManager:
    """WebSocket连接管理器 - 管理前端WebSocket连接"""

    def __init__(self) -> None:
        self.connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """连接WebSocket"""
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """断开WebSocket连接"""
        self.connections.discard(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """发送个人消息"""
        await websocket.send_text(message)

    async def broadcast(self, message: str) -> None:
        """广播消息给所有连接"""
        for connection in list(self.connections):
            try:
                await connection.send_text(message)
            except Exception:
                # 连接已断开,移除
                self.connections.discard(connection)


# 全局管理器实例
manager = ConnectionManager()
