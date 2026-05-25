"""
在线聊天(新) WebSocket 路由

功能：
1. 前端通过 WebSocket 连接后端，订阅指定账号的 IM 实时消息推送
2. 当 IM 服务器推送新消息时，后端解密后实时转发给前端
3. 支持心跳保活（ping/pong）

与 chat_new.py 的 HTTP 接口配合使用：
- 前端先通过 HTTP 接口首次加载会话列表和消息
- 然后通过此 WebSocket 接收后续的实时更新
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.services.chat_new import get_im_session_manager

router = APIRouter(prefix="/chat-new")


@router.websocket("/ws/{account_id}")
async def chat_new_websocket(websocket: WebSocket, account_id: str):
    """
    在线聊天(新) WebSocket 连接

    前端连接后，会自动将此 WebSocket 注册到 ImSessionManager，
    当 IM 推送消息到达时，会实时转发给前端。

    推送消息格式示例：
    {
        "event": "new_message",
        "cid": "会话ID",
        "message": {
            "senderId": "发送者ID",
            "senderName": "发送者名称",
            "isSelf": false,
            "type": "text",
            "text": "消息内容",
            "images": [],
            "time": 1234567890000
        }
    }

    前端可发送的消息：
    - {"type": "ping"} 心跳检测

    Args:
        websocket: WebSocket 连接
        account_id: 账号ID
    """
    await websocket.accept()
    logger.info(f"【{account_id}】在线聊天 WebSocket 已连接")

    manager = get_im_session_manager()

    try:
        # 注册到管理器，开始接收推送
        await manager.register_ws_client(account_id, websocket)

        # 发送连接成功消息
        await websocket.send_text(json.dumps({
            "event": "connected",
            "account_id": account_id,
            "message": "WebSocket 已连接，等待实时消息推送",
        }, ensure_ascii=False))

        # 持续接收前端消息（心跳等）
        await _receive_loop(websocket, account_id)

    except WebSocketDisconnect:
        logger.info(f"【{account_id}】在线聊天 WebSocket 已断开")
    except Exception as e:
        logger.error(f"【{account_id}】在线聊天 WebSocket 异常: {e}")
    finally:
        await manager.unregister_ws_client(account_id, websocket)
        logger.info(f"【{account_id}】在线聊天 WebSocket 已清理")


async def _receive_loop(websocket: WebSocket, account_id: str):
    """
    接收前端 WebSocket 消息的循环

    目前支持：
    - ping: 心跳，回复 pong
    - 其他: 忽略

    Args:
        websocket: WebSocket 连接
        account_id: 账号ID（用于日志）
    """
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_text(
                    json.dumps({"event": "pong"}, ensure_ascii=False)
                )
            else:
                logger.info(
                    f"【{account_id}】收到前端未知消息类型: {msg_type}"
                )
    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.error(f"【{account_id}】接收前端消息异常: {e}")
        raise
