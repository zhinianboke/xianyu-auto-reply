"""原订单及采集任务循环，按原实现拆分，配置与业务执行行为保持一致。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.services.scheduled_task_service import (
    TASK_CODE_CLEANUP_BROWSER_DATA,
    TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA,
    TASK_CODE_DAY_SWITCH,
    TASK_CODE_FETCH_ITEMS,
    TASK_CODE_FETCH_ORDERS,
    TASK_CODE_FETCH_PENDING_ORDERS,
    TASK_CODE_FETCH_REFUND_ORDERS,
    TASK_CODE_POLISH,
    TASK_CODE_RATE,
    TASK_CODE_REDELIVERY,
    ScheduledTaskService,
)


class SchedulerOrderLoops:
    """原订单及采集任务循环，按原实现拆分，配置与业务执行行为保持一致。"""

    async def _run_redelivery_loop(self) -> None:
        """补发货任务执行循环"""
        logger.info("[定时任务调度] 补发货任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_REDELIVERY)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_REDELIVERY)
            if not config:
                config = {"interval_seconds": 5, "enabled": True}
            
            interval = config.get("interval_seconds", 5)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._redelivery_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 补发货任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 补发货任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 补发货任务等待被取消")
                break
        
        logger.info("[定时任务调度] 补发货任务循环结束")


    async def _run_rate_loop(self) -> None:
        """补评价任务执行循环"""
        logger.info("[定时任务调度] 补评价任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_RATE)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_RATE)
            if not config:
                config = {"interval_seconds": 20, "enabled": True}
            
            interval = config.get("interval_seconds", 20)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._rate_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 补评价任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 补评价任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 补评价任务等待被取消")
                break
        
        logger.info("[定时任务调度] 补评价任务循环结束")


    async def _run_polish_loop(self) -> None:
        """擦亮任务执行循环"""
        logger.info("[定时任务调度] 擦亮任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_POLISH)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_POLISH)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}
            
            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._polish_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 擦亮任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 擦亮任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 擦亮任务等待被取消")
                break
        
        logger.info("[定时任务调度] 擦亮任务循环结束")


    async def _run_day_switch_loop(self) -> None:
        """平台日切换任务执行循环"""
        logger.info("[定时任务调度] 平台日切换任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_DAY_SWITCH)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_DAY_SWITCH)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}
            
            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._day_switch_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 平台日切换任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 平台日切换任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 平台日切换任务等待被取消")
                break
        
        logger.info("[定时任务调度] 平台日切换任务循环结束")


    async def _run_cleanup_browser_data_loop(self) -> None:
        """清理被禁用账号浏览器数据任务执行循环"""
        logger.info("[定时任务调度] 清理被禁用账号浏览器数据任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_CLEANUP_BROWSER_DATA)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_CLEANUP_BROWSER_DATA)
            if not config:
                config = {"interval_seconds": 600, "enabled": True}
            
            interval = config.get("interval_seconds", 600)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._cleanup_browser_data_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 清理被禁用账号浏览器数据任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 清理被禁用账号浏览器数据任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 清理被禁用账号浏览器数据任务等待被取消")
                break
        
        logger.info("[定时任务调度] 清理被禁用账号浏览器数据任务循环结束")


    async def _run_cleanup_unconfigured_browser_data_loop(self) -> None:
        """清理未配置账号密码的浏览器数据任务执行循环"""
        logger.info("[定时任务调度] 清理未配置账号密码的浏览器数据任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA)
            if not config:
                config = {"interval_seconds": 10800, "enabled": False}

            interval = config.get("interval_seconds", 10800)
            enabled = config.get("enabled", False)

            if enabled:
                try:
                    await self._cleanup_unconfigured_browser_data_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 清理未配置账号密码的浏览器数据任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 清理未配置账号密码的浏览器数据任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 清理未配置账号密码的浏览器数据任务等待被取消")
                break

        logger.info("[定时任务调度] 清理未配置账号密码的浏览器数据任务循环结束")


    async def _run_fetch_orders_loop(self) -> None:
        """获取闲鱼订单任务执行循环"""
        logger.info("[定时任务调度] 获取闲鱼订单任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(TASK_CODE_FETCH_ORDERS)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_ORDERS)
            if not config:
                config = {"interval_seconds": 600, "enabled": True}
            
            interval = config.get("interval_seconds", 600)
            enabled = config.get("enabled", True)
            
            if enabled:
                try:
                    await self._fetch_orders_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 获取闲鱼订单任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 获取闲鱼订单任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 获取闲鱼订单任务等待被取消")
                break
        
        logger.info("[定时任务调度] 获取闲鱼订单任务循环结束")


    async def _run_fetch_pending_orders_loop(self) -> None:
        """获取待发货订单任务执行循环"""
        logger.info("[定时任务调度] 获取待发货订单任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_FETCH_PENDING_ORDERS)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_PENDING_ORDERS)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}

            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._fetch_pending_orders_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 获取待发货订单任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 获取待发货订单任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 获取待发货订单任务等待被取消")
                break

        logger.info("[定时任务调度] 获取待发货订单任务循环结束")


    async def _run_fetch_refund_orders_loop(self) -> None:
        """获取退款订单任务执行循环"""
        logger.info("[定时任务调度] 获取退款订单任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_FETCH_REFUND_ORDERS)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_REFUND_ORDERS)
            if not config:
                config = {"interval_seconds": 120, "enabled": True}

            interval = config.get("interval_seconds", 120)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._fetch_refund_orders_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 获取退款订单任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 获取退款订单任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 获取退款订单任务等待被取消")
                break

        logger.info("[定时任务调度] 获取退款订单任务循环结束")


    async def _run_fetch_items_loop(self) -> None:
        """获取闲鱼商品任务执行循环"""
        logger.info("[定时任务调度] 获取闲鱼商品任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_FETCH_ITEMS)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_ITEMS)
            if not config:
                config = {"interval_seconds": 1200, "enabled": True}

            interval = config.get("interval_seconds", 1200)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._fetch_items_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 获取闲鱼商品任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 获取闲鱼商品任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 获取闲鱼商品任务等待被取消")
                break

        logger.info("[定时任务调度] 获取闲鱼商品任务循环结束")

