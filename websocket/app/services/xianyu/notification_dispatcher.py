"""
通知调度器模块

使用策略模式将各通知渠道的发送逻辑封装为独立的处理器，
支持单渠道发送和多渠道并行发送（带错误隔离）。

设计要点:
- 每个通知渠道是一个独立的 handler 方法
- dispatch() 根据 channel_type 路由到正确的 handler
- dispatch_all() 使用 asyncio.gather 并行发送到所有渠道，一个渠道失败不影响其他渠道
- 错误隔离: return_exceptions=True 确保单个渠道异常不会中断整体流程
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from common.utils.notification_utils import (
    parse_notification_config,
    send_dingtalk_notification,
    send_feishu_notification,
    send_bark_notification,
    send_email_notification,
    send_webhook_notification,
    send_wechat_notification,
    send_telegram_notification,
    send_ntfy_notification,
)


class NotificationDispatcher:
    """通知调度器 - 策略模式

    将通知渠道的路由逻辑从调用方解耦，每个渠道类型对应一个独立的
    handler 方法。新增渠道只需添加对应的 handler 和注册即可。
    """

    # channel_type 别名映射：允许多个别名指向同一个 handler
    _ALIASES: Dict[str, str] = {
        "ding_talk": "dingtalk",
        "lark": "feishu",
        "wechat_work": "wechat",
    }

    def _normalize_channel_type(self, channel_type: str) -> str:
        """将渠道类型别名规范化为内部名称"""
        return self._ALIASES.get(channel_type, channel_type)

    # ==================== 各渠道 handler ====================

    async def _handle_dingtalk(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送钉钉通知"""
        return await send_dingtalk_notification(config_data, content)

    async def _handle_feishu(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送飞书通知"""
        return await send_feishu_notification(config_data, content)

    async def _handle_bark(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送 Bark 通知"""
        return await send_bark_notification(config_data, content)

    async def _handle_email(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送邮件通知"""
        attachment_path = kwargs.get("attachment_path")
        return await send_email_notification(config_data, content, attachment_path)

    async def _handle_webhook(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送 Webhook 通知"""
        return await send_webhook_notification(config_data, content)

    async def _handle_wechat(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送企业微信通知"""
        return await send_wechat_notification(config_data, content)

    async def _handle_telegram(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送 Telegram 通知"""
        return await send_telegram_notification(config_data, content)

    async def _handle_ntfy(
        self, config_data: Dict[str, Any], content: str, **kwargs
    ) -> bool:
        """发送 ntfy 通知"""
        return await send_ntfy_notification(config_data, content)

    # 渠道类型 -> handler 方法名映射
    _HANDLER_MAP: Dict[str, str] = {
        "dingtalk": "_handle_dingtalk",
        "feishu": "_handle_feishu",
        "bark": "_handle_bark",
        "email": "_handle_email",
        "webhook": "_handle_webhook",
        "wechat": "_handle_wechat",
        "telegram": "_handle_telegram",
        "ntfy": "_handle_ntfy",
    }

    # ==================== 公共调度接口 ====================

    async def dispatch(
        self,
        channel_type: str,
        channel_config: Any,
        content: str,
        **kwargs,
    ) -> bool:
        """将通知发送到指定渠道

        Args:
            channel_type: 渠道类型（支持别名，如 ding_talk -> dingtalk）
            channel_config: 渠道配置（字典或 JSON 字符串）
            content: 通知内容
            **kwargs: 传递给 handler 的额外参数（如 attachment_path）

        Returns:
            True 表示发送成功，False 表示失败或渠道不支持
        """
        normalized = self._normalize_channel_type(channel_type)
        handler_name = self._HANDLER_MAP.get(normalized)

        if not handler_name:
            logger.warning(f"不支持的通知渠道类型: {channel_type}")
            return False

        handler = getattr(self, handler_name)
        config_data = parse_notification_config(channel_config)

        try:
            return await handler(config_data, content, **kwargs)
        except Exception as e:
            logger.error(f"发送 {channel_type} 通知失败: {e}")
            return False

    async def dispatch_single(
        self,
        notification: Dict[str, Any],
        content: str,
        **kwargs,
    ) -> bool:
        """根据通知配置项发送单条通知

        Args:
            notification: 通知配置字典，需包含 channel_type 和 channel_config，
                          可选 enabled（默认 True）
            content: 通知内容
            **kwargs: 传递给 handler 的额外参数

        Returns:
            True 表示发送成功
        """
        if not notification.get("enabled", True):
            return False

        channel_type = notification.get("channel_type", "")
        channel_config = notification.get("channel_config", {}) or {}

        channel_name = notification.get("channel_name", channel_type)
        try:
            result = await self.dispatch(
                channel_type, channel_config, content, **kwargs
            )
            if result:
                logger.info(f"NotificationDispatcher: 通知发送成功 ({channel_name})")
            else:
                logger.warning(f"NotificationDispatcher: 通知发送失败 ({channel_name})")
            return result
        except Exception as e:
            logger.error(f"NotificationDispatcher: 发送通知失败 ({channel_name}): {e}")
            return False

    async def dispatch_all(
        self,
        channels: List[Dict[str, Any]],
        content: str,
        **kwargs,
    ) -> bool:
        """并行发送通知到所有启用的渠道

        使用 asyncio.gather + return_exceptions=True 实现错误隔离：
        任何一个渠道的异常不会影响其他渠道的发送。

        Args:
            channels: 通知配置列表，每项需包含 channel_type 和 channel_config
            content: 通知内容
            **kwargs: 传递给每个 handler 的额外参数（如 attachment_path）

        Returns:
            True 表示至少有一个渠道发送成功
        """
        enabled_channels = [
            ch for ch in channels if ch.get("enabled", True)
        ]

        if not enabled_channels:
            return False

        tasks = [
            self.dispatch_single(ch, content, **kwargs)
            for ch in enabled_channels
        ]

        # return_exceptions=True: 任何单个 task 抛出的异常会作为结果返回，
        # 而不会导致 gather 本身失败，从而实现错误隔离
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for i, result in enumerate(results):
            channel_name = enabled_channels[i].get("channel_name", "Unknown")
            if isinstance(result, Exception):
                logger.error(
                    f"NotificationDispatcher: 通知渠道 {channel_name} 发送异常: {result}"
                )
            elif result:
                success_count += 1

        return success_count > 0


# 模块级单例，方便直接使用
dispatcher = NotificationDispatcher()
