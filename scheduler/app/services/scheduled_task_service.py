"""
定时任务配置服务

功能：
1. 获取定时任务列表
2. 更新定时任务配置（间隔时间、是否启用）
3. 配置更新后通知调度器刷新
4. 缓存任务配置，减少数据库查询
"""
from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.scheduled_task import ScheduledTask


# 任务代码常量
TASK_CODE_REDELIVERY = "redelivery"
TASK_CODE_RATE = "rate"
TASK_CODE_POLISH = "polish"
TASK_CODE_DAY_SWITCH = "day_switch"
TASK_CODE_CLEANUP_BROWSER_DATA = "cleanup_browser_data"
TASK_CODE_FETCH_ORDERS = "fetch_orders"
TASK_CODE_FETCH_PENDING_ORDERS = "fetch_pending_orders"
TASK_CODE_FETCH_REFUND_ORDERS = "fetch_refund_orders"
TASK_CODE_FETCH_ITEMS = "fetch_items"
TASK_CODE_LOGIN_RENEW = "login_renew"
TASK_CODE_COOKIES_REFRESH = "cookies_refresh"
TASK_CODE_API_COOKIE_RENEW = "api_cookie_renew"
TASK_CODE_CLOSE_NOTICE = "close_notice"
TASK_CODE_RED_FLOWER = "red_flower"
TASK_CODE_DB_BACKUP = "db_backup"
TASK_CODE_DELIVERY_TIMEOUT = "delivery_timeout"
TASK_CODE_LISTING_MONITOR = "listing_monitor"
TASK_CODE_SELLER_FILL = "seller_fill"
TASK_CODE_DM_SEND = "dm_send"
TASK_CODE_AUTO_ORDER = "auto_order"

# 默认配置（数据库无配置时使用）
DEFAULT_CONFIGS = {
    TASK_CODE_REDELIVERY: {"interval_seconds": 5, "enabled": True},
    TASK_CODE_RATE: {"interval_seconds": 20, "enabled": True},
    TASK_CODE_POLISH: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_DAY_SWITCH: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_CLEANUP_BROWSER_DATA: {"interval_seconds": 600, "enabled": False},
    TASK_CODE_FETCH_ORDERS: {"interval_seconds": 600, "enabled": True},
    TASK_CODE_FETCH_PENDING_ORDERS: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_FETCH_REFUND_ORDERS: {"interval_seconds": 120, "enabled": True},
    TASK_CODE_FETCH_ITEMS: {"interval_seconds": 1200, "enabled": True},
    TASK_CODE_LOGIN_RENEW: {"interval_seconds": 600, "enabled": False},
    TASK_CODE_COOKIES_REFRESH: {"interval_seconds": 600, "enabled": False},
    TASK_CODE_API_COOKIE_RENEW: {"interval_seconds": 3600, "enabled": True},
    TASK_CODE_CLOSE_NOTICE: {"interval_seconds": 600, "enabled": False},
    TASK_CODE_RED_FLOWER: {"interval_seconds": 300, "enabled": True},
    TASK_CODE_DB_BACKUP: {"interval_seconds": 3600, "enabled": True},
    TASK_CODE_DELIVERY_TIMEOUT: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_LISTING_MONITOR: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_SELLER_FILL: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_DM_SEND: {"interval_seconds": 60, "enabled": True},
    TASK_CODE_AUTO_ORDER: {"interval_seconds": 60, "enabled": True},
}


class ScheduledTaskService:
    """定时任务配置服务"""
    
    # 配置缓存：task_code -> {interval_seconds, enabled}
    _config_cache: Dict[str, dict] = {}
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_all_tasks(self) -> List[ScheduledTask]:
        """获取所有定时任务配置"""
        stmt = select(ScheduledTask).order_by(ScheduledTask.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_task_by_code(self, task_code: str) -> Optional[ScheduledTask]:
        """根据任务代码获取任务配置"""
        stmt = select(ScheduledTask).where(ScheduledTask.task_code == task_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def load_task_config(self, task_code: str) -> dict:
        """
        从数据库加载任务配置并缓存
        
        Args:
            task_code: 任务代码
            
        Returns:
            任务配置字典 {interval_seconds, enabled}
        """
        try:
            task = await self.get_task_by_code(task_code)
            
            if task:
                config = {
                    "interval_seconds": task.interval_seconds,
                    "enabled": task.enabled,
                }
                # 更新缓存
                self._config_cache[task_code] = config
                logger.info(
                    f"[定时任务配置] 加载任务配置 {task_code}: "
                    f"间隔={config['interval_seconds']}秒, 启用={config['enabled']}"
                )
                return config
        except Exception as e:
            logger.error(f"[定时任务配置] 加载任务配置失败 {task_code}: {e}")
        
        # 返回默认配置
        default_config = DEFAULT_CONFIGS.get(
            task_code,
            {"interval_seconds": 60, "enabled": True}
        )
        self._config_cache[task_code] = default_config
        logger.warning(
            f"[定时任务配置] 使用默认配置 {task_code}: "
            f"间隔={default_config['interval_seconds']}秒, 启用={default_config['enabled']}"
        )
        return default_config
    
    @classmethod
    def get_cached_config(cls, task_code: str) -> Optional[dict]:
        """
        从缓存获取任务配置
        
        Args:
            task_code: 任务代码
            
        Returns:
            任务配置字典，如果缓存中不存在返回None
        """
        return cls._config_cache.get(task_code)
    
    async def update_task(
        self,
        task_code: str,
        interval_seconds: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[ScheduledTask]:
        """
        更新定时任务配置
        
        Args:
            task_code: 任务代码
            interval_seconds: 执行间隔（秒），None表示不更新
            enabled: 是否启用，None表示不更新
            
        Returns:
            更新后的任务配置，如果任务不存在返回None
        """
        task = await self.get_task_by_code(task_code)
        if not task:
            logger.warning(f"[定时任务配置] 任务不存在: {task_code}")
            return None
        
        # 更新字段
        if interval_seconds is not None:
            if interval_seconds < 1:
                raise ValueError("执行间隔不能小于1秒")
            task.interval_seconds = interval_seconds
        
        if enabled is not None:
            task.enabled = enabled
        
        await self.session.commit()
        await self.session.refresh(task)
        
        logger.info(
            f"[定时任务配置] 任务配置已更新: {task_code}, "
            f"间隔={task.interval_seconds}秒, 启用={task.enabled}"
        )
        
        # 更新缓存
        self._config_cache[task_code] = {
            "interval_seconds": task.interval_seconds,
            "enabled": task.enabled,
        }
        
        # 通知调度器刷新配置
        await self._notify_scheduler_reload(task_code)
        
        return task
    
    async def _notify_scheduler_reload(self, task_code: str) -> None:
        """通知调度器重新加载任务配置"""
        try:
            from app.services.scheduler_service import get_scheduler_service
            scheduler = get_scheduler_service()
            await scheduler.reload_task_config(task_code)
        except Exception as e:
            logger.error(f"[定时任务配置] 通知调度器刷新配置失败: {e}")
