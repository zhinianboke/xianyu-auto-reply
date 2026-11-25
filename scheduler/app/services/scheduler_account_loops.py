"""原账号及维护任务循环，按原实现拆分，不改变原任务配置和执行逻辑。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.services.scheduled_task_service import (
    TASK_CODE_API_COOKIE_RENEW,
    TASK_CODE_CLOSE_NOTICE,
    TASK_CODE_COOKIES_REFRESH,
    TASK_CODE_DB_BACKUP,
    TASK_CODE_LOGIN_RENEW,
    TASK_CODE_RED_FLOWER,
    TASK_CODE_TOKEN_RENEWAL,
    ScheduledTaskService,
)


class SchedulerAccountLoops:
    """原账号及维护任务循环，按原实现拆分，不改变原任务配置和执行逻辑。"""

    async def _run_login_renew_loop(self) -> None:
        """登录续期任务执行循环"""
        logger.info("[定时任务调度] 登录续期任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_LOGIN_RENEW)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_LOGIN_RENEW)
            if not config:
                config = {"interval_seconds": 600, "enabled": True}
            
            interval = config.get("interval_seconds", 600)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._login_renew_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 登录续期任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 登录续期任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 登录续期任务等待被取消")
                break
        
        logger.info("[定时任务调度] 登录续期任务循环结束")


    async def _run_token_renewal_loop(self) -> None:
        """Token续期任务执行循环。"""
        logger.info("[定时任务调度] Token续期任务循环开始")

        await self.reload_task_config(TASK_CODE_TOKEN_RENEWAL)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_TOKEN_RENEWAL)
            if not config:
                config = {"interval_seconds": 20, "enabled": True}

            interval = config.get("interval_seconds", 20)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._token_renewal_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] Token续期任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] Token续期任务执行异常: {e}")

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] Token续期任务等待被取消")
                break

        logger.info("[定时任务调度] Token续期任务循环结束")


    async def _run_cookies_refresh_loop(self) -> None:
        """COOKIES续期任务执行循环"""
        logger.info("[定时任务调度] COOKIES续期任务循环开始")
        
        await self.reload_task_config(TASK_CODE_COOKIES_REFRESH)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_COOKIES_REFRESH)
            if not config:
                config = {"interval_seconds": 600, "enabled": True}
            
            interval = config.get("interval_seconds", 600)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._cookies_refresh_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] COOKIES续期任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] COOKIES续期任务执行异常: {e}")
            
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] COOKIES续期任务等待被取消")
                break
        
        logger.info("[定时任务调度] COOKIES续期任务循环结束")


    async def _run_api_cookie_renew_loop(self) -> None:
        """接口续期Cookies任务执行循环"""
        logger.info("[定时任务调度] 接口续期Cookies任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_API_COOKIE_RENEW)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_API_COOKIE_RENEW)
            if not config:
                config = {"interval_seconds": 600, "enabled": True}

            interval = config.get("interval_seconds", 600)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._api_cookie_renew_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 接口续期Cookies任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 接口续期Cookies任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 接口续期Cookies任务等待被取消")
                break

        logger.info("[定时任务调度] 接口续期Cookies任务循环结束")


    async def _run_close_notice_loop(self) -> None:
        """关闭账号消息通知任务执行循环"""
        logger.info("[定时任务调度] 关闭账号消息通知任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_CLOSE_NOTICE)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_CLOSE_NOTICE)
            if not config:
                config = {"interval_seconds": 600, "enabled": False}
            
            interval = config.get("interval_seconds", 600)
            enabled = config.get("enabled", False)
            
            if enabled:
                try:
                    await self._close_notice_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 关闭账号消息通知任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 关闭账号消息通知任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 关闭账号消息通知任务等待被取消")
                break
        
        logger.info("[定时任务调度] 关闭账号消息通知任务循环结束")


    async def _run_red_flower_loop(self) -> None:
        """求小红花任务执行循环"""
        logger.info("[定时任务调度] 求小红花任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_RED_FLOWER)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_RED_FLOWER)
            if not config:
                config = {"interval_seconds": 300, "enabled": False}
            
            interval = config.get("interval_seconds", 300)
            enabled = config.get("enabled", False)
            
            if enabled:
                try:
                    await self._red_flower_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 求小红花任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 求小红花任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 求小红花任务等待被取消")
                break
        
        logger.info("[定时任务调度] 求小红花任务循环结束")


    async def _run_db_backup_loop(self) -> None:
        """数据库备份任务执行循环"""
        logger.info("[定时任务调度] 数据库备份任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_DB_BACKUP)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_DB_BACKUP)
            if not config:
                config = {"interval_seconds": 3600, "enabled": True}

            interval = config.get("interval_seconds", 3600)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._db_backup_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 数据库备份任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 数据库备份任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 数据库备份任务等待被取消")
                break

        logger.info("[定时任务调度] 数据库备份任务循环结束")

