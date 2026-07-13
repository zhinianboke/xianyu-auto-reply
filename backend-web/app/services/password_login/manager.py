"""
协议化账号密码登录 - 会话管理器（backend-web 本进程执行）

功能：
1. 管理协议登录会话（pl_ 前缀，带 owner_id 归属）
2. 启动后台编排任务、查询状态、取消会话
3. 与 websocket 浏览器登录并存：协议会话在本地，浏览器会话在 websocket

会话状态：processing / verification_required / success / failed
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any, Dict, Optional

from loguru import logger

from app.services.password_login.flow import run_protocol_login

# 协议会话 ID 前缀（用于路由区分：pl_ → 本地协议会话；无前缀 → websocket 浏览器会话）
SESSION_PREFIX = "pl_"
# 会话过期时间（秒）
_SESSION_TTL = 3600
# 终态（success/failed）会话读取后的宽限保留时长（秒）：
# 期内并发/重复轮询仍能稳定读到终态，避免"读一次即删除"导致后到的轮询读到
# not_found 而把成功误报为失败（success→not_found 竞态）。
_TERMINAL_GRACE = 30


class PasswordLoginManager:
    """协议化密码登录会话管理器（单例）。"""

    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}
        # 后台任务强引用，防止被 GC
        self._tasks: set = set()

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = []
        for sid, s in self.sessions.items():
            terminal_at = s.get("terminal_at")
            if terminal_at is not None:
                # 终态会话：宽限期后回收（宽限期内允许并发/重复轮询稳定读到终态）
                if now - terminal_at > _TERMINAL_GRACE:
                    expired.append(sid)
            elif now - s.get("timestamp", 0) > _SESSION_TTL:
                # 非终态会话：按总过期时间回收
                expired.append(sid)
        for sid in expired:
            self.sessions.pop(sid, None)

    def start(
        self, *, account_id: str, account: str, password: str,
        show_browser: bool, owner_id: int,
    ) -> str:
        """创建协议登录会话并启动后台编排任务，返回 pl_ 前缀的 session_id。

        同账号在途会话去重：若该账号已有进行中的会话（本人），直接复用其 session_id，
        避免重复点击触发多个 login.do/过滑块任务。
        """
        self._cleanup_expired()
        for sid, s in self.sessions.items():
            if (
                s.get("account_id") == account_id
                and s.get("owner_id") == owner_id
                and s.get("status") in ("processing", "verification_required")
                and not s.get("cancelled")
            ):
                logger.info(f"【{account_id}】已有在途协议登录会话，复用: {sid}")
                return sid

        session_id = SESSION_PREFIX + secrets.token_urlsafe(16)
        self.sessions[session_id] = {
            "owner_id": owner_id,
            "account_id": account_id,
            "status": "processing",
            "face_qr_url": None,
            "error": None,
            "message": "登录处理中，请稍候...",
            "fallback_session_id": None,
            "is_new_account": None,
            "cancelled": False,
            "timestamp": time.time(),
            "terminal_at": None,
        }
        session = self.sessions[session_id]

        async def _runner() -> None:
            try:
                await run_protocol_login(
                    session=session, account_id=account_id, account=account,
                    password=password, show_browser=show_browser,
                    owner_id=owner_id,
                )
            except Exception as e:  # 兜底：绝不让后台任务静默吞异常
                logger.exception(f"【{account_id}】协议登录后台任务异常")
                session["status"] = "failed"
                session["error"] = f"登录失败：{e}"

        task = asyncio.create_task(_runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.info(f"【{account_id}】协议密码登录会话已创建: {session_id}")
        return session_id

    def get_status(self, session_id: str, owner_id: int) -> Optional[Dict[str, Any]]:
        """查询会话状态（校验归属；非本人返回 None → 上层按 not_found 处理）。"""
        self._cleanup_expired()
        session = self.sessions.get(session_id)
        if not session or session.get("owner_id") != owner_id:
            return None
        result = {
            "status": session["status"],
            "face_qr_url": session.get("face_qr_url"),
            "error": session.get("error"),
            "message": session.get("message"),
            "account_id": session.get("account_id"),
            "is_new_account": session.get("is_new_account"),
            "fallback_session_id": session.get("fallback_session_id"),
        }
        # 终态会话不立即删除：首次读到终态时打宽限时间戳，宽限期内并发/重复轮询仍能
        # 稳定读到 success/failed（规避 success→not_found 竞态），到期后由 _cleanup_expired 回收
        if session["status"] in ("success", "failed") and session.get("terminal_at") is None:
            session["terminal_at"] = time.time()
        return result

    def cancel(self, session_id: str, owner_id: int) -> bool:
        """取消会话（校验归属）。"""
        session = self.sessions.get(session_id)
        if not session or session.get("owner_id") != owner_id:
            return False
        session["cancelled"] = True
        self.sessions.pop(session_id, None)
        return True

    def owns(self, session_id: str) -> bool:
        """是否为本地协议会话（按前缀判断，供路由分流）。"""
        return session_id.startswith(SESSION_PREFIX)


# 全局单例
password_login_manager = PasswordLoginManager()
