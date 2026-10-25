"""Cookie 管理器的账号配置加载、启动调度和停止流程。"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models import XYAccount


class CookieManagerLifecycle:
    """复用 CookieManager 的内存配置和任务锁管理账号生命周期。"""

    async def load_from_db(self, db_session: AsyncSession):
        """从指定数据库会话加载账号配置；失败时抛出异常供启动状态展示。"""
        if self._loading_account_changes is None:
            self._loading_account_changes = set()
        try:
            logger.info("从数据库加载Cookie配置...")
            result = await db_session.execute(select(
                XYAccount.account_id, XYAccount.cookie, XYAccount.status,
                XYAccount.owner_id, XYAccount.auto_confirm,
            ))
            for account in result.all():
                cookie_id = account.account_id
                if cookie_id in self._loading_account_changes:
                    continue
                if cookie_id in self.cookies:
                    logger.warning(f"检测到重复账号ID: {cookie_id}，将使用最新加载的记录覆盖内存状态")
                self.cookies[cookie_id] = account.cookie or ""
                self.cookie_status[cookie_id] = account.status == "active"
                self.user_ids[cookie_id] = account.owner_id
                self.auto_confirm_settings[cookie_id] = account.auto_confirm
                self.keywords.setdefault(cookie_id, [])
            logger.info(
                f"从数据库加载了 {len(self.cookies)} 个Cookie、"
                f"{len(self.cookie_status)} 个状态记录"
            )
        except Exception:
            logger.exception("从数据库加载Cookie配置失败")
            raise
        finally:
            self._loading_account_changes = None

    async def start_all_tasks(self):
        """按快照逐个调度启用账号，并重新检查状态以兼容启动期间的账号操作。"""
        cookie_ids = [key for key, enabled in self.cookie_status.items() if enabled]
        self.startup_total = len(cookie_ids)
        self.startup_processed = 0
        for cookie_id in cookie_ids:
            if self.cookie_status.get(cookie_id, False) and cookie_id in self.cookies:
                await self._add_cookie_async(
                    cookie_id, self.cookies[cookie_id], self.user_ids.get(cookie_id),
                    restart_existing=False,
                )
            self.startup_processed += 1
            # 保留原有错峰间隔；后台调度让出事件循环，HTTP 可同时响应。
            await asyncio.sleep(0.05)

    async def stop_all_tasks(self):
        """停止当前所有账号任务，沿用账号级停止和资源清理逻辑。"""
        for cookie_id in list(self.tasks):
            await self._stop_task_async(cookie_id)

    async def start(self):
        """捕获事件循环，加载账号配置并调度启用账号；失败时抛出异常。"""
        try:
            logger.info("CookieManager启动中...")
            if self.loop is None:
                self.loop = asyncio.get_running_loop()
                logger.info(f"CookieManager已捕获事件循环: {self.loop}")
            async with async_session_maker() as db_session:
                await self.load_from_db(db_session)
            await self.start_all_tasks()
            logger.info(f"CookieManager启动完成,已调度 {len(self.tasks)} 个账号任务")
        except Exception:
            logger.exception("CookieManager启动失败")
            raise

    async def stop(self):
        """停止所有账号任务；失败时抛出异常供生命周期管理记录。"""
        try:
            logger.info("CookieManager停止中...")
            await self.stop_all_tasks()
            logger.info("CookieManager已停止")
        except Exception:
            logger.exception("CookieManager停止失败")
            raise
