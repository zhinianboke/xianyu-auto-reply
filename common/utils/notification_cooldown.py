"""通知发送占位和成功冷却，供同一进程的多线程及多个事件循环共享。"""
from __future__ import annotations

import time
from threading import Lock


class NotificationCooldown:
    """单账号通知状态；仅操作内存时持锁，发送期间不持有线程锁。"""

    def __init__(self) -> None:
        """初始化成功时间、正在发送的占位及保护状态的线程锁。"""
        self.last_sent: dict[str, float] = {}
        self._pending: dict[str, object] = {}
        self._lock = Lock()

    def reserve(self, key: str, cooldown: float) -> object | None:
        """按通知键申请发送；发送中或成功冷却未结束时返回None。

        Args:
            key: 聊天消息摘要或账号事件类型。
            cooldown: 成功发送后的冷却秒数。
        Returns:
            本次发送的唯一占位标记；重复触发返回None。
        """
        with self._lock:
            now = time.time()
            # 只清理聊天成功记录，账号通知可能有更长的冷却。
            expired = [key for key, sent_at in self.last_sent.items() if key.startswith("chat:") and now - sent_at > 3600]
            for expired_key in expired:
                self.last_sent.pop(expired_key, None)
            if key in self._pending:
                return None
            sent_at = self.last_sent.get(key)
            if sent_at is not None and now - sent_at < cooldown:
                return None
            reservation = object()
            self._pending[key] = reservation
            return reservation

    def finish(self, key: str, reservation: object | None, sent: bool) -> None:
        """结束本次发送，成功才开始冷却，失败或取消只释放占位。

        Args:
            key: 申请发送时使用的通知键。
            reservation: 本次唯一占位；未取得占位则不修改状态。
            sent: 是否至少有一个渠道确认发送成功。
        Returns:
            无返回值。
        """
        with self._lock:
            if reservation is None or self._pending.get(key) is not reservation:
                return
            self._pending.pop(key)
            if sent:
                self.last_sent[key] = time.time()


_registry_lock = Lock()
_cooldowns: dict[str, NotificationCooldown] = {}


def get_notification_cooldown(account_id: str) -> NotificationCooldown:
    """按账号返回共享状态；参数为账号标识，返回进程内唯一的冷却实例。"""
    with _registry_lock:
        if account_id not in _cooldowns:
            _cooldowns[account_id] = NotificationCooldown()
        return _cooldowns[account_id]
