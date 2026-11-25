"""原业务任务循环，按原实现拆分，保留原任务执行和取消行为。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.services.scheduled_task_service import (
    TASK_CODE_AUTO_ORDER,
    TASK_CODE_AUTO_RELIST,
    TASK_CODE_DELIVERY_TIMEOUT,
    TASK_CODE_DM_SEND,
    TASK_CODE_IMAGE_CLEANUP,
    TASK_CODE_LISTING_MONITOR,
    TASK_CODE_SELLER_FILL,
    ScheduledTaskService,
)


class SchedulerBusinessLoops:
    """原业务任务循环，按原实现拆分，保留原任务执行和取消行为。"""

    async def _run_delivery_timeout_loop(self) -> None:
        """发货超时检测任务执行循环"""
        logger.info("[定时任务调度] 发货超时检测任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_DELIVERY_TIMEOUT)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_DELIVERY_TIMEOUT)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}

            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._delivery_timeout_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 发货超时检测任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 发货超时检测任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 发货超时检测任务等待被取消")
                break

        logger.info("[定时任务调度] 发货超时检测任务循环结束")


    async def _run_listing_monitor_loop(self) -> None:
        """商品监控任务执行循环"""
        logger.info("[定时任务调度] 商品监控任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_LISTING_MONITOR)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_LISTING_MONITOR)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}

            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._listing_monitor_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 商品监控任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 商品监控任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 商品监控任务等待被取消")
                break

        logger.info("[定时任务调度] 商品监控任务循环结束")


    async def _run_seller_fill_loop(self) -> None:
        """采集商品卖家ID补全任务执行循环"""
        logger.info("[定时任务调度] 采集商品卖家ID补全任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_SELLER_FILL)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_SELLER_FILL)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}

            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._seller_fill_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 采集商品卖家ID补全任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 采集商品卖家ID补全任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 采集商品卖家ID补全任务等待被取消")
                break

        logger.info("[定时任务调度] 采集商品卖家ID补全任务循环结束")


    async def _run_dm_send_loop(self) -> None:
        """采集商品发送私信任务执行循环"""
        logger.info("[定时任务调度] 采集商品发送私信任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_DM_SEND)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_DM_SEND)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}

            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._dm_send_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 采集商品发送私信任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 采集商品发送私信任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 采集商品发送私信任务等待被取消")
                break

        logger.info("[定时任务调度] 采集商品发送私信任务循环结束")


    async def _run_auto_order_loop(self) -> None:
        """采集商品自动下单任务执行循环"""
        logger.info("[定时任务调度] 采集商品自动下单任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_AUTO_ORDER)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_AUTO_ORDER)
            if not config:
                config = {"interval_seconds": 60, "enabled": True}

            interval = config.get("interval_seconds", 60)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._auto_order_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 采集商品自动下单任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 采集商品自动下单任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 采集商品自动下单任务等待被取消")
                break

        logger.info("[定时任务调度] 采集商品自动下单任务循环结束")


    async def _run_image_cleanup_loop(self) -> None:
        """图片清理任务执行循环"""
        logger.info("[定时任务调度] 图片清理任务循环开始")

        # 初始加载配置
        await self.reload_task_config(TASK_CODE_IMAGE_CLEANUP)

        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_IMAGE_CLEANUP)
            if not config:
                config = {"interval_seconds": 1200, "enabled": True}

            interval = config.get("interval_seconds", 1200)
            enabled = config.get("enabled", True)

            if enabled:
                try:
                    await self._image_cleanup_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] 图片清理任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] 图片清理任务执行异常: {e}")

            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[定时任务调度] 图片清理任务等待被取消")
                break

        logger.info("[定时任务调度] 图片清理任务循环结束")


    async def _run_auto_relist_loop(self) -> None:
        """商品自动续售唯一 runner 循环。"""
        logger.info("[定时任务调度] [自动续售] 商品自动续售任务循环开始")
        await self.reload_task_config(TASK_CODE_AUTO_RELIST)
        while self._running:
            config = ScheduledTaskService.get_cached_config(TASK_CODE_AUTO_RELIST) or {
                "interval_seconds": 30,
                "enabled": True,
            }
            if config.get("enabled", True):
                logger.info("[定时任务调度] [自动续售] 商品自动续售任务本轮开始")
                try:
                    await self._auto_relist_task.execute()
                except asyncio.CancelledError:
                    logger.info("[定时任务调度] [自动续售] 商品自动续售任务被取消")
                    break
                except Exception as exc:
                    logger.error(f"[定时任务调度] [自动续售] 商品自动续售任务执行异常: {exc}")
                finally:
                    logger.info("[定时任务调度] [自动续售] 商品自动续售任务本轮结束")
            try:
                await asyncio.sleep(max(5, int(config.get("interval_seconds", 30))))
            except asyncio.CancelledError:
                break
        logger.info("[定时任务调度] [自动续售] 商品自动续售任务循环结束")

