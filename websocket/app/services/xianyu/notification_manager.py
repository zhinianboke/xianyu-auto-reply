"""
通知管理模块

负责处理各种类型的通知发送，包括：
- 消息通知
- Token刷新异常通知
- 发货失败通知

使用common/utils/notification_utils.py中的通知发送函数
"""
import time
import asyncio
import hashlib
from loguru import logger

from common.utils.notification_utils import (
    parse_notification_config,
    send_dingtalk_notification,
    send_feishu_notification,
    send_bark_notification,
    send_email_notification,
    send_webhook_notification,
    send_wechat_notification,
    send_telegram_notification
)
from common.utils.text_utils import safe_str


class NotificationManager:
    """通知管理器"""

    # 类级别共享冷却字典：按 cookie_id 分组保存各通知类型的最后发送时间
    # 目的：同一账号即使创建了多个 NotificationManager 实例（如 XianyuAsync 持久实例
    # 与 XianyuSliderStealth._send_account_disabled_notification 临时新建实例），
    # 也共享同一份冷却记录，避免短时间内发送多条重复通知。
    _shared_last_notification_time: dict = {}
    
    def __init__(self, cookie_id: str):
        """初始化通知管理器
        
        Args:
            cookie_id: Cookie ID
        """
        self.cookie_id = cookie_id
        
        # 通知防重复机制：取该 cookie_id 在共享字典中的子字典，所有同 cookie_id 的实例共享
        if cookie_id not in NotificationManager._shared_last_notification_time:
            NotificationManager._shared_last_notification_time[cookie_id] = {}
        self.last_notification_time = NotificationManager._shared_last_notification_time[cookie_id]
        self.notification_cooldown = 300  # 5分钟
        self.token_refresh_notification_cooldown = 10800  # 3小时
        self.notification_lock = asyncio.Lock()
    
    def _safe_str(self, e) -> str:
        """安全地将异常转换为字符串（委托公共实现）"""
        return safe_str(e)

    async def send_notification(self, send_user_name: str, send_user_id: str, 
                               send_message: str, item_id: str = None, chat_id: str = None):
        """发送消息通知"""
        try:
            from common.db.compat import db_manager

            # 过滤系统默认消息
            system_messages = ['发来一条消息', '发来一条新消息']
            if send_message in system_messages:
                logger.warning(f"📱 系统消息不发送通知: {send_message}")
                return

            # 检查消息过滤规则（跳过消息通知）
            try:
                filter_keywords = db_manager.get_message_filter_keywords(self.cookie_id, 'skip_notify')
                if filter_keywords:
                    for keyword in filter_keywords:
                        if keyword and keyword in send_message:
                            logger.info(f"📱 【消息过滤】消息包含过滤关键词「{keyword}」，跳过消息通知")
                            return
            except Exception as e:
                logger.warning(f"📱 检查消息过滤规则失败: {self._safe_str(e)}")

            # 生成通知唯一标识
            notification_key = f"{chat_id or 'unknown'}_{send_user_id}_{send_message}"
            notification_hash = hashlib.md5(notification_key.encode('utf-8')).hexdigest()
            
            async with self.notification_lock:
                current_time = time.time()
                if notification_hash in self.last_notification_time:
                    time_since_last = current_time - self.last_notification_time[notification_hash]
                    if time_since_last < self.notification_cooldown:
                        remaining_seconds = int(self.notification_cooldown - time_since_last)
                        logger.warning(f"📱 通知在冷却期内（剩余 {remaining_seconds} 秒），跳过重复发送")
                        return
                
                self.last_notification_time[notification_hash] = current_time
                
                # 清理过期记录
                expired_keys = [
                    key for key, timestamp in self.last_notification_time.items()
                    if current_time - timestamp > 3600
                ]
                for key in expired_keys:
                    del self.last_notification_time[key]

            logger.info(f"📱 开始发送消息通知 - 账号: {self.cookie_id}, 买家: {send_user_name}")

            # 获取账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)
            if not notifications:
                logger.warning(f"📱 账号 {self.cookie_id} 未配置消息通知，跳过通知发送")
                return

            # 获取账号备注
            remark = ""
            try:
                account_details = db_manager.get_cookie_details(self.cookie_id)
                if account_details:
                    remark = account_details.get("remark") or ""
            except Exception as e:
                logger.warning(f"获取账号详情失败: {e}")

            # 构建通知内容（与旧框架保持一致）
            account_desc = f"{self.cookie_id}({remark})" if remark else self.cookie_id
            notification_msg = f"🚨 接收消息通知\n\n" \
                             f"闲鱼账号: {account_desc}\n" \
                             f"买家: {send_user_name} (ID: {send_user_id})\n" \
                             f"商品ID: {item_id or '未知'}\n" \
                             f"聊天ID: {chat_id or '未知'}\n" \
                             f"消息内容: {send_message}\n" \
                             f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            # 发送通知到各渠道
            await self._send_to_channels(notifications, notification_msg)

        except Exception as e:
            logger.error(f"📱 处理消息通知失败: {self._safe_str(e)}")

    async def send_delivery_failure_notification(self, send_user_name: str, send_user_id: str,
                                                  item_id: str, error_message: str, chat_id: str = None):
        """发送自动发货失败通知"""
        try:
            from common.db.compat import db_manager

            # 检查消息过滤规则（跳过消息通知）
            # 自动发货通知此前不走过滤，导致"发货成功"等结果无法被消息过滤屏蔽，此处补齐。
            # 匹配对象为发货结果文本 error_message（即通知中的"结果"字段），
            # 这样配置"发货成功"只屏蔽成功通知，失败通知的错误信息不含该关键词，仍正常发送。
            try:
                filter_keywords = db_manager.get_message_filter_keywords(self.cookie_id, 'skip_notify')
                if filter_keywords:
                    for keyword in filter_keywords:
                        if keyword and keyword in (error_message or ''):
                            logger.info(f"📱 【消息过滤】自动发货通知包含过滤关键词「{keyword}」，跳过通知")
                            return
            except Exception as e:
                logger.warning(f"📱 检查自动发货通知过滤规则失败: {self._safe_str(e)}")

            # 获取账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)
            if not notifications:
                logger.warning("未配置消息通知，跳过自动发货通知")
                return

            # 获取账号备注
            remark = ""
            try:
                account_details = db_manager.get_cookie_details(self.cookie_id)
                if account_details:
                    remark = account_details.get("remark") or ""
            except Exception as e:
                logger.warning(f"获取账号详情失败: {e}")

            # 构建通知内容（与旧框架保持一致）
            account_desc = f"{self.cookie_id}({remark})" if remark else self.cookie_id
            notification_message = f"🚨 自动发货通知\n\n" \
                                 f"闲鱼账号: {account_desc}\n" \
                                 f"买家: {send_user_name} (ID: {send_user_id})\n" \
                                 f"商品ID: {item_id}\n" \
                                 f"聊天ID: {chat_id or '未知'}\n" \
                                 f"结果: {error_message}\n" \
                                 f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                                 f"请及时处理！"

            # 发送通知到各渠道
            await self._send_to_channels(notifications, notification_message)

        except Exception as e:
            logger.error(f"发送自动发货通知异常: {self._safe_str(e)}")

    async def send_token_refresh_notification(self, error_message: str, notification_type: str = "token_refresh",
                                             chat_id: str = None, attachment_path: str = None, 
                                             verification_url: str = None):
        """发送Token刷新异常通知
        
        Args:
            error_message: 错误消息
            notification_type: 通知类型
            chat_id: 聊天ID（可选）
            attachment_path: 附件路径（可选）
            verification_url: 验证链接（可选）
        """
        try:
            # 检查是否是正常的令牌过期，跳过通知
            if self._is_normal_token_expiry(error_message):
                logger.warning(f"检测到正常的令牌过期，跳过通知: {error_message}")
                return

            current_time = time.time()
            last_time = self.last_notification_time.get(notification_type, 0)

            # 根据错误类型决定冷却时间
            if self._is_token_related_error(error_message):
                cooldown_time = self.token_refresh_notification_cooldown
                cooldown_desc = "3小时"
            else:
                cooldown_time = self.notification_cooldown
                cooldown_desc = f"{self.notification_cooldown // 60}分钟"

            # 检查冷却时间
            if current_time - last_time < cooldown_time:
                remaining_time = cooldown_time - (current_time - last_time)
                remaining_hours = int(remaining_time // 3600)
                remaining_minutes = int((remaining_time % 3600) // 60)
                if remaining_hours > 0:
                    time_desc = f"{remaining_hours}小时{remaining_minutes}分钟"
                else:
                    time_desc = f"{remaining_minutes}分钟"
                logger.warning(f"Token刷新通知在冷却期内，跳过发送 (还需等待 {time_desc})")
                return

            from common.db.compat import db_manager
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.warning("未配置消息通知，跳过Token刷新通知")
                return

            # 构造通知消息 - 根据通知类型使用不同标题
            notification_title_map = {
                "password_login_success": "🎉 账号密码登录成功",
                "password_error": "❌ 账号密码登录失败",
                "password_login_verification": "⚠️ 需要人脸验证",
                "captcha_success_auto_update": "✅ 滑块验证成功",
                "captcha_max_retries_exceeded": "⚠️ 滑块验证失败",
                "captcha_dependency_missing": "⚠️ 滑块验证模块缺失",
                "no_credentials": "⚠️ 未配置登录凭据",
                "token_refresh_failed": "❌ Token刷新失败",
                "token_refresh_exception": "❌ Token刷新异常",
                "cookie_update_failed": "❌ Cookie更新失败",
                "db_update_failed": "❌ 数据库更新失败",
                "cookie_id_missing": "⚠️ Cookie ID缺失",
                "face_verification_required": "⚠️ 需要人脸验证",
                "face_verification_timeout": "⚠️ 人脸验证超时",
                "account_disabled": "⚠️ 账号已自动禁用",
                "baxia_punish_captcha": "⚠️ 触发风控图形验证",
            }
            
            # 获取通知标题
            notification_title = notification_title_map.get(notification_type, "🔔 系统通知")
            
            # 获取账号备注
            remark = ""
            try:
                account_details = db_manager.get_cookie_details(self.cookie_id)
                if account_details:
                    remark = account_details.get("remark") or ""
            except Exception as e:
                logger.warning(f"获取账号详情失败: {e}")

            account_desc = f"{self.cookie_id}({remark})" if remark else self.cookie_id

            # 根据不同情况构建通知消息
            if "滑块验证成功" in error_message:
                notification_msg = f"{notification_title}\n\n{error_message}\n\n闲鱼账号: {account_desc}\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            elif "登录成功" in error_message or notification_type == "password_login_success":
                notification_msg = f"{notification_title}\n\n{error_message}\n\n闲鱼账号: {account_desc}\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            elif verification_url:
                notification_msg = f"{notification_title}\n\n{error_message}\n\n闲鱼账号: {account_desc}\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n验证链接: {verification_url}\n"
            else:
                notification_msg = f"{notification_title}\n\n闲鱼账号: {account_desc}\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n详情: {error_message}\n\n请检查账号状态。\n"

            notification_sent = await self._send_to_channels(notifications, notification_msg, attachment_path)

            if notification_sent:
                self.last_notification_time[notification_type] = current_time
                next_send_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time + cooldown_time))
                logger.info(f"Token刷新通知已发送，下次可发送时间: {next_send_time}")

        except Exception as e:
            logger.error(f"处理Token刷新通知失败: {self._safe_str(e)}")

    def _is_normal_token_expiry(self, error_message: str) -> bool:
        """检查是否是正常的令牌过期"""
        no_notification_keywords = [
            'FAIL_SYS_TOKEN_EXOIRED::令牌过期',
            'FAIL_SYS_TOKEN_EXPIRED::令牌过期',
            'FAIL_SYS_TOKEN_EXOIRED',
            'FAIL_SYS_TOKEN_EXPIRED',
            'FAIL_SYS_TOKEN_EMPTY::令牌为空',
            'FAIL_SYS_TOKEN_EMPTY',
            '令牌过期',
            '令牌为空',
            'FAIL_SYS_SESSION_EXPIRED::Session过期',
            'FAIL_SYS_SESSION_EXPIRED',
            'Session过期',
            'Token定时刷新失败，将自动重试',
            'Token定时刷新失败'
        ]

        for keyword in no_notification_keywords:
            if keyword in error_message:
                return True
        return False

    def _is_token_related_error(self, error_message: str) -> bool:
        """检查是否是Token相关的错误"""
        token_error_keywords = [
            'Token刷新失败', 'Token刷新异常', 'token刷新失败', 'token刷新异常',
            'TOKEN刷新失败', 'TOKEN刷新异常',
            'FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR',
            '哎哟喂,被挤爆啦', '请稍后重试',
            'punish?x5secdata', 'captcha',
            '无法获取有效token', '无法获取有效Token',
            'Token获取失败', 'token获取失败', 'TOKEN获取失败',
            'Token定时刷新失败', 'token定时刷新失败', 'TOKEN定时刷新失败',
            '初始化时无法获取有效Token', '初始化时无法获取有效token',
            'accessToken', 'access_token', '_m_h5_tk',
            'mtop.taobao.idlemessage.pc.login.token'
        ]

        error_message_lower = error_message.lower()
        for keyword in token_error_keywords:
            if keyword.lower() in error_message_lower:
                return True
        return False

    async def _send_to_channels(self, notifications: list, message: str, attachment_path: str = None) -> bool:
        """发送通知到各个渠道
        
        Args:
            notifications: 通知配置列表
            message: 通知消息
            attachment_path: 附件路径（可选）
            
        Returns:
            是否成功发送
        """
        notification_sent = False
        
        for notification in notifications:
            if not notification.get('enabled', True):
                continue

            channel_type = notification.get('channel_type')
            channel_config = notification.get('channel_config')
            
            logger.info(f"📱 通知渠道: {channel_type}, 配置: {channel_config}")

            try:
                config_data = parse_notification_config(channel_config)
                logger.info(f"📱 解析后配置: {config_data}")

                if channel_type in ('ding_talk', 'dingtalk'):
                    await send_dingtalk_notification(config_data, message)
                    notification_sent = True
                elif channel_type in ('feishu', 'lark'):
                    await send_feishu_notification(config_data, message)
                    notification_sent = True
                elif channel_type == 'bark':
                    await send_bark_notification(config_data, message)
                    notification_sent = True
                elif channel_type == 'email':
                    await send_email_notification(config_data, message, attachment_path)
                    notification_sent = True
                elif channel_type == 'webhook':
                    await send_webhook_notification(config_data, message)
                    notification_sent = True
                elif channel_type in ('wechat', 'wechat_work'):
                    await send_wechat_notification(config_data, message)
                    notification_sent = True
                elif channel_type == 'telegram':
                    await send_telegram_notification(config_data, message)
                    notification_sent = True
                else:
                    logger.warning(f"不支持的通知渠道类型: {channel_type}")

            except Exception as notify_error:
                logger.error(f"发送通知失败 ({notification.get('channel_name', 'Unknown')}): {self._safe_str(notify_error)}")

        return notification_sent
