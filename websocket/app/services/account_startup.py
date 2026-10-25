"""管理账号后台启动任务，提供进度反馈并在应用退出时取消调度。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from loguru import logger

from app.services.xianyu.cookie_manager import CookieManager


class AccountStartup:
    """持有账号启动任务和状态，HTTP 存活检查无需等待账号加载。"""

    def __init__(self, manager: CookieManager, enabled: bool):
        """保存账号管理器与自动启动配置，初始化启动状态。"""
        self.manager = manager
        self.enabled = enabled
        self.task: asyncio.Task | None = None
        self.status = "starting" if enabled else "disabled"
        self.error = ""

    async def _start(self):
        """后台执行账号启动，记录真实失败原因和完整异常堆栈。"""
        try:
            # 先交还事件循环，让 ASGI 启动完成事件可以立即发送。
            await asyncio.sleep(0)
            await self.manager.start()
            self.status = "completed"
            logger.info("CookieManager后台启动完成，账号任务已调度")
        except asyncio.CancelledError:
            self.status = "cancelled"
            logger.info("CookieManager后台启动已取消")
            raise
        except Exception as exc:
            self.status = "failed"
            self.error = f"账号自动启动失败：{exc}"
            logger.exception(self.error)

    def get_status(self) -> dict:
        """返回调度状态、中文说明和处理进度；完成调度不代表全部账号已连接。"""
        total = self.manager.startup_total
        processed = self.manager.startup_processed
        if self.status == "starting":
            message = (
                f"账号正在后台启动，已处理 {processed}/{total} 个"
                if total else "账号配置正在后台加载"
            )
        elif self.status == "completed":
            message = f"账号启动调度完成，共处理 {processed} 个，连接状态请查看账号管理"
        elif self.status == "failed":
            message = self.error
        elif self.status == "disabled":
            message = "账号自动启动已关闭"
        else:
            message = "账号启动调度已取消"
        return {
            "status": self.status,
            "message": message,
            "total": total,
            "processed": processed,
        }

    @asynccontextmanager
    async def run(self):
        """启动后台任务并立即交还应用；退出时先取消调度，再停止账号任务。"""
        if self.enabled:
            # 在 HTTP 接收请求前记录账号操作，覆盖后台任务尚未开始加载的窗口。
            self.manager._loading_account_changes = set()
            self.task = asyncio.create_task(self._start(), name="cookie-manager-startup")
            logger.info("CookieManager后台启动任务已创建，HTTP服务无需等待账号调度")
        else:
            logger.info("已禁用自动启动WebSocket连接（AUTO_START_WEBSOCKET=false）")
        try:
            yield
        finally:
            if self.task is not None:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    self.status = "cancelled"
                    logger.info("CookieManager后台启动任务已回收")
            self.manager._loading_account_changes = None
            try:
                await self.manager.stop()
                logger.info("CookieManager已停止")
            except Exception:
                logger.exception("CookieManager停止失败")
