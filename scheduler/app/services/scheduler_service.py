"""
定时任务调度服务

功能：
1. 管理定时任务的启动和停止
2. 从数据库读取任务配置（间隔时间、是否启用）
3. 支持动态更新任务配置（实时生效）
4. 定时补发货任务
5. 定时补评价任务
"""
from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from app.services.scheduler.redelivery_task import RedeliveryTask
from app.services.scheduler.rate_task import RateTask
from app.services.scheduler.polish_task import polish_task_service
from app.services.scheduler.day_switch_task import day_switch_task_service
from app.services.scheduler.cleanup_browser_data_task import cleanup_browser_data_task_service
from app.services.scheduler.fetch_orders_task import (
    fetch_orders_task_service,
    fetch_pending_orders_task_service,
    fetch_refund_orders_task_service,
)
from app.services.scheduler.fetch_items_task import fetch_items_task_service
from app.services.scheduler.login_renew_task import login_renew_task_service
from app.services.scheduler.cookies_refresh_task import cookies_refresh_task_service
from app.services.scheduler.api_cookie_renew_task import api_cookie_renew_task_service
from app.services.scheduler.close_notice_task import close_notice_task_service
from app.services.scheduler.red_flower_task import RedFlowerTask
from app.services.scheduler.db_backup_task import db_backup_task_service
from app.services.scheduler.delivery_timeout_task import delivery_timeout_task_service
from app.services.scheduler.listing_monitor_task import listing_monitor_task_service
from app.services.scheduler.seller_fill_task import seller_fill_task_service
from app.services.scheduler.dm_send_task import dm_send_task_service
from app.services.scheduler.auto_order_task import auto_order_task_service
from app.services.scheduled_task_service import (
    ScheduledTaskService,
    TASK_CODE_REDELIVERY,
    TASK_CODE_RATE,
    TASK_CODE_POLISH,
    TASK_CODE_DAY_SWITCH,
    TASK_CODE_CLEANUP_BROWSER_DATA,
    TASK_CODE_FETCH_ORDERS,
    TASK_CODE_FETCH_PENDING_ORDERS,
    TASK_CODE_FETCH_REFUND_ORDERS,
    TASK_CODE_FETCH_ITEMS,
    TASK_CODE_LOGIN_RENEW,
    TASK_CODE_COOKIES_REFRESH,
    TASK_CODE_API_COOKIE_RENEW,
    TASK_CODE_CLOSE_NOTICE,
    TASK_CODE_RED_FLOWER,
    TASK_CODE_DB_BACKUP,
    TASK_CODE_DELIVERY_TIMEOUT,
    TASK_CODE_LISTING_MONITOR,
    TASK_CODE_SELLER_FILL,
    TASK_CODE_DM_SEND,
    TASK_CODE_AUTO_ORDER,
)
from common.db.session import async_session_maker


class SchedulerService:
    """定时任务调度服务 - 支持从数据库读取配置并动态更新"""
    
    _instance: Optional["SchedulerService"] = None
    
    def __init__(self):
        self._running = False
        self._redelivery_task_handle: Optional[asyncio.Task] = None
        self._rate_task_handle: Optional[asyncio.Task] = None
        self._polish_task_handle: Optional[asyncio.Task] = None
        self._day_switch_task_handle: Optional[asyncio.Task] = None
        self._cleanup_browser_data_task_handle: Optional[asyncio.Task] = None
        self._fetch_orders_task_handle: Optional[asyncio.Task] = None
        self._fetch_pending_orders_task_handle: Optional[asyncio.Task] = None
        self._fetch_refund_orders_task_handle: Optional[asyncio.Task] = None
        self._fetch_items_task_handle: Optional[asyncio.Task] = None
        self._login_renew_task_handle: Optional[asyncio.Task] = None
        self._cookies_refresh_task_handle: Optional[asyncio.Task] = None
        self._api_cookie_renew_task_handle: Optional[asyncio.Task] = None
        self._close_notice_task_handle: Optional[asyncio.Task] = None
        self._red_flower_task_handle: Optional[asyncio.Task] = None
        self._db_backup_task_handle: Optional[asyncio.Task] = None
        self._delivery_timeout_task_handle: Optional[asyncio.Task] = None
        self._listing_monitor_task_handle: Optional[asyncio.Task] = None
        self._seller_fill_task_handle: Optional[asyncio.Task] = None
        self._dm_send_task_handle: Optional[asyncio.Task] = None
        self._auto_order_task_handle: Optional[asyncio.Task] = None
        self._redelivery_task = RedeliveryTask()
        self._rate_task = RateTask()
        self._polish_task = polish_task_service
        self._day_switch_task = day_switch_task_service
        self._cleanup_browser_data_task = cleanup_browser_data_task_service
        self._fetch_orders_task = fetch_orders_task_service
        self._fetch_pending_orders_task = fetch_pending_orders_task_service
        self._fetch_refund_orders_task = fetch_refund_orders_task_service
        self._fetch_items_task = fetch_items_task_service
        self._login_renew_task = login_renew_task_service
        self._cookies_refresh_task = cookies_refresh_task_service
        self._api_cookie_renew_task = api_cookie_renew_task_service
        self._close_notice_task = close_notice_task_service
        self._red_flower_task = RedFlowerTask()
        self._db_backup_task = db_backup_task_service
        self._delivery_timeout_task = delivery_timeout_task_service
        self._listing_monitor_task = listing_monitor_task_service
        self._seller_fill_task = seller_fill_task_service
        self._dm_send_task = dm_send_task_service
        self._auto_order_task = auto_order_task_service
    
    @classmethod
    def get_instance(cls) -> "SchedulerService":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def reload_task_config(self, task_code: str) -> None:
        """
        重新加载指定任务的配置（用于配置更新后刷新）
        
        Args:
            task_code: 任务代码
        """
        try:
            async with async_session_maker() as session:
                service = ScheduledTaskService(session)
                config = await service.load_task_config(task_code)
                logger.info(
                    f"[定时任务调度] 任务配置已更新 {task_code}: "
                    f"间隔={config['interval_seconds']}秒, 启用={config['enabled']}"
                )
        except Exception as e:
            logger.error(f"[定时任务调度] 重新加载任务配置失败 {task_code}: {e}")
    
    async def reload_all_configs(self) -> None:
        """重新加载所有任务配置"""
        for task_code in [TASK_CODE_REDELIVERY, TASK_CODE_RATE, TASK_CODE_POLISH, TASK_CODE_DAY_SWITCH, TASK_CODE_CLEANUP_BROWSER_DATA, TASK_CODE_FETCH_ORDERS, TASK_CODE_FETCH_PENDING_ORDERS, TASK_CODE_FETCH_REFUND_ORDERS, TASK_CODE_FETCH_ITEMS, TASK_CODE_LOGIN_RENEW, TASK_CODE_COOKIES_REFRESH, TASK_CODE_API_COOKIE_RENEW, TASK_CODE_CLOSE_NOTICE, TASK_CODE_RED_FLOWER, TASK_CODE_DB_BACKUP]:
            await self.reload_task_config(task_code)
        for task_code in [TASK_CODE_DELIVERY_TIMEOUT, TASK_CODE_LISTING_MONITOR, TASK_CODE_SELLER_FILL, TASK_CODE_DM_SEND, TASK_CODE_AUTO_ORDER]:
            await self.reload_task_config(task_code)
    
    def start(self) -> None:
        """启动定时任务"""
        if self._running:
            logger.warning("[定时任务调度] 任务已在运行中")
            return
        
        self._running = True
        # 启动任务循环
        self._redelivery_task_handle = asyncio.create_task(self._run_redelivery_loop())
        self._rate_task_handle = asyncio.create_task(self._run_rate_loop())
        self._polish_task_handle = asyncio.create_task(self._run_polish_loop())
        self._day_switch_task_handle = asyncio.create_task(self._run_day_switch_loop())
        self._cleanup_browser_data_task_handle = asyncio.create_task(self._run_cleanup_browser_data_loop())
        self._fetch_orders_task_handle = asyncio.create_task(self._run_fetch_orders_loop())
        self._fetch_pending_orders_task_handle = asyncio.create_task(self._run_fetch_pending_orders_loop())
        self._fetch_refund_orders_task_handle = asyncio.create_task(self._run_fetch_refund_orders_loop())
        self._fetch_items_task_handle = asyncio.create_task(self._run_fetch_items_loop())
        self._login_renew_task_handle = asyncio.create_task(self._run_login_renew_loop())
        self._cookies_refresh_task_handle = asyncio.create_task(self._run_cookies_refresh_loop())
        self._api_cookie_renew_task_handle = asyncio.create_task(self._run_api_cookie_renew_loop())
        self._close_notice_task_handle = asyncio.create_task(self._run_close_notice_loop())
        self._red_flower_task_handle = asyncio.create_task(self._run_red_flower_loop())
        self._db_backup_task_handle = asyncio.create_task(self._run_db_backup_loop())
        self._delivery_timeout_task_handle = asyncio.create_task(self._run_delivery_timeout_loop())
        self._listing_monitor_task_handle = asyncio.create_task(self._run_listing_monitor_loop())
        self._seller_fill_task_handle = asyncio.create_task(self._run_seller_fill_loop())
        self._dm_send_task_handle = asyncio.create_task(self._run_dm_send_loop())
        self._auto_order_task_handle = asyncio.create_task(self._run_auto_order_loop())
        logger.info("[定时任务调度] 已启动")
    
    def stop(self) -> None:
        """停止定时任务"""
        if not self._running:
            logger.warning("[定时任务调度] 任务未在运行")
            return
        
        self._running = False
        if self._redelivery_task_handle:
            self._redelivery_task_handle.cancel()
            self._redelivery_task_handle = None
        if self._rate_task_handle:
            self._rate_task_handle.cancel()
            self._rate_task_handle = None
        if self._polish_task_handle:
            self._polish_task_handle.cancel()
            self._polish_task_handle = None
        if self._day_switch_task_handle:
            self._day_switch_task_handle.cancel()
            self._day_switch_task_handle = None
        if self._cleanup_browser_data_task_handle:
            self._cleanup_browser_data_task_handle.cancel()
            self._cleanup_browser_data_task_handle = None
        if self._fetch_orders_task_handle:
            self._fetch_orders_task_handle.cancel()
            self._fetch_orders_task_handle = None
        if self._fetch_pending_orders_task_handle:
            self._fetch_pending_orders_task_handle.cancel()
            self._fetch_pending_orders_task_handle = None
        if self._fetch_refund_orders_task_handle:
            self._fetch_refund_orders_task_handle.cancel()
            self._fetch_refund_orders_task_handle = None
        if self._fetch_items_task_handle:
            self._fetch_items_task_handle.cancel()
            self._fetch_items_task_handle = None
        if self._login_renew_task_handle:
            self._login_renew_task_handle.cancel()
            self._login_renew_task_handle = None
        if self._cookies_refresh_task_handle:
            self._cookies_refresh_task_handle.cancel()
            self._cookies_refresh_task_handle = None
        if self._api_cookie_renew_task_handle:
            self._api_cookie_renew_task_handle.cancel()
            self._api_cookie_renew_task_handle = None
        if self._close_notice_task_handle:
            self._close_notice_task_handle.cancel()
            self._close_notice_task_handle = None
        if self._red_flower_task_handle:
            self._red_flower_task_handle.cancel()
            self._red_flower_task_handle = None
        if self._db_backup_task_handle:
            self._db_backup_task_handle.cancel()
            self._db_backup_task_handle = None
        if self._delivery_timeout_task_handle:
            self._delivery_timeout_task_handle.cancel()
            self._delivery_timeout_task_handle = None
        if self._listing_monitor_task_handle:
            self._listing_monitor_task_handle.cancel()
            self._listing_monitor_task_handle = None
        if self._seller_fill_task_handle:
            self._seller_fill_task_handle.cancel()
            self._seller_fill_task_handle = None
        if self._dm_send_task_handle:
            self._dm_send_task_handle.cancel()
            self._dm_send_task_handle = None
        if self._auto_order_task_handle:
            self._auto_order_task_handle.cancel()
            self._auto_order_task_handle = None
        logger.info("[定时任务调度] 已停止")
    
    def get_task_status(self) -> dict:
        """获取所有任务的运行状态"""
        redelivery_config = ScheduledTaskService.get_cached_config(TASK_CODE_REDELIVERY)
        rate_config = ScheduledTaskService.get_cached_config(TASK_CODE_RATE)
        polish_config = ScheduledTaskService.get_cached_config(TASK_CODE_POLISH)
        day_switch_config = ScheduledTaskService.get_cached_config(TASK_CODE_DAY_SWITCH)
        cleanup_browser_data_config = ScheduledTaskService.get_cached_config(TASK_CODE_CLEANUP_BROWSER_DATA)
        fetch_orders_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_ORDERS)
        fetch_pending_orders_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_PENDING_ORDERS)
        fetch_refund_orders_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_REFUND_ORDERS)
        fetch_items_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_ITEMS)
        login_renew_config = ScheduledTaskService.get_cached_config(TASK_CODE_LOGIN_RENEW)
        cookies_refresh_config = ScheduledTaskService.get_cached_config(TASK_CODE_COOKIES_REFRESH)
        api_cookie_renew_config = ScheduledTaskService.get_cached_config(TASK_CODE_API_COOKIE_RENEW)
        close_notice_config = ScheduledTaskService.get_cached_config(TASK_CODE_CLOSE_NOTICE)
        red_flower_config = ScheduledTaskService.get_cached_config(TASK_CODE_RED_FLOWER)
        db_backup_config = ScheduledTaskService.get_cached_config(TASK_CODE_DB_BACKUP)
        delivery_timeout_config = ScheduledTaskService.get_cached_config(TASK_CODE_DELIVERY_TIMEOUT)
        listing_monitor_config = ScheduledTaskService.get_cached_config(TASK_CODE_LISTING_MONITOR)
        seller_fill_config = ScheduledTaskService.get_cached_config(TASK_CODE_SELLER_FILL)
        dm_send_config = ScheduledTaskService.get_cached_config(TASK_CODE_DM_SEND)
        auto_order_config = ScheduledTaskService.get_cached_config(TASK_CODE_AUTO_ORDER)
        
        return {
            "running": self._running,
            "tasks": {
                TASK_CODE_REDELIVERY: {
                    "config": redelivery_config or {"interval_seconds": 5, "enabled": True},
                    "task_running": (
                        self._redelivery_task_handle is not None 
                        and not self._redelivery_task_handle.done()
                    ),
                },
                TASK_CODE_RATE: {
                    "config": rate_config or {"interval_seconds": 20, "enabled": True},
                    "task_running": (
                        self._rate_task_handle is not None 
                        and not self._rate_task_handle.done()
                    ),
                },
                TASK_CODE_POLISH: {
                    "config": polish_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._polish_task_handle is not None 
                        and not self._polish_task_handle.done()
                    ),
                },
                TASK_CODE_DAY_SWITCH: {
                    "config": day_switch_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._day_switch_task_handle is not None 
                        and not self._day_switch_task_handle.done()
                    ),
                },
                TASK_CODE_CLEANUP_BROWSER_DATA: {
                    "config": cleanup_browser_data_config or {"interval_seconds": 600, "enabled": True},
                    "task_running": (
                        self._cleanup_browser_data_task_handle is not None 
                        and not self._cleanup_browser_data_task_handle.done()
                    ),
                },
                TASK_CODE_FETCH_ORDERS: {
                    "config": fetch_orders_config or {"interval_seconds": 600, "enabled": True},
                    "task_running": (
                        self._fetch_orders_task_handle is not None 
                        and not self._fetch_orders_task_handle.done()
                    ),
                },
                TASK_CODE_FETCH_PENDING_ORDERS: {
                    "config": fetch_pending_orders_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._fetch_pending_orders_task_handle is not None
                        and not self._fetch_pending_orders_task_handle.done()
                    ),
                },
                TASK_CODE_FETCH_REFUND_ORDERS: {
                    "config": fetch_refund_orders_config or {"interval_seconds": 120, "enabled": True},
                    "task_running": (
                        self._fetch_refund_orders_task_handle is not None
                        and not self._fetch_refund_orders_task_handle.done()
                    ),
                },
                TASK_CODE_FETCH_ITEMS: {
                    "config": fetch_items_config or {"interval_seconds": 1200, "enabled": True},
                    "task_running": (
                        self._fetch_items_task_handle is not None
                        and not self._fetch_items_task_handle.done()
                    ),
                },
                TASK_CODE_LOGIN_RENEW: {
                    "config": login_renew_config or {"interval_seconds": 600, "enabled": True},
                    "task_running": (
                        self._login_renew_task_handle is not None 
                        and not self._login_renew_task_handle.done()
                    ),
                },
                TASK_CODE_COOKIES_REFRESH: {
                    "config": cookies_refresh_config or {"interval_seconds": 600, "enabled": True},
                    "task_running": (
                        self._cookies_refresh_task_handle is not None
                        and not self._cookies_refresh_task_handle.done()
                    ),
                },
                TASK_CODE_API_COOKIE_RENEW: {
                    "config": api_cookie_renew_config or {"interval_seconds": 600, "enabled": True},
                    "task_running": (
                        self._api_cookie_renew_task_handle is not None
                        and not self._api_cookie_renew_task_handle.done()
                    ),
                },
                TASK_CODE_CLOSE_NOTICE: {
                    "config": close_notice_config or {"interval_seconds": 600, "enabled": False},
                    "task_running": (
                        self._close_notice_task_handle is not None 
                        and not self._close_notice_task_handle.done()
                    ),
                },
                TASK_CODE_RED_FLOWER: {
                    "config": red_flower_config or {"interval_seconds": 300, "enabled": False},
                    "task_running": (
                        self._red_flower_task_handle is not None
                        and not self._red_flower_task_handle.done()
                    ),
                },
                TASK_CODE_DB_BACKUP: {
                    "config": db_backup_config or {"interval_seconds": 3600, "enabled": True},
                    "task_running": (
                        self._db_backup_task_handle is not None
                        and not self._db_backup_task_handle.done()
                    ),
                },
                TASK_CODE_DELIVERY_TIMEOUT: {
                    "config": delivery_timeout_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._delivery_timeout_task_handle is not None
                        and not self._delivery_timeout_task_handle.done()
                    ),
                },
                TASK_CODE_LISTING_MONITOR: {
                    "config": listing_monitor_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._listing_monitor_task_handle is not None
                        and not self._listing_monitor_task_handle.done()
                    ),
                },
                TASK_CODE_SELLER_FILL: {
                    "config": seller_fill_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._seller_fill_task_handle is not None
                        and not self._seller_fill_task_handle.done()
                    ),
                },
                TASK_CODE_DM_SEND: {
                    "config": dm_send_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._dm_send_task_handle is not None
                        and not self._dm_send_task_handle.done()
                    ),
                },
                TASK_CODE_AUTO_ORDER: {
                    "config": auto_order_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._auto_order_task_handle is not None
                        and not self._auto_order_task_handle.done()
                    ),
                },
            }
        }
    
    async def trigger_task(self, task_code: str) -> None:
        """
        手动触发任务执行
        
        Args:
            task_code: 任务代码
        """
        if task_code == TASK_CODE_REDELIVERY:
            logger.info("[定时任务调度] 手动触发补发货任务")
            await self._redelivery_task.execute()
        elif task_code == TASK_CODE_RATE:
            logger.info("[定时任务调度] 手动触发补评价任务")
            await self._rate_task.execute()
        elif task_code == TASK_CODE_POLISH:
            logger.info("[定时任务调度] 手动触发擦亮任务")
            await self._polish_task.execute()
        elif task_code == TASK_CODE_DAY_SWITCH:
            logger.info("[定时任务调度] 手动触发平台日切换任务")
            await self._day_switch_task.execute()
        elif task_code == TASK_CODE_CLEANUP_BROWSER_DATA:
            logger.info("[定时任务调度] 手动触发清理被禁用账号浏览器数据任务")
            await self._cleanup_browser_data_task.execute()
        elif task_code == TASK_CODE_FETCH_ORDERS:
            logger.info("[定时任务调度] 手动触发获取闲鱼订单任务")
            await self._fetch_orders_task.execute()
        elif task_code == TASK_CODE_FETCH_PENDING_ORDERS:
            logger.info("[定时任务调度] 手动触发获取待发货订单任务")
            await self._fetch_pending_orders_task.execute()
        elif task_code == TASK_CODE_FETCH_REFUND_ORDERS:
            logger.info("[定时任务调度] 手动触发获取退款订单任务")
            await self._fetch_refund_orders_task.execute()
        elif task_code == TASK_CODE_FETCH_ITEMS:
            logger.info("[定时任务调度] 手动触发获取闲鱼商品任务")
            await self._fetch_items_task.execute()
        elif task_code == TASK_CODE_LOGIN_RENEW:
            logger.info("[定时任务调度] 手动触发登录续期任务")
            await self._login_renew_task.execute()
        elif task_code == TASK_CODE_COOKIES_REFRESH:
            logger.info("[定时任务调度] 手动触发COOKIES续期任务")
            await self._cookies_refresh_task.execute()
        elif task_code == TASK_CODE_API_COOKIE_RENEW:
            logger.info("[定时任务调度] 手动触发接口续期Cookies任务")
            await self._api_cookie_renew_task.execute()
        elif task_code == TASK_CODE_CLOSE_NOTICE:
            logger.info("[定时任务调度] 手动触发关闭账号消息通知任务")
            await self._close_notice_task.execute()
        elif task_code == TASK_CODE_RED_FLOWER:
            logger.info("[定时任务调度] 手动触发求小红花任务")
            await self._red_flower_task.execute()
        elif task_code == TASK_CODE_DB_BACKUP:
            logger.info("[定时任务调度] 手动触发数据库备份任务")
            await self._db_backup_task.execute()
        elif task_code == TASK_CODE_DELIVERY_TIMEOUT:
            logger.info("[定时任务调度] 手动触发发货超时检测任务")
            await self._delivery_timeout_task.execute()
        elif task_code == TASK_CODE_LISTING_MONITOR:
            logger.info("[定时任务调度] 手动触发商品监控任务")
            await self._listing_monitor_task.execute(force=True, trigger_type="manual")
        elif task_code == TASK_CODE_SELLER_FILL:
            logger.info("[定时任务调度] 手动触发采集商品卖家ID补全任务")
            await self._seller_fill_task.execute()
        elif task_code == TASK_CODE_DM_SEND:
            logger.info("[定时任务调度] 手动触发采集商品发送私信任务")
            await self._dm_send_task.execute()
        elif task_code == TASK_CODE_AUTO_ORDER:
            logger.info("[定时任务调度] 手动触发采集商品自动下单任务")
            await self._auto_order_task.execute()
        else:
            logger.warning(f"[定时任务调度] 未知的任务代码: {task_code}")
    
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


# 全局实例获取函数
def get_scheduler_service() -> SchedulerService:
    """获取定时任务调度服务实例"""
    return SchedulerService.get_instance()
