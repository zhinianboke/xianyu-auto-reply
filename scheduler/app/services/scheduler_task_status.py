"""原定时任务状态展示，保留各任务状态，只追加安全频率任务。"""
from __future__ import annotations

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
from common.models.security_task import SECURITY_INTERVAL_SECONDS, SECURITY_TASK_CODE


class SchedulerTaskStatus:
    """原定时任务状态展示，保留各任务状态，只追加安全频率任务。"""

    def get_task_status(self) -> dict:
        """获取所有任务的运行状态"""
        redelivery_config = ScheduledTaskService.get_cached_config(TASK_CODE_REDELIVERY)
        rate_config = ScheduledTaskService.get_cached_config(TASK_CODE_RATE)
        polish_config = ScheduledTaskService.get_cached_config(TASK_CODE_POLISH)
        day_switch_config = ScheduledTaskService.get_cached_config(TASK_CODE_DAY_SWITCH)
        cleanup_browser_data_config = ScheduledTaskService.get_cached_config(TASK_CODE_CLEANUP_BROWSER_DATA)
        cleanup_unconfigured_browser_data_config = ScheduledTaskService.get_cached_config(TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA)
        fetch_orders_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_ORDERS)
        fetch_pending_orders_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_PENDING_ORDERS)
        fetch_refund_orders_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_REFUND_ORDERS)
        fetch_items_config = ScheduledTaskService.get_cached_config(TASK_CODE_FETCH_ITEMS)
        login_renew_config = ScheduledTaskService.get_cached_config(TASK_CODE_LOGIN_RENEW)
        token_renewal_config = ScheduledTaskService.get_cached_config(TASK_CODE_TOKEN_RENEWAL)
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
        image_cleanup_config = ScheduledTaskService.get_cached_config(TASK_CODE_IMAGE_CLEANUP)
        auto_relist_config = ScheduledTaskService.get_cached_config(TASK_CODE_AUTO_RELIST)
        scheduled_publish_config = ScheduledTaskService.get_cached_config(TASK_CODE_SCHEDULED_PUBLISH)
        
        return {
            "running": self._running,
            "tasks": {
                SECURITY_TASK_CODE: {
                    "config": ScheduledTaskService.get_cached_config(SECURITY_TASK_CODE)
                        or {"interval_seconds": SECURITY_INTERVAL_SECONDS, "enabled": False},
                    "task_running": bool(self._security_frequency_task_handle
                                         and not self._security_frequency_task_handle.done()),
                },
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
                TASK_CODE_CLEANUP_UNCONFIGURED_BROWSER_DATA: {
                    "config": cleanup_unconfigured_browser_data_config or {"interval_seconds": 10800, "enabled": False},
                    "task_running": (
                        self._cleanup_unconfigured_browser_data_task_handle is not None
                        and not self._cleanup_unconfigured_browser_data_task_handle.done()
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
                TASK_CODE_TOKEN_RENEWAL: {
                    "config": token_renewal_config or {"interval_seconds": 20, "enabled": True},
                    "task_running": (
                        self._token_renewal_task_handle is not None
                        and not self._token_renewal_task_handle.done()
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
                TASK_CODE_IMAGE_CLEANUP: {
                    "config": image_cleanup_config or {"interval_seconds": 1200, "enabled": True},
                    "task_running": (
                        self._image_cleanup_task_handle is not None
                        and not self._image_cleanup_task_handle.done()
                    ),
                },
                TASK_CODE_AUTO_RELIST: {
                    "config": auto_relist_config or {"interval_seconds": 30, "enabled": True},
                    "task_running": (
                        self._auto_relist_task_handle is not None
                        and not self._auto_relist_task_handle.done()
                    ),
                },
                TASK_CODE_SCHEDULED_PUBLISH: {
                    "config": scheduled_publish_config or {"interval_seconds": 60, "enabled": True},
                    "task_running": (
                        self._scheduled_publish_task_handle is not None
                        and not self._scheduled_publish_task_handle.done()
                    ),
                },
            }
        }

