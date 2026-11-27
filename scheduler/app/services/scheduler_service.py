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

from app.services.scheduled_task_service import (
    TASK_CODE_API_COOKIE_RENEW,
    TASK_CODE_AUTO_ORDER,
    TASK_CODE_AUTO_RELIST,
    TASK_CODE_CLEANUP_BROWSER_DATA,
    TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA,
    TASK_CODE_CLOSE_NOTICE,
    TASK_CODE_COOKIES_REFRESH,
    TASK_CODE_DAY_SWITCH,
    TASK_CODE_DB_BACKUP,
    TASK_CODE_DELIVERY_TIMEOUT,
    TASK_CODE_DM_SEND,
    TASK_CODE_FETCH_ITEMS,
    TASK_CODE_FETCH_ORDERS,
    TASK_CODE_FETCH_PENDING_ORDERS,
    TASK_CODE_FETCH_REFUND_ORDERS,
    TASK_CODE_IMAGE_CLEANUP,
    TASK_CODE_LISTING_MONITOR,
    TASK_CODE_LOGIN_RENEW,
    TASK_CODE_POLISH,
    TASK_CODE_RATE,
    TASK_CODE_RED_FLOWER,
    TASK_CODE_REDELIVERY,
    TASK_CODE_SCHEDULED_PUBLISH,
    TASK_CODE_SELLER_FILL,
    TASK_CODE_TOKEN_RENEWAL,
    ScheduledTaskService,
)
from app.services.scheduler.api_cookie_renew_task import api_cookie_renew_task_service
from app.services.scheduler.auto_order_task import auto_order_task_service
from app.services.scheduler.auto_relist_task import auto_relist_task_service
from app.services.scheduler.cleanup_browser_data_task import (
    cleanup_browser_data_task_service,
)
from app.services.scheduler.cleanup_unconfigured_browser_data_task import (
    cleanup_unconfigured_browser_data_task_service,
)
from app.services.scheduler.close_notice_task import close_notice_task_service
from app.services.scheduler.cookies_refresh_task import cookies_refresh_task_service
from app.services.scheduler.day_switch_task import day_switch_task_service
from app.services.scheduler.db_backup_task import db_backup_task_service
from app.services.scheduler.delivery_timeout_task import delivery_timeout_task_service
from app.services.scheduler.dm_send_task import dm_send_task_service
from app.services.scheduler.fetch_items_task import fetch_items_task_service
from app.services.scheduler.fetch_orders_task import (
    fetch_orders_task_service,
    fetch_pending_orders_task_service,
    fetch_refund_orders_task_service,
)
from app.services.scheduler.image_cleanup_task import image_cleanup_task_service
from app.services.scheduler.listing_monitor_task import listing_monitor_task_service
from app.services.scheduler.login_renew_task import login_renew_task_service
from app.services.scheduler.polish_task import polish_task_service
from app.services.scheduler.rate_task import RateTask
from app.services.scheduler.red_flower_task import RedFlowerTask
from app.services.scheduler.redelivery_task import RedeliveryTask
from app.services.scheduler.scheduled_publish_task import scheduled_publish_task_service
from app.services.scheduler.security_frequency_task import (
    security_frequency_task_service,
)
from app.services.scheduler.security_log_cleanup_task import run_security_log_cleanup
from app.services.scheduler.seller_fill_task import seller_fill_task_service
from app.services.scheduler.token_renewal_task import token_renewal_task_service
from app.services.scheduler_account_loops import SchedulerAccountLoops
from app.services.scheduler_business_loops import SchedulerBusinessLoops
from app.services.scheduler_interval_loop import SchedulerIntervalLoop
from app.services.scheduler_order_loops import SchedulerOrderLoops
from app.services.scheduler_task_status import SchedulerTaskStatus
from common.db.session import async_session_maker
from common.models.security_task import SECURITY_INTERVAL_SECONDS, SECURITY_TASK_CODE
from common.services.audit_writer import report_safely


class SchedulerService(SchedulerOrderLoops, SchedulerAccountLoops, SchedulerBusinessLoops,
                       SchedulerTaskStatus, SchedulerIntervalLoop):
    """定时任务调度服务 - 支持从数据库读取配置并动态更新"""
    
    _instance: Optional["SchedulerService"] = None
    
    def __init__(self):
        """初始化原任务实例及句柄；安全检查与商品定时发布注册在同一调度器。"""
        self._running = False
        self._stopping_tasks: set[asyncio.Task] = set()
        self._redelivery_task_handle: Optional[asyncio.Task] = None
        self._rate_task_handle: Optional[asyncio.Task] = None
        self._polish_task_handle: Optional[asyncio.Task] = None
        self._day_switch_task_handle: Optional[asyncio.Task] = None
        self._cleanup_browser_data_task_handle: Optional[asyncio.Task] = None
        self._cleanup_unconfigured_browser_data_task_handle: Optional[asyncio.Task] = None
        self._fetch_orders_task_handle: Optional[asyncio.Task] = None
        self._fetch_pending_orders_task_handle: Optional[asyncio.Task] = None
        self._fetch_refund_orders_task_handle: Optional[asyncio.Task] = None
        self._fetch_items_task_handle: Optional[asyncio.Task] = None
        self._login_renew_task_handle: Optional[asyncio.Task] = None
        self._token_renewal_task_handle: Optional[asyncio.Task] = None
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
        self._image_cleanup_task_handle: Optional[asyncio.Task] = None
        self._auto_relist_task_handle: Optional[asyncio.Task] = None
        self._scheduled_publish_task_handle: Optional[asyncio.Task] = None
        self._security_frequency_task_handle: Optional[asyncio.Task] = None
        self._security_log_cleanup_task_handle: asyncio.Task | None = None
        self._redelivery_task = RedeliveryTask()
        self._rate_task = RateTask()
        self._polish_task = polish_task_service
        self._day_switch_task = day_switch_task_service
        self._cleanup_browser_data_task = cleanup_browser_data_task_service
        self._cleanup_unconfigured_browser_data_task = cleanup_unconfigured_browser_data_task_service
        self._fetch_orders_task = fetch_orders_task_service
        self._fetch_pending_orders_task = fetch_pending_orders_task_service
        self._fetch_refund_orders_task = fetch_refund_orders_task_service
        self._fetch_items_task = fetch_items_task_service
        self._login_renew_task = login_renew_task_service
        self._token_renewal_task = token_renewal_task_service
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
        self._image_cleanup_task = image_cleanup_task_service
        self._auto_relist_task = auto_relist_task_service
        self._scheduled_publish_task = scheduled_publish_task_service
        self._security_frequency_task = security_frequency_task_service
    
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
        for task_code in [TASK_CODE_REDELIVERY, TASK_CODE_RATE, TASK_CODE_POLISH, TASK_CODE_DAY_SWITCH, TASK_CODE_CLEANUP_BROWSER_DATA, TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA, TASK_CODE_FETCH_ORDERS, TASK_CODE_FETCH_PENDING_ORDERS, TASK_CODE_FETCH_REFUND_ORDERS, TASK_CODE_FETCH_ITEMS, TASK_CODE_LOGIN_RENEW, TASK_CODE_TOKEN_RENEWAL, TASK_CODE_COOKIES_REFRESH, TASK_CODE_API_COOKIE_RENEW, TASK_CODE_CLOSE_NOTICE, TASK_CODE_RED_FLOWER, TASK_CODE_DB_BACKUP]:
            await self.reload_task_config(task_code)
        for task_code in [TASK_CODE_DELIVERY_TIMEOUT, TASK_CODE_LISTING_MONITOR, TASK_CODE_SELLER_FILL, TASK_CODE_DM_SEND, TASK_CODE_AUTO_ORDER]:
            await self.reload_task_config(task_code)
        await self.reload_task_config(TASK_CODE_IMAGE_CLEANUP)
        await self.reload_task_config(TASK_CODE_AUTO_RELIST)
        await self.reload_task_config(TASK_CODE_SCHEDULED_PUBLISH)
        await self.reload_task_config(SECURITY_TASK_CODE)
    
    def start(self) -> None:
        """启动定时任务"""
        if self._running:
            logger.warning("[定时任务调度] 任务已在运行中")
            return
        
        for name, task in vars(self).items():
            if name.endswith('_task'):
                start = getattr(task, 'start', None)
                if start is not None:
                    start()
        self._running = True
        # 启动任务循环
        self._redelivery_task_handle = asyncio.create_task(self._run_redelivery_loop())
        self._rate_task_handle = asyncio.create_task(self._run_rate_loop())
        self._polish_task_handle = asyncio.create_task(self._run_polish_loop())
        self._day_switch_task_handle = asyncio.create_task(self._run_day_switch_loop())
        self._cleanup_browser_data_task_handle = asyncio.create_task(self._run_cleanup_browser_data_loop())
        self._cleanup_unconfigured_browser_data_task_handle = asyncio.create_task(self._run_cleanup_unconfigured_browser_data_loop())
        self._fetch_orders_task_handle = asyncio.create_task(self._run_fetch_orders_loop())
        self._fetch_pending_orders_task_handle = asyncio.create_task(self._run_fetch_pending_orders_loop())
        self._fetch_refund_orders_task_handle = asyncio.create_task(self._run_fetch_refund_orders_loop())
        self._fetch_items_task_handle = asyncio.create_task(self._run_fetch_items_loop())
        self._login_renew_task_handle = asyncio.create_task(self._run_login_renew_loop())
        self._token_renewal_task_handle = asyncio.create_task(self._run_token_renewal_loop())
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
        self._image_cleanup_task_handle = asyncio.create_task(self._run_image_cleanup_loop())
        self._auto_relist_task_handle = asyncio.create_task(self._run_auto_relist_loop())
        self._scheduled_publish_task_handle = asyncio.create_task(self._run_interval_task_loop(
            TASK_CODE_SCHEDULED_PUBLISH, '商品定时发布', self._scheduled_publish_task,
            default_interval=60, default_enabled=True))
        self._security_frequency_task_handle = asyncio.create_task(self._run_interval_task_loop(
            SECURITY_TASK_CODE, '安全频率限制', self._security_frequency_task,
            default_interval=SECURITY_INTERVAL_SECONDS, default_enabled=False))
        self._security_log_cleanup_task_handle = asyncio.create_task(run_security_log_cleanup())
        logger.info("[定时任务调度] 已启动")
    
    def stop(self) -> None:
        """停止定时任务"""
        if not self._running:
            logger.warning("[定时任务调度] 任务未在运行")
            return
        
        self._running = False
        self._stopping_tasks.update(handle for name, handle in vars(self).items()
                                    if name.endswith('_task_handle') and isinstance(handle, asyncio.Task))
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
        if self._cleanup_unconfigured_browser_data_task_handle:
            self._cleanup_unconfigured_browser_data_task_handle.cancel()
            self._cleanup_unconfigured_browser_data_task_handle = None
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
        if self._token_renewal_task_handle:
            self._token_renewal_task_handle.cancel()
            self._token_renewal_task_handle = None
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
        if self._image_cleanup_task_handle:
            self._image_cleanup_task_handle.cancel()
            self._image_cleanup_task_handle = None
        if self._auto_relist_task_handle:
            self._auto_relist_task_handle.cancel()
            self._auto_relist_task_handle = None
        if self._scheduled_publish_task_handle:
            self._scheduled_publish_task_handle.cancel()
            self._scheduled_publish_task_handle = None
        if self._security_frequency_task_handle:
            self._security_frequency_task_handle.cancel()
            self._security_frequency_task_handle = None
        if self._security_log_cleanup_task_handle:
            self._security_log_cleanup_task_handle.cancel()
            self._security_log_cleanup_task_handle = None
        logger.info("[定时任务调度] 已停止")

    async def trigger_task(self, task_code: str, owner_id: int | None = None) -> dict | None:
        """
        手动触发任务执行
        
        Args:
            task_code: 任务代码
            owner_id: 已认证管理员ID，用于需要记录操作人的业务审计。
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
        elif task_code == TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA:
            logger.info("[定时任务调度] 手动触发清理未配置账号密码的浏览器数据任务")
            await self._cleanup_unconfigured_browser_data_task.execute()
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
        elif task_code == TASK_CODE_TOKEN_RENEWAL:
            logger.info("[定时任务调度] 手动触发Token续期任务")
            await self._token_renewal_task.execute()
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
        elif task_code == TASK_CODE_IMAGE_CLEANUP:
            logger.info("[定时任务调度] 手动触发图片清理任务")
            await self._image_cleanup_task.execute()
        elif task_code == TASK_CODE_AUTO_RELIST:
            logger.info("[定时任务调度] [自动续售] 手动触发商品自动续售任务")
            try:
                await self._auto_relist_task.execute()
            finally:
                logger.info("[定时任务调度] [自动续售] 手动触发商品自动续售任务结束")
        elif task_code == TASK_CODE_SCHEDULED_PUBLISH:
            logger.info("[定时任务调度] 手动触发商品定时发布任务")
            await self._scheduled_publish_task.execute()
        elif task_code == SECURITY_TASK_CODE:
            logger.info("[定时任务调度] 手动触发安全频率限制任务")
            if owner_id is None:
                raise ValueError('手动执行缺少管理员信息')
            return await self._security_frequency_task.execute(owner_id=owner_id)
        else:
            logger.warning(f"[定时任务调度] 未知的任务代码: {task_code}")

    async def close(self) -> None:
        """等待原任务循环和已开始的业务审计收尾，再由生命周期释放数据库。"""
        self.stop()
        try:
            for name, task in vars(self).items():
                if name.endswith('_task'):
                    close = getattr(task, 'close', None)
                    if close is not None:
                        await close()
        finally:
            handles = tuple(self._stopping_tasks)
            results = await asyncio.gather(*handles, return_exceptions=True)
            self._stopping_tasks.difference_update(handles)
            for result in results:
                if isinstance(result, Exception):
                    report_safely('定时任务关闭收尾失败', result)

# 全局实例获取函数
def get_scheduler_service() -> SchedulerService:
    """获取定时任务调度服务实例"""
    return SchedulerService.get_instance()
