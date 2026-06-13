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
)
from app.services.scheduler.fetch_items_task import fetch_items_task_service
from app.services.scheduler.login_renew_task import login_renew_task_service
from app.services.scheduler.cookies_refresh_task import cookies_refresh_task_service
from app.services.scheduler.api_cookie_renew_task import api_cookie_renew_task_service
from app.services.scheduler.close_notice_task import close_notice_task_service
from app.services.scheduler.red_flower_task import RedFlowerTask
from app.services.scheduler.db_backup_task import db_backup_task_service
from app.services.scheduler.inventory_monitor_task import inventory_monitor_task_service
from app.services.scheduler.delivery_timeout_task import delivery_timeout_task_service
from app.services.scheduled_task_service import (
    ScheduledTaskService,
    TASK_CODE_REDELIVERY,
    TASK_CODE_RATE,
    TASK_CODE_POLISH,
    TASK_CODE_DAY_SWITCH,
    TASK_CODE_CLEANUP_BROWSER_DATA,
    TASK_CODE_FETCH_ORDERS,
    TASK_CODE_FETCH_PENDING_ORDERS,
    TASK_CODE_FETCH_ITEMS,
    TASK_CODE_LOGIN_RENEW,
    TASK_CODE_COOKIES_REFRESH,
    TASK_CODE_API_COOKIE_RENEW,
    TASK_CODE_CLOSE_NOTICE,
    TASK_CODE_RED_FLOWER,
    TASK_CODE_DB_BACKUP,
    TASK_CODE_INVENTORY_MONITOR,
    TASK_CODE_DELIVERY_TIMEOUT,
)
from common.db.session import async_session_maker


class SchedulerService:
    """定时任务调度服务 - 支持从数据库读取配置并动态更新"""
    
    _instance: Optional["SchedulerService"] = None
    
    # Task registry: task_code -> (service_attr, default_interval, default_enabled, display_name)
    TASK_REGISTRY: dict[str, tuple[str, int, bool, str]] = {
        TASK_CODE_REDELIVERY: ("_redelivery_task", 5, True, "补发货"),
        TASK_CODE_RATE: ("_rate_task", 20, True, "补评价"),
        TASK_CODE_POLISH: ("_polish_task", 60, True, "擦亮"),
        TASK_CODE_DAY_SWITCH: ("_day_switch_task", 60, True, "平台日切换"),
        TASK_CODE_CLEANUP_BROWSER_DATA: ("_cleanup_browser_data_task", 600, True, "清理被禁用账号浏览器数据"),
        TASK_CODE_FETCH_ORDERS: ("_fetch_orders_task", 600, True, "获取闲鱼订单"),
        TASK_CODE_FETCH_PENDING_ORDERS: ("_fetch_pending_orders_task", 60, True, "获取待发货订单"),
        TASK_CODE_FETCH_ITEMS: ("_fetch_items_task", 1200, True, "获取闲鱼商品"),
        TASK_CODE_LOGIN_RENEW: ("_login_renew_task", 600, True, "登录续期"),
        TASK_CODE_COOKIES_REFRESH: ("_cookies_refresh_task", 600, True, "COOKIES续期"),
        TASK_CODE_API_COOKIE_RENEW: ("_api_cookie_renew_task", 600, True, "接口续期Cookies"),
        TASK_CODE_CLOSE_NOTICE: ("_close_notice_task", 600, False, "关闭账号消息通知"),
        TASK_CODE_RED_FLOWER: ("_red_flower_task", 300, False, "求小红花"),
        TASK_CODE_DB_BACKUP: ("_db_backup_task", 3600, True, "数据库备份"),
        TASK_CODE_INVENTORY_MONITOR: ("_inventory_monitor_task", 300, True, "卡券库存监控"),
        TASK_CODE_DELIVERY_TIMEOUT: ("_delivery_timeout_task", 60, True, "发货超时检测"),
    }
    
    def __init__(self):
        self._running = False
        self._task_handles: dict[str, asyncio.Task] = {}
        self._redelivery_task = RedeliveryTask()
        self._rate_task = RateTask()
        self._polish_task = polish_task_service
        self._day_switch_task = day_switch_task_service
        self._cleanup_browser_data_task = cleanup_browser_data_task_service
        self._fetch_orders_task = fetch_orders_task_service
        self._fetch_pending_orders_task = fetch_pending_orders_task_service
        self._fetch_items_task = fetch_items_task_service
        self._login_renew_task = login_renew_task_service
        self._cookies_refresh_task = cookies_refresh_task_service
        self._api_cookie_renew_task = api_cookie_renew_task_service
        self._close_notice_task = close_notice_task_service
        self._red_flower_task = RedFlowerTask()
        self._db_backup_task = db_backup_task_service
        self._inventory_monitor_task = inventory_monitor_task_service
        self._delivery_timeout_task = delivery_timeout_task_service
    
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
        for task_code in self.TASK_REGISTRY:
            await self.reload_task_config(task_code)
    
    def start(self) -> None:
        """启动定时任务"""
        if self._running:
            logger.warning("[定时任务调度] 任务已在运行中")
            return
        
        self._running = True
        # 启动任务循环
        for task_code in self.TASK_REGISTRY:
            self._task_handles[task_code] = asyncio.create_task(
                self._run_task_loop(task_code)
            )
        logger.info("[定时任务调度] 已启动")
    
    def stop(self) -> None:
        """停止定时任务"""
        if not self._running:
            logger.warning("[定时任务调度] 任务未在运行")
            return
        
        self._running = False
        for handle in self._task_handles.values():
            if handle:
                handle.cancel()
        self._task_handles.clear()
        logger.info("[定时任务调度] 已停止")
    
    def get_task_status(self) -> dict:
        """获取所有任务的运行状态"""
        tasks = {}
        for task_code, (_, default_interval, default_enabled, _) in self.TASK_REGISTRY.items():
            config = ScheduledTaskService.get_cached_config(task_code)
            handle = self._task_handles.get(task_code)
            tasks[task_code] = {
                "config": config or {"interval_seconds": default_interval, "enabled": default_enabled},
                "task_running": handle is not None and not handle.done(),
            }
        return {"running": self._running, "tasks": tasks}
    
    async def trigger_task(self, task_code: str) -> None:
        """
        手动触发任务执行
        
        Args:
            task_code: 任务代码
        """
        if task_code not in self.TASK_REGISTRY:
            logger.warning(f"[定时任务调度] 未知的任务代码: {task_code}")
            return
        
        service_attr, _, _, display_name = self.TASK_REGISTRY[task_code]
        service = getattr(self, service_attr)
        logger.info(f"[定时任务调度] 手动触发{display_name}任务")
        await service.execute()
    
    async def _run_task_loop(self, task_code: str, timeout: float = 300.0) -> None:
        """通用任务执行循环
        
        Args:
            task_code: 任务代码
            timeout: 任务执行超时时间（秒），默认300秒
        """
        service_attr, default_interval, default_enabled, display_name = self.TASK_REGISTRY[task_code]
        service = getattr(self, service_attr)
        
        logger.info(f"[定时任务调度] {display_name}任务循环开始")
        
        # 初始加载配置
        await self.reload_task_config(task_code)
        
        while self._running:
            config = ScheduledTaskService.get_cached_config(task_code)
            if not config:
                config = {"interval_seconds": default_interval, "enabled": default_enabled}
            
            interval = config.get("interval_seconds", default_interval)
            enabled = config.get("enabled", default_enabled)
            
            if enabled:
                try:
                    await asyncio.wait_for(service.execute(), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.error(f"[定时任务调度] {display_name}任务执行超时({timeout}秒)")
                except asyncio.CancelledError:
                    logger.info(f"[定时任务调度] {display_name}任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[定时任务调度] {display_name}任务执行异常: {e}")
            
            # 等待下一次执行
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info(f"[定时任务调度] {display_name}任务等待被取消")
                break
        
        logger.info(f"[定时任务调度] {display_name}任务循环结束")


# 全局实例获取函数
def get_scheduler_service() -> SchedulerService:
    """获取定时任务调度服务实例"""
    return SchedulerService.get_instance()
