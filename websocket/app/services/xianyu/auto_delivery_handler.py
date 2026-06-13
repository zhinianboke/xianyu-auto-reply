"""
自动发货处理模块
负责处理自动发货相关的所有逻辑，包括：
- 发货触发检测
- 发货内容获取（API、文本、批量数据、图片）
- 发货确认
- 免拼发货
- 发货冷却检查
- 亦凡API委托给YifanApiHandler处理
"""

import asyncio
import json
import time
import hashlib
import aiohttp
from loguru import logger

from app.services.xianyu.delivery_utils import (
    process_delivery_content_with_description,
    replace_order_context_variables as _replace_order_context_variables,
    recursive_replace_params
)
from app.services.xianyu.yifan_api_handler import YifanApiHandler
from common.utils.fish_nick_utils import get_buyer_fish_nick
from common.utils.delivery_cooldown import delivery_cooldown as _delivery_cooldown
from app.services.xianyu.delivery_pipeline import DeliveryPipeline, DeliveryContext


class AutoDeliveryHandler:
    """自动发货处理器"""
    
    # 配置标志：是否使用新的发货管道（默认关闭，保持向后兼容）
    USE_DELIVERY_PIPELINE = False
    
    def __init__(self, parent):
        """
        初始化自动发货处理器
        
        Args:
            parent: XianyuLive实例，用于访问共享资源
        """
        self.parent = parent
        # 初始化亦凡API处理器
        self._yifan_api_handler = YifanApiHandler(self)
        # 最近一次发货失败原因（用于记录到数据库）
        self._last_delivery_fail_reason = None
        # 最近一次获取的买家闲鱼明文昵称（pre_check 阶段获取，供写库及备注/API 变量复用）
        self._current_buyer_fish_nick = None
        # 最近一次匹配到的卡券来源/类型（供多数量循环判断是否退化为单张）
        # - card_source: own / dock_l1 / dock_l2，对接卡券类需在多数量场景退化为 1 张避免代理订单结算 bug
        # - card_type:   text / data / image / api / yifan_api，固定内容类（text/image）需退化为 1 张避免重复发同样内容
        self._last_delivery_card_source = None
        self._last_delivery_card_type = None
    
    # ==================== 属性代理 ====================
    
    @property
    def cookie_id(self):
        return self.parent.cookie_id
    
    @property
    def cookies_str(self):
        return self.parent.cookies_str
    
    @cookies_str.setter
    def cookies_str(self, value):
        self.parent.cookies_str = value
    
    @property
    def cookies(self):
        return self.parent.cookies
    
    @cookies.setter
    def cookies(self, value):
        self.parent.cookies = value
    
    @property
    def session(self):
        return self.parent.session
    
    @property
    def current_token(self):
        return self.parent.current_token
    
    @current_token.setter
    def current_token(self, value):
        self.parent.current_token = value
    
    @property
    def last_token_refresh_time(self):
        return self.parent.last_token_refresh_time
    
    @last_token_refresh_time.setter
    def last_token_refresh_time(self, value):
        self.parent.last_token_refresh_time = value
    
    @property
    def token_refresh_interval(self):
        return self.parent.token_refresh_interval
    
    @property
    def ws(self):
        return self.parent.ws
    
    @property
    def delivery_sent_orders(self):
        return self.parent.delivery_sent_orders
    
    @property
    def last_delivery_time(self):
        return self.parent.last_delivery_time
    
    @property
    def delivery_cooldown(self):
        return self.parent.delivery_cooldown
    
    @property
    def order_status_handler(self):
        return getattr(self.parent, 'order_status_handler', None)
    
    @property
    def _order_locks(self):
        return self.parent._order_locks
    
    @property
    def _lock_usage_times(self):
        return self.parent._lock_usage_times
    
    @property
    def _lock_hold_info(self):
        return self.parent._lock_hold_info
    
    @property
    def confirmed_orders(self):
        return self.parent.confirmed_orders
    
    @property
    def order_confirm_cooldown(self):
        return self.parent.order_confirm_cooldown
    
    @property
    def yifan_account_lock(self):
        return self.parent.yifan_account_lock
    
    @property
    def yifan_account_waiting(self):
        return self.parent.yifan_account_waiting
    
    # ==================== 辅助方法代理 ====================
    
    def _safe_str(self, obj):
        return self.parent._safe_str(obj)
    
    def _handle_response_cookies(self, response) -> None:
        """处理响应中的set-cookie，更新本地cookie
        
        令牌过期时服务端会在响应头中返回新的cookie（包含新的_m_h5_tk），
        存储后重试请求即可使用新的token签名
        
        Args:
            response: HTTP响应对象
        """
        try:
            from common.utils.xianyu_utils import trans_cookies
            
            if 'set-cookie' in response.headers:
                new_cookies = {}
                for cookie in response.headers.getall('set-cookie', []):
                    if '=' in cookie:
                        name, value = cookie.split(';')[0].split('=', 1)
                        new_cookies[name.strip()] = value.strip()
                
                if new_cookies:
                    existing_cookies = trans_cookies(self.cookies_str)
                    existing_cookies.update(new_cookies)
                    self.cookies_str = '; '.join([f"{k}={v}" for k, v in existing_cookies.items()])
                    self.cookies = existing_cookies
                    logger.info(f"【{self.cookie_id}】已从响应中更新Cookie（含{len(new_cookies)}个字段）")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】处理响应Cookie失败: {self._safe_str(e)}")
    
    async def create_session(self):
        return await self.parent.create_session()
    
    async def send_msg(self, websocket, chat_id, send_user_id, content):
        return await self.parent.send_msg(websocket, chat_id, send_user_id, content)
    
    async def send_image_msg(self, websocket, chat_id, send_user_id, image_url, card_id=None, keyword=None, default_reply_item_id=None, image_index=None):
        return await self.parent.send_image_msg(websocket, chat_id, send_user_id, image_url, card_id=card_id, keyword=keyword, default_reply_item_id=default_reply_item_id, image_index=image_index)
    
    async def _send_msg_with_retry(self, websocket, chat_id: str, send_user_id: str,
                                    content: str, max_retries: int = 5, retry_delay: int = 2) -> dict:
        """发送文本消息（带重试机制）
        
        失败后等待指定秒数再重试，重试时尝试获取最新的WebSocket连接（可能已重连）。
        
        Args:
            websocket: WebSocket连接
            chat_id: 会话ID
            send_user_id: 接收者用户ID
            content: 消息内容
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            
        Returns:
            发送结果字典
        """
        current_ws = websocket
        result = None
        for attempt in range(max_retries + 1):
            result = await self.send_msg(current_ws, chat_id, send_user_id, content)
            if isinstance(result, dict) and result.get("success"):
                if attempt > 0:
                    logger.info(f"【{self.cookie_id}】消息重试第{attempt}次发送成功: {content[:30]}...")
                return result
            # 最后一次不再重试
            if attempt >= max_retries:
                break
            error_msg = result.get("error_message", "未知错误") if isinstance(result, dict) else "返回值异常"
            logger.warning(f"【{self.cookie_id}】发送消息失败(第{attempt+1}次): {error_msg}，{retry_delay}秒后重试...")
            await asyncio.sleep(retry_delay)
            # 重试时尝试获取最新的WebSocket连接（连接可能已重建）
            try:
                latest_ws = self.ws
                if latest_ws is not None and latest_ws != current_ws:
                    current_ws = latest_ws
                    logger.info(f"【{self.cookie_id}】检测到新的WebSocket连接，使用新连接重试")
            except Exception:
                pass
        return result or {"success": False, "mode": "text", "content": content, "error_message": "重试耗尽仍失败"}
    
    async def _send_image_msg_with_retry(self, websocket, chat_id: str, send_user_id: str,
                                          image_url: str, max_retries: int = 5, retry_delay: int = 2,
                                          **kwargs) -> dict:
        """发送图片消息（带重试机制）
        
        Args:
            websocket: WebSocket连接
            chat_id: 会话ID
            send_user_id: 接收者用户ID
            image_url: 图片URL
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            **kwargs: 传递给 send_image_msg 的其他参数
            
        Returns:
            发送结果字典
        """
        current_ws = websocket
        result = None
        for attempt in range(max_retries + 1):
            result = await self.send_image_msg(current_ws, chat_id, send_user_id, image_url, **kwargs)
            if isinstance(result, dict) and result.get("success"):
                if attempt > 0:
                    logger.info(f"【{self.cookie_id}】图片重试第{attempt}次发送成功: {image_url[:50]}...")
                return result
            if attempt >= max_retries:
                break
            error_msg = result.get("error_message", "未知错误") if isinstance(result, dict) else "返回值异常"
            logger.warning(f"【{self.cookie_id}】发送图片失败(第{attempt+1}次): {error_msg}，{retry_delay}秒后重试...")
            await asyncio.sleep(retry_delay)
            try:
                latest_ws = self.ws
                if latest_ws is not None and latest_ws != current_ws:
                    current_ws = latest_ws
                    logger.info(f"【{self.cookie_id}】检测到新的WebSocket连接，使用新连接重试")
            except Exception:
                pass
        return result or {"success": False, "mode": "image", "image_url": image_url, "error_message": "重试耗尽仍失败"}
    
    async def _send_text_with_separator(self, websocket, chat_id: str, send_user_id: str, text: str, msg_time: str = "", user_url: str = "", send_results: list = None) -> bool:
        """发送文本消息，支持 ###### 分隔符拆分为多条消息
        
        Args:
            websocket: WebSocket连接
            chat_id: 会话ID
            send_user_id: 接收者用户ID
            text: 消息内容
            msg_time: 消息时间（用于日志）
            user_url: 用户URL（用于日志）
            
        Returns:
            是否全部发送成功
        """
        all_success = True
        # 检查是否包含分隔符
        if '######' in text:
            messages = [msg.strip() for msg in text.split('######') if msg.strip()]
            logger.info(f"【{self.cookie_id}】检测到分隔符，拆分为 {len(messages)} 条消息")
            
            for i, msg in enumerate(messages):
                result = await self._send_msg_with_retry(websocket, chat_id, send_user_id, msg)
                if send_results is not None and isinstance(result, dict):
                    send_results.append(result)
                send_ok = isinstance(result, dict) and result.get("success", False)
                if send_ok:
                    if msg_time and user_url:
                        logger.info(f'[{msg_time}] 【自动发货文字】第 {i+1}/{len(messages)} 条已向 {user_url} 发送: {msg[:50]}...')
                    else:
                        logger.info(f"【{self.cookie_id}】发送文本消息 {i+1}/{len(messages)}: {msg[:50]}...")
                else:
                    all_success = False
                    error_msg = result.get("error_message", "未知错误") if isinstance(result, dict) else "返回值异常"
                    if msg_time and user_url:
                        logger.error(f'[{msg_time}] 【自动发货文字】第 {i+1}/{len(messages)} 条发送失败(已重试5次): {error_msg}')
                    else:
                        logger.error(f"【{self.cookie_id}】发送文本消息 {i+1}/{len(messages)} 失败(已重试5次): {error_msg}")
                
                # 多条消息之间添加短暂延迟
                if i < len(messages) - 1:
                    await asyncio.sleep(0.5)
        else:
            # 单条消息直接发送
            result = await self._send_msg_with_retry(websocket, chat_id, send_user_id, text)
            if send_results is not None and isinstance(result, dict):
                send_results.append(result)
            send_ok = isinstance(result, dict) and result.get("success", False)
            if send_ok:
                if msg_time and user_url:
                    logger.info(f'[{msg_time}] 【自动发货文字】已向 {user_url} 发送: {text[:50]}...')
                else:
                    logger.info(f"【{self.cookie_id}】发送文本消息: {text[:50]}...")
            else:
                all_success = False
                error_msg = result.get("error_message", "未知错误") if isinstance(result, dict) else "返回值异常"
                if msg_time and user_url:
                    logger.error(f'[{msg_time}] 【自动发货文字】发送失败(已重试5次): {error_msg}')
                else:
                    logger.error(f"【{self.cookie_id}】发送文本消息失败(已重试5次): {error_msg}")
        return all_success
    
    async def send_notification(self, send_user_name, send_user_id, content, item_id, chat_id):
        """发送通知 - 直接调用NotificationManager"""
        try:
            from app.services.xianyu.notification_manager import NotificationManager
            notification_manager = NotificationManager(self.cookie_id)
            return await notification_manager.send_notification(send_user_name, send_user_id, content, item_id, chat_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送通知失败: {self._safe_str(e)}")
    
    async def _update_delivery_fail_reason(self, order_no: str, fail_reason: str):
        """更新订单发货失败原因到数据库"""
        try:
            from common.services.order_service import OrderService
            from common.db.session import async_session_maker
            async with async_session_maker() as db_session:
                order_service = OrderService(db_session)
                await order_service.update_order_delivery_fail_reason(order_no, fail_reason)
                logger.info(f"【{self.cookie_id}】订单 {order_no} 发货失败原因已记录")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】更新订单发货失败原因失败: {self._safe_str(e)}")

    async def send_delivery_failure_notification(self, send_user_name, send_user_id, item_id, error_message, chat_id):
        """发送发货通知 - 直接调用NotificationManager"""
        try:
            from app.services.xianyu.notification_manager import NotificationManager
            notification_manager = NotificationManager(self.cookie_id)
            return await notification_manager.send_delivery_failure_notification(send_user_name, send_user_id, item_id, error_message, chat_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送发货通知失败: {self._safe_str(e)}")
    
    async def _record_delivery_log(self, chat_id: str, item_id: str, sender_user_id: str,
                                    sender_user_name: str, msg_time: str, order_id: str,
                                    delivery_contents: list, send_results: list,
                                    any_send_failed: bool) -> None:
        """将自动发货的发送结果写入消息日志表
        
        Args:
            chat_id: 会话ID
            item_id: 商品ID
            sender_user_id: 买家用户ID
            sender_user_name: 买家用户名
            msg_time: 消息时间
            order_id: 订单号
            delivery_contents: 发货内容列表
            send_results: 每条消息的实际发送结果
            any_send_failed: 是否有发送失败
        """
        try:
            from app.services.xianyu.auto_reply_log_service import AutoReplyLogService
            
            # 统计成功/失败数
            success_count = sum(1 for r in send_results if r.get("success"))
            fail_count = len(send_results) - success_count
            
            # 合并发货内容用于展示（去掉内部标记前缀）
            display_contents = []
            for content in delivery_contents:
                if content.startswith("__DELIVERY_WITH_IMAGES__"):
                    display_contents.append("[图文发货]")
                elif content.startswith("__MULTI_IMAGE_SEND__"):
                    display_contents.append("[多图片发货]")
                elif content.startswith("__IMAGE_SEND__"):
                    display_contents.append("[图片发货]")
                else:
                    display_contents.append(content[:200])
            
            # 提取失败原因
            error_message = None
            if any_send_failed:
                errors = [r.get("error_message", "发送失败") for r in send_results if not r.get("success")]
                error_message = "；".join(errors[:3]) if errors else "部分消息发送失败"

            # 发送状态：发送层（WebSocket 发送）失败直接判定 failed；
            # 全部发出成功则先置 unknown，由后台任务等服务端响应后回写 success/failed
            send_status = "failed" if any_send_failed else "unknown"
            send_fail_reason = error_message if any_send_failed else None
            # 收集本次发出文本消息的 (future, mid)，供异步检测是否被安全拦截
            pending_send_waiters = [
                (r.get("send_future"), r.get("mid"))
                for r in send_results
                if r.get("send_future") is not None
            ]

            log_payload = {
                "sender_user_id": sender_user_id,
                "sender_user_name": sender_user_name,
                "source_message": f"[自动发货] 订单: {order_id}",
                "chat_id": chat_id,
                "item_id": item_id or None,
                "order_no": order_id or None,
                "msg_time": msg_time,
                "process_status": "failed" if any_send_failed else "success",
                "decision_reason": "auto_delivery",
                "reply_strategy": "auto_delivery",
                "reply_mode": "text",
                "reply_text": "\n---\n".join(display_contents),
                "error_message": error_message,
                "send_status": send_status,
                "send_fail_reason": send_fail_reason,
                "send_result_json": send_results,
                "context_snapshot": {
                    "order_id": order_id,
                    "delivery_count": len(delivery_contents),
                    "send_success": success_count,
                    "send_fail": fail_count,
                },
            }

            log_service = AutoReplyLogService(self.cookie_id)
            log_id = await log_service.record_message(log_payload)
            logger.info(f"【{self.cookie_id}】自动发货消息日志已记录: 成功{success_count}/失败{fail_count}")

            # 发出成功且日志写入成功时，起后台任务异步等待发送结果并回写发送状态
            if log_id and not any_send_failed and pending_send_waiters:
                self._spawn_delivery_send_status_writeback(log_service, log_id, pending_send_waiters)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】写入自动发货消息日志失败: {self._safe_str(e)}")

    def _spawn_delivery_send_status_writeback(
        self, log_service, log_id: int, waiters: list
    ) -> None:
        """起后台任务：异步等待自动发货的发送结果并回写日志发送状态

        不阻塞发货主流程。复用实例的任务追踪器创建后台任务。

        Args:
            log_service: 日志服务实例（复用同一个，避免重复构造）
            log_id: 日志主键ID
            waiters: 本次发出消息的 (send_future, mid) 列表
        """
        try:
            # handler 自身无任务追踪器，复用 parent（XianyuAsync）的追踪任务创建方法
            self.parent._create_tracked_task(
                self._writeback_delivery_send_status(log_service, log_id, waiters)
            )
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】启动发货发送状态回写任务失败 log_id={log_id}: {self._safe_str(e)}")

    async def _writeback_delivery_send_status(
        self, log_service, log_id: int, waiters: list
    ) -> None:
        """等待各发送响应，按结果回写自动发货日志的发送状态

        - 任一消息被服务端拦截（返回 reason）→ send_status=failed，记录失败原因
        - 全部无拦截响应（含正常发送、超时）→ send_status=success

        Args:
            log_service: 日志服务实例
            log_id: 日志主键ID
            waiters: 本次发出消息的 (send_future, mid) 列表
        """
        try:
            wait_fn = getattr(self.parent, "wait_send_reject_reason", None)
            if not callable(wait_fn):
                return
            reasons = []
            for send_future, mid in waiters:
                reason = await wait_fn(send_future, mid)
                if reason:
                    reasons.append(reason)
            if reasons:
                await log_service.safe_update_send_status(log_id, "failed", "；".join(reasons))
                logger.warning(
                    f"【{self.cookie_id}】自动发货发送被拦截 log_id={log_id}: {'；'.join(reasons)}"
                )
            else:
                await log_service.safe_update_send_status(log_id, "success", None)
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】回写发货发送状态异常 log_id={log_id}: {self._safe_str(e)}")
    
    def is_lock_held(self, lock_key: str) -> bool:
        return self.parent.is_lock_held(lock_key)
    
    async def _delayed_lock_release(self, lock_key: str, delay_minutes: int = 10):
        return await self.parent._delayed_lock_release(lock_key, delay_minutes)
    
    async def fetch_order_detail_info(self, order_id: str, item_id: str = None, buyer_id: str = None):
        """获取订单详情信息，并同步更新到数据库
        
        获取逻辑（参照旧框架）：
        1. 先检查数据库缓存，如果有完整的规格信息则直接返回
        2. 如果数据库中没有规格信息，通过API获取订单详情
        3. 获取到详情后更新到数据库
        """
        try:
            from common.services.order_service import OrderService
            from common.db.session import async_session_maker
            
            async with async_session_maker() as db_session:
                order_service = OrderService(db_session)
                # 先尝试从数据库获取订单
                existing_order = await order_service.get_order_by_id(order_id)
                
                result = {}
                if existing_order:
                    result = {
                        'spec_name': existing_order.spec_name or '',
                        'spec_value': existing_order.spec_value or '',
                        'amount': existing_order.amount,
                        'quantity': str(existing_order.quantity) if existing_order.quantity else '1',
                        'receiver_name': existing_order.receiver_name or '',
                        'receiver_phone': existing_order.receiver_phone or '',
                        'receiver_address': existing_order.receiver_address or '',
                    }
                    
                    # 如果数据库中已有规格信息，直接返回
                    if result.get('spec_name') and result.get('spec_value'):
                        logger.info(f"【{self.cookie_id}】订单 {order_id} 从数据库获取规格信息: {result['spec_name']}={result['spec_value']}")
                        return result
                
                # 数据库中没有规格信息，通过API获取
                logger.info(f"【{self.cookie_id}】订单 {order_id} 数据库无规格信息，尝试通过API获取...")
                api_result = await self._fetch_order_detail_from_api(order_id)
                
                if api_result:
                    # 更新到数据库
                    await self._update_order_detail_to_db(
                        db_session=db_session,
                        order_id=order_id,
                        item_id=item_id,
                        buyer_id=buyer_id,
                        order_detail=api_result
                    )
                    logger.info(f"【{self.cookie_id}】订单 {order_id} API获取成功: 规格={api_result.get('spec_name')}:{api_result.get('spec_value')}")
                    return api_result
                else:
                    logger.warning(f"【{self.cookie_id}】订单 {order_id} API获取失败")
                    # API获取失败，返回数据库中的数据（可能不完整）
                    return result if result else None
                    
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取订单详情失败: {self._safe_str(e)}")
            return None
    
    async def _fetch_order_detail_from_api(self, order_id: str, retry_count: int = 0) -> dict:
        """通过API接口获取订单详情
        
        参照旧框架 backend/app/services/order/detail_fetcher.py 实现
        
        Args:
            order_id: 订单号
            retry_count: 当前重试次数
            
        Returns:
            订单详情字典，包含spec_name, spec_value, amount, quantity等
        """
        max_retry = 3
        
        if not self.cookies_str:
            logger.warning(f"【{self.cookie_id}】订单 {order_id} API获取失败：未提供Cookie")
            return None
        
        try:
            import json
            import time
            import aiohttp
            from common.utils.xianyu_utils import trans_cookies, generate_sign
            
            cookies = trans_cookies(self.cookies_str)
            timestamp = str(int(time.time() * 1000))
            data_val = json.dumps({"tid": order_id}, separators=(',', ':'))
            
            # 从Cookie中获取token用于签名
            token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
            if not token:
                logger.warning(f"【{self.cookie_id}】订单 {order_id} Cookie中未找到_m_h5_tk token")
            
            sign = generate_sign(timestamp, token, data_val)
            
            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': sign,
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.idle.web.trade.order.detail',
                'sessionOption': 'AutoLoginOnly',
                'spm_cnt': 'a21ybx.order-detail.0.0',
            }
            
            headers = {
                'accept': 'application/json',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://www.goofish.com',
                'referer': 'https://www.goofish.com/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
                'cookie': self.cookies_str.replace('\n', '').replace('\r', '') if self.cookies_str else '',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://h5api.m.goofish.com/h5/mtop.idle.web.trade.order.detail/1.0/',
                    params=params,
                    data={'data': data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as response:
                    res_json = await response.json()
                    
                    # 处理响应中的set-cookie，更新本地cookie（令牌过期时服务端会返回新cookie）
                    self._handle_response_cookies(response)
                    
                    # 检查响应是否成功
                    ret_list = res_json.get('ret', [])
                    logger.info(f"【{self.cookie_id}】订单 {order_id} API响应: ret={ret_list}")
                    
                    if not any('SUCCESS' in ret for ret in ret_list):
                        logger.warning(f"【{self.cookie_id}】订单 {order_id} API调用失败: {ret_list}")
                        # API失败重试（令牌过期时set-cookie已更新，重试可用新token）
                        if retry_count < max_retry - 1:
                            logger.info(f"【{self.cookie_id}】订单 {order_id} API请求失败，准备重试({retry_count + 1}/{max_retry - 1})...")
                            await asyncio.sleep(0.5)
                            return await self._fetch_order_detail_from_api(order_id, retry_count + 1)
                        return None
                    
                    # 解析返回数据
                    return self._parse_order_detail_response(order_id, res_json)
                    
        except asyncio.TimeoutError:
            logger.warning(f"【{self.cookie_id}】订单 {order_id} API请求超时（第{retry_count + 1}次）")
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self._fetch_order_detail_from_api(order_id, retry_count + 1)
            return None
        except Exception as e:
            logger.error(f"【{self.cookie_id}】订单 {order_id} API请求异常（第{retry_count + 1}次）: {self._safe_str(e)}")
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self._fetch_order_detail_from_api(order_id, retry_count + 1)
            return None
    
    def _parse_order_detail_response(self, order_id: str, res_json: dict) -> dict:
        """解析API返回的订单详情数据
        
        Args:
            order_id: 订单号
            res_json: API返回的JSON数据
            
        Returns:
            解析后的订单详情字典
        """
        try:
            data = res_json.get('data', {})
            components = data.get('components', [])
            
            result = {
                'spec_name': '',
                'spec_value': '',
                'quantity': '1',
                'amount': '',
                'receiver_name': '',
                'receiver_phone': '',
                'receiver_address': '',
            }
            
            for component in components:
                render_type = component.get('render', '')
                comp_data = component.get('data', {})
                
                # 解析订单信息（包含商品信息）
                if render_type == 'orderInfoVO':
                    item_info = comp_data.get('itemInfo', {})
                    
                    # 获取数量
                    buy_amount = item_info.get('buyAmount', '1')
                    result['quantity'] = str(buy_amount)
                    
                    # 获取价格
                    price = item_info.get('price', '')
                    if price:
                        result['amount'] = str(price)
                    
                    # 获取规格信息（格式：规格名:规格值）
                    sku_info = item_info.get('skuInfo', '')
                    if sku_info and ':' in sku_info:
                        parts = sku_info.split(':', 1)
                        result['spec_name'] = parts[0].strip()
                        result['spec_value'] = parts[1].strip() if len(parts) > 1 else ''
                    
                    logger.info(f"【{self.cookie_id}】订单 {order_id} 解析商品信息: 价格={result['amount']}, 数量={result['quantity']}, 规格={sku_info}")
                
                # 解析收货地址信息
                elif render_type == 'addressInfoVO':
                    result['receiver_name'] = comp_data.get('name', '')
                    result['receiver_phone'] = comp_data.get('phoneNumber', '')
                    result['receiver_address'] = comp_data.get('address', '')
                    
                    logger.info(f"【{self.cookie_id}】订单 {order_id} 解析收货信息: 姓名={result['receiver_name']}")
            
            return result
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】订单 {order_id} 解析API响应失败: {self._safe_str(e)}")
            return None
    
    async def _update_order_detail_to_db(self, db_session, order_id: str, item_id: str, buyer_id: str, order_detail: dict):
        """将订单详情更新到数据库"""
        try:
            from sqlalchemy import select, update
            from common.models.xy_order import XYOrder
            
            spec_name = order_detail.get('spec_name', '')
            spec_value = order_detail.get('spec_value', '')
            amount = order_detail.get('amount')
            quantity = order_detail.get('quantity', '1')
            receiver_name = order_detail.get('receiver_name', '')
            receiver_phone = order_detail.get('receiver_phone', '')
            receiver_address = order_detail.get('receiver_address', '')
            
            # 查询现有订单
            stmt = select(XYOrder).where(XYOrder.order_no == order_id)
            result = await db_session.execute(stmt)
            existing_order = result.scalars().first()
            
            if existing_order:
                update_values = {}
                
                # 基本信息：数据库为空时才更新
                if item_id and not existing_order.item_id:
                    update_values['item_id'] = item_id
                if buyer_id and not existing_order.buyer_id:
                    update_values['buyer_id'] = buyer_id
                
                # 订单详情：有值就更新
                if spec_name:
                    update_values['spec_name'] = spec_name
                if spec_value:
                    update_values['spec_value'] = spec_value
                if amount:
                    update_values['amount'] = amount
                if quantity:
                    update_values['quantity'] = int(quantity) if quantity else 1
                
                # 收货人信息：新值不为空，且（旧值为空 或 旧值包含脱敏字符*）时更新
                def should_update_receiver(new_val: str, old_val: str) -> bool:
                    if not new_val:
                        return False
                    if not old_val:
                        return True
                    if '*' in old_val and '*' not in new_val:
                        return True
                    return False
                
                if should_update_receiver(receiver_name, existing_order.receiver_name):
                    update_values['receiver_name'] = receiver_name
                if should_update_receiver(receiver_phone, existing_order.receiver_phone):
                    update_values['receiver_phone'] = receiver_phone
                if should_update_receiver(receiver_address, existing_order.receiver_address):
                    update_values['receiver_address'] = receiver_address
                
                if update_values:
                    stmt = update(XYOrder).where(XYOrder.order_no == order_id).values(**update_values)
                    await db_session.execute(stmt)
                    await db_session.commit()
                    logger.info(f"【{self.cookie_id}】订单 {order_id} 详情已更新: {list(update_values.keys())}")
            else:
                logger.warning(f"【{self.cookie_id}】订单 {order_id} 不存在，无法更新详情")
                
        except Exception as e:
            logger.error(f"【{self.cookie_id}】更新订单详情到数据库失败: {self._safe_str(e)}")
    
    def is_auto_confirm_enabled(self) -> bool:
        return self.parent.is_auto_confirm_enabled()
    
    def is_confirm_before_send_enabled(self) -> bool:
        """检查是否开启发货成功再发卡券开关"""
        return self.parent.is_confirm_before_send_enabled()

    def is_send_before_confirm_enabled(self) -> bool:
        """检查是否开启卡券发送成功再确认发货开关"""
        return self.parent.is_send_before_confirm_enabled()
    
    # ==================== 发货冷却检查 ====================
    
    async def can_auto_delivery(self, order_id: str) -> bool:
        """检查是否可以进行自动发货（防重复发货）- 基于订单ID
        
        使用 Redis 优先的 DeliveryCooldown 模块（多实例安全），
        Redis 不可用时自动降级为内存缓存。
        """
        if not order_id:
            # 如果没有订单ID，则不进行冷却检查，允许发货
            return True

        in_cooldown = await _delivery_cooldown.check(order_id)
        if in_cooldown:
            logger.info(f"【{self.cookie_id}】订单 {order_id} 在冷却期内，跳过自动发货")
            return False

        return True

    async def mark_delivery_sent(self, order_id: str):
        """标记订单已发货（通过 Redis/内存冷却管理器设置冷却）"""
        # 记录发货时间（用于内存清理，保留向后兼容）
        current_time = time.time()
        self.delivery_sent_orders[order_id] = current_time
        self.last_delivery_time[order_id] = current_time
        # 通过 DeliveryCooldown 模块设置冷却（Redis 优先，降级内存）
        await _delivery_cooldown.set(order_id)
        logger.info(f"【{self.cookie_id}】订单 {order_id} 已标记为发货（冷却期已设置）")


    # ==================== 统一发货处理 ====================

    async def _handle_auto_delivery(self, websocket, message: dict, send_user_name: str, send_user_id: str,
                                   item_id: str, chat_id: str, msg_time: str, override_order_id: str = None,
                                   pre_check_result: dict | None = None):
        """统一处理自动发货逻辑

        Args:
            override_order_id: 如果指定，直接使用此订单ID，跳过从raw_message提取
            pre_check_result: 可选的预先 pre_delivery_check_and_close 结果。
                调用方（如 _handle_card_message / 重发货关键字）若需要在调用免拼接口
                之前先做禁止发货检查，可以预先调用 pre_delivery_check_and_close 拿到
                结果再传入此方法，避免本方法内部重复执行 pre_check 而造成
                "重复关闭订单 / 重复给买家发提示消息 / 重复写 fail_reason" 的副作用。
                若为 None，本方法仍按原逻辑自行调 pre_check。
        """
        # 当启用发货管道时，委托给 DeliveryPipeline 执行
        if self.USE_DELIVERY_PIPELINE:
            pipeline = DeliveryPipeline(self)
            ctx = DeliveryContext(
                websocket=websocket,
                message=message,
                send_user_name=send_user_name,
                send_user_id=send_user_id,
                item_id=item_id,
                chat_id=chat_id,
                msg_time=msg_time,
                override_order_id=override_order_id,
                pre_check_result=pre_check_result,
            )
            result = await pipeline.execute(ctx)
            if not result.success:
                logger.info(f'[{msg_time}] 【{self.cookie_id}】发货管道执行结束: {result.reason}')
            return
        
        try:
            # 检查商品是否属于当前cookies
            if item_id and item_id != "未知商品":
                try:
                    from common.db.compat import db_manager
                    item_info = db_manager.get_item_info(self.cookie_id, item_id)
                    if not item_info:
                        logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 商品 {item_id} 不属于当前账号，跳过自动发货')
                        return
                    logger.warning(f'[{msg_time}] 【{self.cookie_id}】✅ 商品 {item_id} 归属验证通过')
                except Exception as e:
                    logger.error(f'[{msg_time}] 【{self.cookie_id}】检查商品归属失败: {self._safe_str(e)}，跳过自动发货')
                    return

            # 提取订单ID（如果指定了override_order_id则直接使用）
            if override_order_id:
                order_id = override_order_id
                logger.info(f'[{msg_time}] 【{self.cookie_id}】使用指定订单ID: {order_id}（重发货触发）')
            else:
                order_id = self.parent._extract_order_id(message)

            # 如果order_id不存在，直接返回
            if not order_id:
                logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 未能提取到订单ID，跳过自动发货')
                return

            # 订单ID已提取，将在自动发货时进行确认发货处理
            logger.info(f'[{msg_time}] 【{self.cookie_id}】提取到订单ID: {order_id}，将在自动发货时处理确认发货')

            # 检查订单金额，金额为0禁止发货
            try:
                from common.db.compat import db_manager
                order_check = db_manager.get_order_by_id(order_id)
                if order_check:
                    order_amount = order_check.get('amount')
                    if order_amount is not None:
                        from decimal import Decimal
                        if Decimal(str(order_amount)) <= 0:
                            logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 订单 {order_id} 金额为 {order_amount}，禁止自动发货')
                            # 记录失败原因（对外展示统一提示为账号掉线，便于运营快速定位真实原因）
                            await self._update_delivery_fail_reason(order_id, "账号已掉线，请重新登录")
                            return
            except Exception as e:
                logger.warning(f'[{msg_time}] 【{self.cookie_id}】检查订单金额异常: {self._safe_str(e)}')

            # 禁止发货统一拦截：调用 pre_delivery_check_and_close 完成"取设置→评价
            # 检查→命中后发消息+写 fail_reason+按开关关闭订单"全部链路。
            # 返回的 action 决定后续行为：
            #   'allow'     → 正常发货（含 confirm + 卡券）
            #   'block'     → 直接 return（不发卡券）
            #   'card_only' → 跳过 confirm 接口，仅向买家发送卡券（订单已被关闭）
            #
            # 若外部已经预先调用过 pre_check（如小刀卡片场景需要在 freeshipping 之前
            # 拿到 action 决策），则复用外部结果，避免重复执行造成副作用。
            if pre_check_result is not None:
                pre_check = pre_check_result
                logger.info(
                    f'[{msg_time}] 【{self.cookie_id}】使用外部传入的 pre_check 结果，'
                    f'跳过内部重复检查: action={pre_check.get("action", "allow")}'
                )
            else:
                pre_check = await self.pre_delivery_check_and_close(
                    websocket=websocket,
                    order_no=order_id,
                    buyer_id=send_user_id,
                    chat_id=chat_id,
                    log_prefix=f'[{msg_time}] 【{self.cookie_id}】',
                    item_id=item_id,
                )
            pre_check_action = pre_check.get('action', 'allow')
            if pre_check_action == 'block':
                return
            # card_only 下需跳过 confirm 接口，仅发卡券
            skip_confirm_for_card_only = (pre_check_action == 'card_only')

            # 将 buyer_fish_nick 保存为局部变量，避免并发场景下
            # self._current_buyer_fish_nick 被其他协程重置导致写入数据库时为空
            local_buyer_fish_nick = pre_check.get('buyer_fish_nick') or self._current_buyer_fish_nick

            # 使用订单ID作为锁的键
            lock_key = order_id

            # 第一重检查：延迟锁状态（在获取锁之前检查，避免不必要的等待）
            if self.is_lock_held(lock_key):
                logger.info(f'[{msg_time}] 【{self.cookie_id}】🔒【提前检查】订单 {lock_key} 延迟锁仍在持有状态，跳过发货')
                return

            # 第二重检查：基于时间的冷却机制
            if not await self.can_auto_delivery(order_id):
                logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {order_id} 在冷却期内，跳过发货')
                return

            # 使用Redis分布式锁（跨进程并发控制，Redis失败时降级为仅本地锁）
            from common.db.redis_client import try_acquire_delivery_lock
            
            lock_result = None
            redis_lock_acquired = False
            try:
                lock_result = await try_acquire_delivery_lock(order_id, expire=120, holder_info=self.cookie_id, wait_timeout=5)
                if lock_result.success:
                    redis_lock_acquired = True
                    logger.info(f'[{msg_time}] 【{self.cookie_id}】获取Redis分布式锁成功: {order_id}')
                elif lock_result.is_locked_by_other:
                    # 锁被其他进程持有，直接返回，不执行发货
                    logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ Redis分布式锁被其他进程持有，跳过发货: {order_id}')
                    return
                elif lock_result.has_error:
                    # Redis连接异常，降级为本地锁控制
                    logger.warning(f'[{msg_time}] 【{self.cookie_id}】Redis连接异常，降级为本地锁控制: {order_id}')
            except Exception as e:
                logger.warning(f'[{msg_time}] 【{self.cookie_id}】Redis分布式锁异常，降级为本地锁控制: {order_id}, error={e}')
            
            try:
                # 获取锁后检查数据库订单状态，如果已发货则跳过
                if redis_lock_acquired and order_id:
                    try:
                        from common.db.compat import db_manager
                        existing_order = db_manager.get_order_by_id(order_id)
                        if existing_order and existing_order.get('status') == 'shipped':
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】获取锁后检查发现订单 {order_id} 已发货，跳过处理')
                            return
                    except Exception as e:
                        logger.warning(f'[{msg_time}] 【{self.cookie_id}】获取锁后检查订单状态异常: {self._safe_str(e)}')

                # 第三重检查：获取锁后再次检查延迟锁状态（双重检查，防止在等待锁期间状态发生变化）
                if self.is_lock_held(lock_key):
                    logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {lock_key} 在获取锁后检查发现延迟锁仍持有，跳过发货')
                    return

                # 第四重检查：获取锁后再次检查冷却状态
                if not await self.can_auto_delivery(order_id):
                    logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {order_id} 在获取锁后检查发现仍在冷却期，跳过发货')
                    return

                # 构造用户URL
                user_url = f'https://www.goofish.com/personal?userId={send_user_id}'

                # 自动发货逻辑
                try:
                    # 重置失败原因
                    self._last_delivery_fail_reason = None
                    # 设置默认标题（将通过API获取真实商品信息）
                    item_title = "待获取商品信息"

                    logger.info(f"【{self.cookie_id}】准备自动发货: item_id={item_id}, item_title={item_title}")

                    # 检查是否需要多数量发货
                    from common.db.compat import db_manager
                    quantity_to_send = 1  # 默认发送1个

                    # 检查商品是否开启了多数量发货
                    multi_quantity_delivery = db_manager.get_item_multi_quantity_delivery_status(self.cookie_id, item_id)

                    if multi_quantity_delivery and order_id:
                        logger.info(f"商品 {item_id} 开启了多数量发货，获取订单详情...")
                        try:
                            # 使用现有方法获取订单详情
                            order_detail = await self.fetch_order_detail_info(order_id, item_id, send_user_id)
                            if order_detail and order_detail.get('quantity'):
                                try:
                                    order_quantity = int(order_detail['quantity'])
                                    if order_quantity > 1:
                                        quantity_to_send = order_quantity
                                        logger.info(f"从订单详情获取数量: {order_quantity}，将发送 {quantity_to_send} 个卡券")
                                    else:
                                        logger.info(f"订单数量为 {order_quantity}，发送单个卡券")
                                except (ValueError, TypeError):
                                    logger.warning(f"订单数量格式无效: {order_detail.get('quantity')}，发送单个卡券")
                            else:
                                logger.info(f"未获取到订单数量信息，发送单个卡券")
                        except Exception as e:
                            logger.error(f"获取订单详情失败: {self._safe_str(e)}，发送单个卡券")
                    elif not multi_quantity_delivery:
                        logger.info(f"商品 {item_id} 未开启多数量发货，发送单个卡券")
                    else:
                        logger.info(f"无订单ID，发送单个卡券")

                    # card_only 多数量退化保护：订单已被关闭 + 仅补发卡券是商家"礼貌性安抚"语义，
                    # 业务上就是补 1 张固定卡券；多数量场景下 N 倍补发会让货主额外亏 N-1 张卡密成本
                    # （特别是 data/api 实际卡密会扣库存/调 API），强制退化为 1 张。
                    if quantity_to_send > 1 and skip_confirm_for_card_only:
                        logger.warning(
                            f"【{self.cookie_id}】订单 {order_id} card_only 模式仅补发 1 张固定卡券，"
                            f"已退化为 1 张（原数量 {quantity_to_send}）"
                        )
                        quantity_to_send = 1

                    # 多次调用自动发货方法，每次获取不同的内容
                    delivery_contents = []
                    success_count = 0
                    order_already_shipped = False  # 标记订单是否已发货
                    # 对接卡券退化标记：多数量循环里若第 1 张匹配到对接卡券，强制 break 退化为 1 张
                    # 规避底层 _create_agent_order + settlement_service 在 N 次调用时引发的金额 bug
                    quantity_degraded_for_dock = False
                    # 固定内容类型（text/image）退化标记：循环 N 次只是把同一段话/同一张图重复发 N 次，
                    # 业务上无意义且会打扰买家。商家若需要多数量真正发不同内容，应使用 data 或 api 类型卡券
                    quantity_degraded_for_fixed_content = False

                    # 在循环开始前清空上次的卡券来源/类型记录，避免跨订单残留
                    self._last_delivery_card_source = None
                    self._last_delivery_card_type = None

                    for i in range(quantity_to_send):
                        try:
                            # 每次调用都可能获取不同的内容（API卡券、批量数据等）
                            # skip_confirm=True：禁止发货 + 关闭订单后继续发货场景，跳过确认发货接口
                            delivery_content = await self._auto_delivery(
                                item_id, item_title, order_id, send_user_id, chat_id, send_user_name,
                                skip_confirm=skip_confirm_for_card_only,
                            )
                            if delivery_content:
                                delivery_contents.append(delivery_content)
                                success_count += 1
                                if quantity_to_send > 1:
                                    logger.info(f"第 {i+1}/{quantity_to_send} 个卡券内容获取成功")

                                # 对接卡券退化保护：第 1 张发货完成后，若卡券来源是 dock_l1/dock_l2，
                                # 立即 break 退化为 1 张，避免后续 N-1 张触发代理订单结算的金额 bug。
                                # 退化原因详见 internal API deliver_order 注释（手续费重复扣等）。
                                if quantity_to_send > 1 and self._last_delivery_card_source in ('dock_l1', 'dock_l2'):
                                    quantity_degraded_for_dock = True
                                    logger.warning(
                                        f"【{self.cookie_id}】订单 {order_id} 对接卡券暂不支持多数量发货，"
                                        f"已退化为 1 张（原数量 {quantity_to_send}，card_source={self._last_delivery_card_source}）。"
                                        f"剩余 {quantity_to_send - 1} 张请商家手动补发或改用自有卡券"
                                    )
                                    break

                                # text/image 固定内容卡券退化保护：第 1 张发货完成后，若卡券类型是
                                # text 或 image，立即 break。这两种类型每次返回相同 text_content/image_url，
                                # 循环 N 次发同样内容没有业务意义且会打扰买家。
                                if quantity_to_send > 1 and self._last_delivery_card_type in ('text', 'image'):
                                    quantity_degraded_for_fixed_content = True
                                    logger.warning(
                                        f"【{self.cookie_id}】订单 {order_id} 固定内容卡券（{self._last_delivery_card_type} 类型）"
                                        f"不支持多数量发货，已退化为 1 张（原数量 {quantity_to_send}）。"
                                        f"如需为多数量订单发送不同卡密，请改用 data（批量数据）或 api（接口拉取）类型卡券"
                                    )
                                    break
                            elif delivery_content is None and i == 0:
                                # 第一次调用返回None，可能是订单已发货，检查订单状态
                                from common.db.compat import db_manager
                                existing_order = db_manager.get_order_by_id(order_id)
                                if existing_order and existing_order.get('status') == 'shipped':
                                    logger.info(f"【{self.cookie_id}】订单 {order_id} 已发货，跳过发送卡券")
                                    order_already_shipped = True
                                    break
                                else:
                                    logger.warning(f"第 {i+1}/{quantity_to_send} 个卡券内容获取失败")
                            else:
                                logger.warning(f"第 {i+1}/{quantity_to_send} 个卡券内容获取失败")
                        except Exception as e:
                            logger.error(f"第 {i+1}/{quantity_to_send} 个卡券获取异常: {self._safe_str(e)}")

                    # 如果订单已发货，不需要发送通知
                    if order_already_shipped:
                        logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {order_id} 已发货，无需重复处理')
                    elif delivery_contents:
                        # 标记已发货（防重复）- 基于订单ID
                        await self.mark_delivery_sent(order_id)

                        # 标记锁为持有状态，并启动延迟释放任务
                        self._lock_hold_info[lock_key] = {
                            'locked': True,
                            'lock_time': time.time(),
                            'release_time': None,
                            'task': None
                        }

                        # 启动延迟释放锁的异步任务（10分钟后释放）
                        delay_task = asyncio.create_task(self._delayed_lock_release(lock_key, delay_minutes=10))
                        self._lock_hold_info[lock_key]['task'] = delay_task

                        # 发送所有获取到的发货内容，跟踪发送结果
                        any_send_failed = False
                        send_results = []  # 收集所有发送结果用于写入消息日志
                        for i, delivery_content in enumerate(delivery_contents):
                            try:
                                # 检查是否是带图片的发货内容
                                if delivery_content.startswith("__DELIVERY_WITH_IMAGES__"):
                                    # 格式: __DELIVERY_WITH_IMAGES__卡券ID|图片数量|图片URL1|图片URL2|...|文字内容
                                    data = delivery_content.replace("__DELIVERY_WITH_IMAGES__", "")
                                    parts = data.split("|")
                                    if len(parts) >= 3:
                                        try:
                                            card_id = int(parts[0])
                                        except ValueError:
                                            logger.error(f"无效的卡券ID: {parts[0]}")
                                            card_id = None
                                        
                                        try:
                                            image_count = int(parts[1])
                                        except ValueError:
                                            logger.error(f"无效的图片数量: {parts[1]}")
                                            image_count = 0
                                        
                                        # 提取图片URL和文字内容
                                        image_urls = parts[2:2+image_count] if image_count > 0 else []
                                        text_content = parts[2+image_count] if len(parts) > 2+image_count else ""
                                        
                                        # 先发送所有图片，无间隔
                                        for img_idx, image_url in enumerate(image_urls):
                                            if image_url:
                                                img_result = await self._send_image_msg_with_retry(websocket, chat_id, send_user_id, image_url, card_id=card_id, image_index=img_idx)
                                                if isinstance(img_result, dict):
                                                    send_results.append(img_result)
                                                img_ok = isinstance(img_result, dict) and img_result.get("success", False)
                                                if img_ok:
                                                    logger.info(f'[{msg_time}] 【自动发货图片】第 {img_idx+1}/{len(image_urls)} 张已向 {user_url} 发送图片')
                                                else:
                                                    any_send_failed = True
                                                    img_err = img_result.get("error_message", "未知错误") if isinstance(img_result, dict) else "返回值异常"
                                                    logger.error(f'[{msg_time}] 【自动发货图片】第 {img_idx+1}/{len(image_urls)} 张发送失败(已重试5次): {img_err}')
                                        
                                        # 再发送文字内容，支持 ###### 分隔符拆分为多条消息
                                        if text_content:
                                            text_ok = await self._send_text_with_separator(websocket, chat_id, send_user_id, text_content, msg_time, user_url, send_results=send_results)
                                            if not text_ok:
                                                any_send_failed = True
                                    else:
                                        logger.error(f"发货内容格式错误: {delivery_content[:100]}")
                                
                                # 兼容旧的多图片发送标记
                                elif delivery_content.startswith("__MULTI_IMAGE_SEND__"):
                                    # 提取卡券ID和多个图片URL
                                    image_data = delivery_content.replace("__MULTI_IMAGE_SEND__", "")
                                    parts = image_data.split("|")
                                    if len(parts) >= 2:
                                        try:
                                            card_id = int(parts[0])
                                        except ValueError:
                                            logger.error(f"无效的卡券ID: {parts[0]}")
                                            card_id = None
                                        image_urls = parts[1:]  # 剩余的都是图片URL
                                        
                                        # 逐张发送图片，无间隔
                                        for img_idx, image_url in enumerate(image_urls):
                                            if image_url:
                                                img_result = await self._send_image_msg_with_retry(websocket, chat_id, send_user_id, image_url, card_id=card_id, image_index=img_idx)
                                                if isinstance(img_result, dict):
                                                    send_results.append(img_result)
                                                img_ok = isinstance(img_result, dict) and img_result.get("success", False)
                                                if img_ok:
                                                    logger.info(f'[{msg_time}] 【自动发货多图片】第 {img_idx+1}/{len(image_urls)} 张已向 {user_url} 发送图片: {image_url}')
                                                else:
                                                    any_send_failed = True
                                                    img_err = img_result.get("error_message", "未知错误") if isinstance(img_result, dict) else "返回值异常"
                                                    logger.error(f'[{msg_time}] 【自动发货多图片】第 {img_idx+1}/{len(image_urls)} 张发送失败(已重试5次): {img_err}')
                                                # 图片之间无间隔，发送成功后直接发送下一张
                                    else:
                                        logger.error(f"多图片发送标记格式错误: {delivery_content}")
                                
                                # 兼容旧的单图片发送标记
                                elif delivery_content.startswith("__IMAGE_SEND__"):
                                    # 提取卡券ID和图片URL
                                    image_data = delivery_content.replace("__IMAGE_SEND__", "")
                                    if "|" in image_data:
                                        card_id_str, image_url = image_data.split("|", 1)
                                        try:
                                            card_id = int(card_id_str)
                                        except ValueError:
                                            logger.error(f"无效的卡券ID: {card_id_str}")
                                            card_id = None
                                    else:
                                        # 兼容旧格式（没有卡券ID）
                                        card_id = None
                                        image_url = image_data

                                    # 发送图片消息
                                    img_result = await self._send_image_msg_with_retry(websocket, chat_id, send_user_id, image_url, card_id=card_id)
                                    if isinstance(img_result, dict):
                                        send_results.append(img_result)
                                    img_ok = isinstance(img_result, dict) and img_result.get("success", False)
                                    if img_ok:
                                        if len(delivery_contents) > 1:
                                            logger.info(f'[{msg_time}] 【多数量自动发货图片】第 {i+1}/{len(delivery_contents)} 张已向 {user_url} 发送图片: {image_url}')
                                        else:
                                            logger.info(f'[{msg_time}] 【自动发货图片】已向 {user_url} 发送图片: {image_url}')
                                    else:
                                        any_send_failed = True
                                        img_err = img_result.get("error_message", "未知错误") if isinstance(img_result, dict) else "返回值异常"
                                        logger.error(f'[{msg_time}] 【自动发货图片】发送失败(已重试5次): {img_err}')

                                    # 多数量发货时，消息间隔1秒
                                    if len(delivery_contents) > 1 and i < len(delivery_contents) - 1:
                                        await asyncio.sleep(1)

                                else:
                                    # 普通文本发货内容，支持 ###### 分隔符拆分为多条消息
                                    text_ok = await self._send_text_with_separator(websocket, chat_id, send_user_id, delivery_content, msg_time, user_url, send_results=send_results)
                                    if not text_ok:
                                        any_send_failed = True

                                    # 多数量发货时，消息间隔1秒
                                    if len(delivery_contents) > 1 and i < len(delivery_contents) - 1:
                                        await asyncio.sleep(1)

                            except Exception as e:
                                any_send_failed = True
                                logger.error(f"发送第 {i+1} 条消息失败: {self._safe_str(e)}")

                        # 写入消息日志，记录真实发送结果
                        await self._record_delivery_log(
                            chat_id=chat_id,
                            item_id=item_id,
                            sender_user_id=send_user_id,
                            sender_user_name=send_user_name,
                            msg_time=msg_time,
                            order_id=order_id,
                            delivery_contents=delivery_contents,
                            send_results=send_results,
                            any_send_failed=any_send_failed,
                        )

                        # "卡券发送成功再确认发货"模式：卡券已发送，现在执行确认发货
                        send_before_confirm_fail_msg = None  # 记录确认发货失败原因，延后到 update_order_delivery_info 之后写入
                        if not skip_confirm_for_card_only and self.is_send_before_confirm_enabled() and order_id and not any_send_failed:
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】卡券发送成功，开始执行确认发货: order_id={order_id}')
                            if self.is_auto_confirm_enabled():
                                confirm_result = await self.auto_confirm(order_id, item_id)
                                if confirm_result.get('success'):
                                    logger.info(f'[{msg_time}] 【{self.cookie_id}】🎉 卡券发送后确认发货成功: order_id={order_id}')
                                else:
                                    confirm_error = confirm_result.get('error', '未知错误')
                                    send_before_confirm_fail_msg = f"⚠️ 卡券已发送成功，但确认发货失败: {confirm_error}，请手动确认发货"
                                    logger.warning(f'[{msg_time}] 【{self.cookie_id}】{send_before_confirm_fail_msg}，order_id={order_id}')
                                    await self.send_delivery_failure_notification(
                                        send_user_name, send_user_id, item_id,
                                        send_before_confirm_fail_msg,
                                        chat_id,
                                    )
                            else:
                                send_before_confirm_fail_msg = "⚠️ 卡券已发送成功，但自动确认发货已关闭，请手动确认发货"
                                logger.info(f'[{msg_time}] 【{self.cookie_id}】自动确认发货已关闭，卡券已发送但跳过确认发货: order_id={order_id}')
                        elif not skip_confirm_for_card_only and self.is_send_before_confirm_enabled() and order_id and any_send_failed:
                            send_before_confirm_fail_msg = "⚠️ 卡券发送存在失败，已跳过确认发货，请检查买家是否收到完整内容后手动确认发货"
                            logger.warning(f'[{msg_time}] 【{self.cookie_id}】卡券发送存在失败，跳过确认发货: order_id={order_id}')
                            await self.send_delivery_failure_notification(
                                send_user_name, send_user_id, item_id,
                                send_before_confirm_fail_msg,
                                chat_id,
                            )

                        # 如果有消息发送失败，额外发通知告知（不影响订单状态）
                        if any_send_failed:
                            fail_notify_msg = "部分发货消息发送失败（WebSocket连接断开），请检查买家是否收到完整内容"
                            logger.error(f'[{msg_time}] 【{self.cookie_id}】订单 {order_id} {fail_notify_msg}')
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, fail_notify_msg, chat_id)

                        # 发送成功通知（仅 IM 通知，fail_reason 写库延后到 update_order_delivery_info 之后，
                        # 否则会被 update_order_delivery_info 内部的 delivery_fail_reason=None 清空）
                        if quantity_degraded_for_dock:
                            # 对接卡券退化场景：商家必须明确知道还要手动补发剩余卡密
                            remaining = max(quantity_to_send - len(delivery_contents), 0)
                            await self.send_delivery_failure_notification(
                                send_user_name, send_user_id, item_id,
                                f"⚠️ 对接卡券暂不支持多数量发货：订单数量 {quantity_to_send} 张，"
                                f"已自动发送 {len(delivery_contents)} 张，剩余 {remaining} 张请手动补发或改用自有卡券",
                                chat_id,
                            )
                        elif quantity_degraded_for_fixed_content:
                            # text/image 固定内容卡券退化场景：商家应改用 data/api 类型卡券支持多数量
                            remaining = max(quantity_to_send - len(delivery_contents), 0)
                            await self.send_delivery_failure_notification(
                                send_user_name, send_user_id, item_id,
                                f"⚠️ 固定内容卡券（{self._last_delivery_card_type} 类型）不支持多数量发货："
                                f"订单数量 {quantity_to_send} 张，仅发送 1 张固定内容（剩余 {remaining} 张未发）。"
                                f"如需多数量发送不同卡密，请改用 data 或 api 类型卡券",
                                chat_id,
                            )
                        elif len(delivery_contents) > 1:
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, f"多数量发货成功，共发送 {len(delivery_contents)} 个卡券", chat_id)
                        else:
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, "发货成功", chat_id)
                        
                        # 更新订单状态和发货信息（不受消息发送结果影响）
                        # card_only 场景：订单已被关闭，仅记录补发卡券内容，不动 status / fail_reason
                        try:
                            from common.services.order_service import OrderService
                            from common.db.session import async_session_maker
                            async with async_session_maker() as db_session:
                                order_service = OrderService(db_session)
                                # 合并所有发货内容
                                combined_content = "\n---\n".join(delivery_contents) if len(delivery_contents) > 1 else delivery_contents[0]
                                if skip_confirm_for_card_only:
                                    # card_only：仅记录 delivery_method/content，保留 status='closed' 和 fail_reason
                                    await order_service.record_delivery_for_closed_order(
                                        order_no=order_id,
                                        delivery_method="auto",
                                        delivery_content=combined_content,
                                        buyer_fish_nick=local_buyer_fish_nick,
                                    )
                                    logger.info(
                                        f"【{self.cookie_id}】订单 {order_id} card_only 模式：已记录补发卡券内容（订单状态保持已关闭）"
                                    )
                                else:
                                    # 正常发货：记录发货方式为"自动发货"
                                    await order_service.update_order_delivery_info(
                                        order_no=order_id,
                                        status="shipped",
                                        delivery_method="auto",
                                        delivery_content=combined_content,
                                        buyer_fish_nick=local_buyer_fish_nick,
                                    )
                                    logger.info(f"【{self.cookie_id}】订单 {order_id} 状态已更新为已发货（自动发货）")

                                # 退化提示写入：必须在 update_order_delivery_info 之后，否则会被其内部
                                # delivery_fail_reason=None 清空。card_only 走 record_delivery_for_closed_order
                                # 不清空 fail_reason 但仍走相同写入路径，保持文案一致便于商家查看。
                                degraded_warn_msg = None
                                if quantity_degraded_for_dock:
                                    remaining = max(quantity_to_send - len(delivery_contents), 0)
                                    degraded_warn_msg = (
                                        f"⚠️ 对接卡券暂不支持多数量发货：订单数量 {quantity_to_send} 张，"
                                        f"已自动发送 {len(delivery_contents)} 张，剩余 {remaining} 张请手动补发或改用自有卡券"
                                    )
                                elif quantity_degraded_for_fixed_content:
                                    remaining = max(quantity_to_send - len(delivery_contents), 0)
                                    degraded_warn_msg = (
                                        f"⚠️ 固定内容卡券（{self._last_delivery_card_type} 类型）不支持多数量发货："
                                        f"订单数量 {quantity_to_send} 张，仅发送 1 张固定内容（剩余 {remaining} 张未发）。"
                                        f"如需多数量发送不同卡密，请改用 data 或 api 类型卡券"
                                    )

                                if degraded_warn_msg:
                                    try:
                                        await order_service.update_order_delivery_fail_reason(
                                            order_id, degraded_warn_msg
                                        )
                                        logger.warning(
                                            f"【{self.cookie_id}】订单 {order_id} 退化提示已写入 delivery_fail_reason: {degraded_warn_msg}"
                                        )
                                    except Exception as _warn_err:
                                        logger.warning(
                                            f"【{self.cookie_id}】订单 {order_id} 写入退化提示失败: {self._safe_str(_warn_err)}"
                                        )

                                # "卡券发送成功再确认发货"模式下确认失败/发送失败的原因写入
                                # 必须在 update_order_delivery_info 之后，否则会被其内部 delivery_fail_reason=None 清空
                                # 注意：degraded_warn_msg 和 send_before_confirm_fail_msg 不会同时出现
                                # （退化场景 quantity 被强制为 1，不会触发 any_send_failed 的多张失败逻辑）
                                if send_before_confirm_fail_msg and not degraded_warn_msg:
                                    try:
                                        await order_service.update_order_delivery_fail_reason(
                                            order_id, send_before_confirm_fail_msg
                                        )
                                        logger.warning(
                                            f"【{self.cookie_id}】订单 {order_id} 确认发货失败原因已写入: {send_before_confirm_fail_msg}"
                                        )
                                    except Exception as _sbc_err:
                                        logger.warning(
                                            f"【{self.cookie_id}】订单 {order_id} 写入确认发货失败原因失败: {self._safe_str(_sbc_err)}"
                                        )
                                elif send_before_confirm_fail_msg and degraded_warn_msg:
                                    # 两者都有时合并写入
                                    combined_reason = f"{degraded_warn_msg}；{send_before_confirm_fail_msg}"
                                    try:
                                        await order_service.update_order_delivery_fail_reason(
                                            order_id, combined_reason
                                        )
                                        logger.warning(
                                            f"【{self.cookie_id}】订单 {order_id} 合并失败原因已写入: {combined_reason}"
                                        )
                                    except Exception as _sbc_err:
                                        logger.warning(
                                            f"【{self.cookie_id}】订单 {order_id} 写入合并失败原因失败: {self._safe_str(_sbc_err)}"
                                        )
                        except Exception as e:
                            logger.error(f"【{self.cookie_id}】更新订单状态失败: {self._safe_str(e)}")
                    else:
                        fail_msg = self._last_delivery_fail_reason or "未找到匹配的发货规则或获取发货内容失败"
                        logger.warning(f'[{msg_time}] 【自动发货】{fail_msg}')
                        # card_only 模式：pre_check 已写入"禁止发货原因"且已向买家发送过拦截消息，
                        # 这里若再覆盖 fail_reason 会丢失更精确的禁止发货原因，
                        # 再次给买家发通知则造成重复打扰，故跳过这两步
                        if skip_confirm_for_card_only:
                            logger.info(
                                f'[{msg_time}] 【{self.cookie_id}】card_only 模式且卡券获取失败：'
                                f'保留 pre_check 写入的禁止发货原因，不重复通知买家。order_id={order_id}'
                            )
                        else:
                            # 更新订单发货失败原因
                            await self._update_delivery_fail_reason(order_id, fail_msg)
                            # 发送自动发货失败通知
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, fail_msg, chat_id)

                except Exception as e:
                    fail_msg = f"自动发货处理异常: {str(e)}"
                    logger.error(fail_msg)
                    # card_only 模式同上：避免覆盖禁止发货原因 + 重复通知买家
                    if skip_confirm_for_card_only:
                        logger.info(
                            f'[{msg_time}] 【{self.cookie_id}】card_only 模式发生异常：'
                            f'保留 pre_check 写入的禁止发货原因，不重复通知买家。order_id={order_id}'
                        )
                    else:
                        # 更新订单发货失败原因
                        await self._update_delivery_fail_reason(order_id, fail_msg)
                        # 发送自动发货异常通知
                        await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, fail_msg, chat_id)

                logger.info(f'[{msg_time}] 【{self.cookie_id}】自动发货处理完成: {lock_key}')
            
            finally:
                # 处理完成后主动释放Redis分布式锁
                if redis_lock_acquired and lock_result:
                    try:
                        from common.db.redis_client import release_delivery_lock
                        released = await release_delivery_lock(lock_result)
                        if released:
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】Redis分布式锁已释放: {order_id}')
                        else:
                            logger.warning(f'[{msg_time}] 【{self.cookie_id}】Redis分布式锁释放失败: {order_id}')
                    except Exception as e:
                        logger.warning(f'[{msg_time}] 【{self.cookie_id}】Redis分布式锁释放异常: {order_id}, error={e}')

        except Exception as e:
            logger.error(f"统一自动发货处理异常: {self._safe_str(e)}")


    # ==================== 确认发货 ====================

    async def auto_confirm(self, order_id, item_id=None, retry_count=0):
        """自动确认发货 - 使用重构后的确认发货服务"""
        try:
            logger.warning(f"【{self.cookie_id}】开始确认发货，订单ID: {order_id}")

            from common.db.session import async_session_maker
            from common.db.compat import db_manager
            
            # 获取 account_pk
            account_pk = await db_manager.get_account_pk_by_cookie_id(self.cookie_id)
            if not account_pk:
                logger.error(f"【{self.cookie_id}】未找到账号信息")
                return {"error": "未找到账号信息", "order_id": order_id}

            async with async_session_maker() as db_session:
                from app.services.shipping import ConfirmShippingService
                
                # 创建确认发货服务实例
                confirm_service = ConfirmShippingService(db_session, self.session, account_pk)
                
                # 调用确认方法
                result = await confirm_service.auto_confirm(order_id, item_id, retry_count)
                
                # 同步更新后的cookies
                if confirm_service.cookies_str and confirm_service.cookies_str != self.cookies_str:
                    self.cookies_str = confirm_service.cookies_str
                    self.cookies = confirm_service.cookies_dict
                    logger.warning(f"【{self.cookie_id}】已同步确认发货模块更新的cookies")

                return result

        except Exception as e:
            logger.error(f"【{self.cookie_id}】确认发货模块调用失败: {self._safe_str(e)}")
            return {"error": f"确认发货模块调用失败: {self._safe_str(e)}", "order_id": order_id}

    async def auto_freeshipping(self, order_id, item_id, buyer_id, retry_count=0):
        """自动免拼发货 - 使用重构后的免拼发货服务"""
        try:
            logger.warning(f"【{self.cookie_id}】开始免拼发货，订单ID: {order_id}")

            from common.db.session import async_session_maker
            from common.db.compat import db_manager
            
            # 获取 account_pk
            account_pk = await db_manager.get_account_pk_by_cookie_id(self.cookie_id)
            if not account_pk:
                logger.error(f"【{self.cookie_id}】未找到账号信息")
                return {"error": "未找到账号信息", "order_id": order_id}

            async with async_session_maker() as db_session:
                from app.services.shipping import FreeshippingService
                
                # 创建免拼发货服务实例
                freeshipping_service = FreeshippingService(db_session, self.session, account_pk)
                
                # 调用免拼发货方法
                result = await freeshipping_service.auto_freeshipping(order_id, item_id, buyer_id, retry_count)
                
                # 同步更新后的cookies
                if freeshipping_service.cookies_str and freeshipping_service.cookies_str != self.cookies_str:
                    self.cookies_str = freeshipping_service.cookies_str
                    self.cookies = freeshipping_service.cookies_dict
                    logger.warning(f"【{self.cookie_id}】已同步免拼发货模块更新的cookies")

                return result

        except Exception as e:
            logger.error(f"【{self.cookie_id}】免拼发货模块调用失败: {self._safe_str(e)}")
            return {"error": f"免拼发货模块调用失败: {self._safe_str(e)}", "order_id": order_id}


    # ==================== 自动发货核心逻辑 ====================

    async def _resolve_buyer_name_for_variable(
        self,
        card_description: str,
        chat_id: str,
        send_user_name: str,
    ) -> str:
        """解析备注变量 {buyer_name} 应使用的买家昵称

        仅当卡券备注中确实包含 {buyer_name} 变量时，才尝试获取买家闲鱼明文昵称
        （复用订单 buyer_fish_nick 的 mtop user.query 逻辑），避免无谓的接口请求。

        取值优先级：
          1. 预检查阶段已获取的 self._current_buyer_fish_nick（命中则直接复用）
          2. 备注含变量且上面为空时，用 chat_id 实时调用 get_buyer_fish_nick 获取明文昵称
          3. 仍取不到则回退到推送消息携带的昵称 send_user_name；
             但自动发货多由「我已付款，等待你发货」等系统提醒消息触发，此时
             send_user_name 实为系统提醒标题（reminderTitle）而非真实昵称，
             这类系统占位文案不能当作买家昵称，需过滤为空。

        Args:
            card_description: 卡券备注内容
            chat_id: 聊天会话ID（user.query 的 sessionId）
            send_user_name: 推送消息携带的买家昵称（兜底）

        Returns:
            用于替换 {buyer_name} 的昵称字符串
        """
        # 推送昵称兜底：过滤掉系统提醒标题等占位文案
        fallback = send_user_name or ''
        if self._is_system_placeholder_name(fallback):
            fallback = ''

        # 备注无 {buyer_name} 变量，无需额外获取，直接返回兜底值
        if not card_description or '{buyer_name}' not in card_description:
            return fallback

        # 优先复用预检查阶段已获取的明文昵称
        cached_nick = getattr(self, '_current_buyer_fish_nick', None)
        if cached_nick:
            return cached_nick

        # 备注需要变量但缓存为空，用 chat_id 实时获取明文昵称
        if chat_id:
            try:
                fish_nick = await get_buyer_fish_nick(
                    self.cookies_str, chat_id, self.cookie_id
                )
                if fish_nick:
                    # 回写实例属性，供后续写库等复用
                    self._current_buyer_fish_nick = fish_nick
                    return fish_nick
            except Exception as e:
                logger.warning(
                    f"【{self.cookie_id}】备注变量获取买家明文昵称失败，"
                    f"回退推送昵称: {self._safe_str(e)}"
                )

        return fallback

    # 自动发货常由系统提醒消息触发，reminderTitle 会落到这些系统占位文案上，
    # 它们不是真实买家昵称，替换 {buyer_name} 时需排除
    _SYSTEM_PLACEHOLDER_NAMES = {
        '系统',
        '等待你发货',
        '等待您发货',
        '我已付款，等待你发货',
        '我已付款，等待您发货',
        '已付款，待发货',
        '记得及时发货',
        '我已拍下，待付款',
        '买家已付款',
        '付款完成',
    }

    def _is_system_placeholder_name(self, name: str) -> bool:
        """判断昵称是否为系统提醒占位文案（非真实买家昵称）"""
        if not name:
            return True
        cleaned = name.strip().strip('[]【】')
        return cleaned in self._SYSTEM_PLACEHOLDER_NAMES

    async def _auto_delivery(self, item_id: str, item_title: str = None, order_id: str = None, send_user_id: str = None, chat_id: str = None, send_user_name: str = None, skip_confirm: bool = False):
        """自动发货功能 - 根据商品ID获取卡券，执行延时，确认发货，发送内容

        Args:
            skip_confirm: 跳过确认发货接口（auto_confirm）。用于"禁止发货 + 关闭订单后只发卡券"
                场景——订单已经被卖家主动关闭，此时不能再调用确认发货接口，但仍需要把卡券内容
                发送给买家作为"补偿"。该参数为 True 时，"发货成功再发卡券"开关会被忽略。
        """
        try:
            from common.db.compat import db_manager

            logger.info(f"开始自动发货检查: 商品ID={item_id}")

            if not item_id or item_id == "未知商品":
                self._last_delivery_fail_reason = f"商品ID无效，无法自动发货: {item_id}"
                logger.warning(f"商品ID无效，无法自动发货: {item_id}")
                return None

            # 检查商品是否为多规格商品
            is_multi_spec = db_manager.get_item_multi_spec_status(self.cookie_id, item_id)
            logger.info(f"商品 {item_id} 多规格状态: {is_multi_spec}")
            
            spec_name = None
            spec_value = None

            # 如果是多规格商品且有订单ID，获取规格信息
            if is_multi_spec and order_id:
                logger.info(f"检测到多规格商品，获取订单规格信息: {order_id}")
                try:
                    order_detail = await self.fetch_order_detail_info(order_id, item_id, send_user_id)
                    if order_detail and isinstance(order_detail, dict):
                        spec_name = order_detail.get('spec_name', '')
                        spec_value = order_detail.get('spec_value', '')
                        if spec_name and spec_value:
                            logger.info(f"获取到规格信息: {spec_name} = {spec_value}")
                        else:
                            logger.warning(f"未能获取到规格信息")
                    else:
                        logger.warning(f"获取订单详情失败")
                except Exception as e:
                    logger.error(f"获取订单规格信息失败: {self._safe_str(e)}")

            # 根据商品ID获取卡券（含来源信息：own/dock_l1/dock_l2）
            logger.info(f"根据商品ID获取卡券: {item_id}")
            cards = db_manager.get_cards_by_item_id(item_id, spec_name, spec_value)
            
            if not cards:
                self._last_delivery_fail_reason = f"商品 {item_id} 未配置卡券，无法自动发货"
                logger.warning(f"❌ 商品 {item_id} 未配置卡券，无法自动发货")
                return None
            
            # 按优先级分组：自有 → 一级对接 → 二级对接
            source_priority = ['own', 'dock_l1', 'dock_l2']
            source_groups = {}
            for c in cards:
                src = c.get('card_source', 'own')
                source_groups.setdefault(src, []).append(c)
            
            # 按优先级选取第一个有且仅有1张卡券的分组
            card = None
            for src in source_priority:
                group = source_groups.get(src, [])
                if len(group) == 1:
                    card = group[0]
                    logger.info(f"✅ 按优先级匹配到卡券: 来源={src}, 卡券={card.get('name')} ({card.get('type')})")
                    break
                elif len(group) > 1:
                    logger.warning(f"⚠️ 来源 {src} 匹配到 {len(group)} 个卡券，跳过此来源（需唯一匹配）")
                    for i, gc in enumerate(group):
                        logger.info(f"  {src} 卡券{i+1}: {gc.get('name')} ({gc.get('type')})")
            
            if not card:
                self._last_delivery_fail_reason = f"商品 {item_id} 未在任何来源中唯一匹配到卡券，跳过自动发货（共 {len(cards)} 条关联）"
                logger.warning(f"⚠️ 商品 {item_id} 未在任何来源中唯一匹配到卡券，跳过自动发货（共 {len(cards)} 条关联）")
                return None
            
            # 对接卡券发货前校验：最低售价 + 金额覆盖手续费和成本
            card_source = card.get('card_source', 'own')

            # 记录本次匹配到的卡券来源/类型，供外层多数量循环判断是否退化为单张：
            # 1) 对接卡券循环 N 次会触发底层结算逻辑的金额 bug（手续费按张重复扣等）
            # 2) text/image 类型每次返回固定内容，循环 N 次只是把同一段话/同一张图重复发 N 次，
            #    业务上无意义且会打扰买家（应该建议商家用 data/api 类型支持多数量场景）
            self._last_delivery_card_source = card_source
            self._last_delivery_card_type = card.get('type')

            # card_only 模式（禁止发货 + 主动关闭订单 + 仅发卡券）下，对接卡券会让货主双重亏损：
            #   - 闲鱼订单被关闭 → 买家拿到全额退款
            #   - 但 _create_agent_order 仍会扣货主对接账户余额并分润给上下级代理
            # 为避免这种意外财务损失，对接卡券一律不走 card_only 流程，等同于 block：
            # 订单已被关闭，但卡券不发送。
            if skip_confirm and card_source in ('dock_l1', 'dock_l2'):
                self._last_delivery_fail_reason = (
                    f"card_only 模式不适用于对接卡券（card_source={card_source}），"
                    f"为避免货主财务损失，跳过卡券发送（订单已被关闭）"
                )
                logger.warning(
                    f"⚠️ 【{self.cookie_id}】card_only 模式 + 对接卡券：跳过卡券发送，"
                    f"order_id={order_id}, card_source={card_source}"
                )
                return None

            if card_source in ('dock_l1', 'dock_l2') and order_id:
                if not await self._validate_dock_delivery(order_id, card):
                    # _validate_dock_delivery 已在内部设置 self._last_delivery_fail_reason
                    logger.warning(f"⚠️ 对接卡券发货校验未通过，跳过自动发货: 订单={order_id}, 来源={card_source}"
                                   f", 原因={self._last_delivery_fail_reason}")
                    return None
            
            # 构建与原有rule格式兼容的数据结构
            rule = {
                'card_id': card.get('id'),
                'card_name': card.get('name'),
                'card_type': card.get('type'),
                'card_text_content': card.get('text_content'),
                'card_data_content': card.get('data_content'),
                'card_image_url': card.get('image_url'),
                'card_image_urls': card.get('image_urls'),  # 多图片URL列表
                'card_api_config': card.get('api_config'),
                'card_delay_seconds': card.get('delay_seconds', 0),
                'card_description': card.get('description'),
                'is_multi_spec': card.get('is_multi_spec', False),
                'spec_name': card.get('spec_name'),
                'spec_value': card.get('spec_value'),
                'keyword': item_id,  # 使用商品ID作为关键字标识
            }

            # 匹配结果日志
            if rule.get('is_multi_spec'):
                logger.info(f"🎯 匹配多规格卡券: {rule['card_name']} ({rule['card_type']}) [{rule['spec_name']}:{rule['spec_value']}]")
            else:
                logger.info(f"✅ 匹配卡券: {rule['card_name']} ({rule['card_type']})")

            # 获取延时设置
            delay_seconds = rule.get('card_delay_seconds', 0)

            # 执行延时（不管是否确认发货，只要有延时设置就执行）
            if delay_seconds and delay_seconds > 0:
                logger.info(f"检测到发货延时设置: {delay_seconds}秒，开始延时...")
                await asyncio.sleep(delay_seconds)
                logger.info(f"延时完成")

            # 如果调用方明确指示跳过确认发货（如"禁止发货 + 关闭订单后只发卡券"场景），
            # 直接跳过 confirm 步骤，但仍要继续走下方的卡券生成与发送流程。
            if skip_confirm and order_id:
                logger.info(
                    f"【{self.cookie_id}】skip_confirm=True，跳过确认发货接口，"
                    f"直接进入卡券生成流程: order_id={order_id}"
                )

            # 如果开启了"卡券发送成功再确认发货"开关，跳过此处的确认发货，
            # 由外层 _handle_auto_delivery 在卡券发送成功后再执行确认发货。
            # 前提：自动确认发货必须开启，否则整个发货流程都不应执行。
            send_before_confirm_mode = not skip_confirm and self.is_send_before_confirm_enabled()
            if send_before_confirm_mode and order_id:
                if not self.is_auto_confirm_enabled():
                    self._last_delivery_fail_reason = f"自动确认发货已关闭，且卡券发送成功再确认发货开关已开启，无法发送卡券"
                    logger.warning(f"【{self.cookie_id}】自动确认发货已关闭，卡券发送成功再确认发货开关已开启，不发送卡券: {order_id}")
                    return None
                logger.info(
                    f"【{self.cookie_id}】send_before_confirm=True，跳过此处确认发货，"
                    f"将在卡券发送成功后再确认发货: order_id={order_id}"
                )

            # 如果有订单ID，执行确认发货（除非显式 skip_confirm 或 send_before_confirm 模式）
            if order_id and not skip_confirm and not send_before_confirm_mode:
                # 检查是否启用自动确认发货
                if not self.is_auto_confirm_enabled():
                    logger.info(f"自动确认发货已关闭，跳过订单 {order_id}")
                    # 如果开启了"发货成功再发卡券"开关，自动确认关闭意味着无法确认发货，不发送卡券
                    if self.is_confirm_before_send_enabled():
                        self._last_delivery_fail_reason = f"自动确认发货已关闭，且发货成功再发卡券开关已开启，无法发送卡券"
                        logger.warning(f"【{self.cookie_id}】自动确认发货已关闭，发货成功再发卡券开关已开启，不发送卡券: {order_id}")
                        return None
                else:
                    # 检查确认发货冷却时间
                    current_time = time.time()
                    should_confirm = True

                    if order_id in self.confirmed_orders:
                        last_confirm_time = self.confirmed_orders[order_id]
                        if current_time - last_confirm_time < self.order_confirm_cooldown:
                            logger.info(f"订单 {order_id} 已在 {self.order_confirm_cooldown} 秒内确认过，跳过重复确认")
                            should_confirm = False

                    if should_confirm:
                        logger.info(f"开始自动确认发货: 订单ID={order_id}, 商品ID={item_id}")
                        confirm_result = await self.auto_confirm(order_id, item_id)
                        if confirm_result.get('success'):
                            self.confirmed_orders[order_id] = current_time
                            
                            # 检查是否是"已发货成功"的响应
                            success_msg = confirm_result.get('message', '')
                            if 'ORDER_ALREADY_DELIVERY' in success_msg or '已发货成功' in success_msg:
                                logger.info(f"【{self.cookie_id}】订单 {order_id} 已发货过，只更新数据库状态，不再发送卡券")
                                
                                # 更新订单状态为已发货
                                try:
                                    from common.services.order_service import OrderService
                                    from common.db.session import async_session_maker
                                    async with async_session_maker() as db_session:
                                        order_service = OrderService(db_session)
                                        # 确认发货成功但不发送卡券，记录发货方式为"自动发货"，内容为空
                                        await order_service.update_order_delivery_info(
                                            order_no=order_id,
                                            status="shipped",
                                            delivery_method="auto",
                                            delivery_content="订单已确认发货（闲鱼平台已发货）",
                                            buyer_fish_nick=local_buyer_fish_nick,
                                        )
                                    logger.info(f"【{self.cookie_id}】订单 {order_id} 状态已更新为已发货")
                                except Exception as e:
                                    logger.error(f"【{self.cookie_id}】更新订单状态失败: {self._safe_str(e)}")
                                
                                # 标记已发货，防止重复处理
                                await self.mark_delivery_sent(order_id)
                                
                                # 直接返回None，不再发送卡券内容
                                self._last_delivery_fail_reason = f"订单 {order_id} 已发货过，不再发送卡券"
                                return None
                            
                            logger.info(f"🎉 自动确认发货成功！订单ID: {order_id}")
                        else:
                            confirm_error = confirm_result.get('error', '未知错误')
                            logger.warning(f"⚠️ 自动确认发货失败: {confirm_error}")
                            # 检查“发货成功再发卡券”开关，如果开启则不发送卡券
                            if self.is_confirm_before_send_enabled():
                                self._last_delivery_fail_reason = f"自动确认发货失败，发货成功再发卡券开关已开启，不发送卡券: {confirm_error}"
                                logger.warning(f"【{self.cookie_id}】发货成功再发卡券开关已开启，确认发货失败，不发送卡券: {order_id}")
                                return None

            # 检查是否存在订单ID，只有存在订单ID才处理发货内容
            if order_id:
                # 保存订单基本信息到数据库（如果还没有详细信息）
                try:
                    # 检查cookie_id是否在cookies表中存在
                    cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
                    if not cookie_info:
                        logger.warning(f"Cookie ID {self.cookie_id} 不存在于cookies表中，丢弃订单 {order_id}")
                    else:
                        existing_order = db_manager.get_order_by_id(order_id)
                        if not existing_order:
                            # 插入基本订单信息
                            success = db_manager.insert_or_update_order(
                                order_id=order_id,
                                item_id=item_id,
                                buyer_id=send_user_id,
                                cookie_id=self.cookie_id,
                                chat_id=chat_id
                            )
                            
                            # 使用订单状态处理器设置状态
                            if success and self.order_status_handler:
                                try:
                                    self.order_status_handler.handle_order_basic_info_status(
                                        order_id=order_id,
                                        cookie_id=self.cookie_id,
                                        context="自动发货-基本信息",
                                        item_id=item_id,
                                        buyer_id=send_user_id,
                                    )
                                except Exception as e:
                                    logger.error(f"【{self.cookie_id}】订单状态处理器调用失败: {self._safe_str(e)}")
                            
                            if success:
                                logger.info(f"保存基本订单信息到数据库: {order_id}")
                except Exception as db_e:
                    logger.error(f"保存基本订单信息失败: {self._safe_str(db_e)}")

                # 开始处理发货内容
                logger.info(f"开始处理发货内容，规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")

                delivery_content = None
                text_content = None  # 文字内容

                # 根据卡券类型处理发货内容
                if rule['card_type'] == 'api':
                    # API类型：调用API获取内容，传入订单和商品信息用于动态参数替换
                    text_content = await self._get_api_card_content(rule, order_id, item_id, send_user_id, spec_name, spec_value, chat_id=chat_id, send_user_name=send_user_name)
                    if text_content is None:
                        self._last_delivery_fail_reason = f"获取API卡券内容失败: 卡券ID={rule['card_id']}, 名称={rule['card_name']}"
                        logger.warning(self._last_delivery_fail_reason)
                        return None

                elif rule['card_type'] == 'yifan_api':
                    # 亦凡卡劵API类型：调用亦凡API获取内容
                    text_content = await self._get_yifan_api_card_content(rule, order_id, item_id, send_user_id, chat_id)
                    if text_content is None:
                        self._last_delivery_fail_reason = f"获取亦凡API卡券内容失败: 卡券ID={rule['card_id']}, 名称={rule['card_name']}"
                        logger.warning(self._last_delivery_fail_reason)
                        return None

                elif rule['card_type'] == 'text':
                    # 固定文字类型：直接使用文字内容
                    text_content = rule.get('card_text_content')

                elif rule['card_type'] == 'data':
                    # 批量数据类型：获取并消费第一条数据
                    text_content = db_manager.consume_batch_data(rule['card_id'])
                    if text_content is None:
                        self._last_delivery_fail_reason = f"批量卡券数据已用完或获取失败: 卡券ID={rule['card_id']}, 名称={rule['card_name']}"
                        logger.warning(self._last_delivery_fail_reason)
                        return None

                elif rule['card_type'] == 'image':
                    # 图片类型：文字内容为空，只发送图片
                    text_content = None

                # 检查是否有图片需要发送（所有卡券类型都可以配置图片）
                image_urls = rule.get('card_image_urls') or []
                single_image_url = rule.get('card_image_url')
                card_description = rule.get('card_description', '')

                # 构建订单上下文变量（用于备注中的变量替换）
                # 尝试从数据库获取真实商品标题
                real_item_title = item_title or ''
                if not real_item_title or real_item_title == '待获取商品信息':
                    try:
                        item_info = db_manager.get_item_info(self.cookie_id, item_id)
                        if item_info:
                            real_item_title = item_info.get('title') or item_info.get('item_title') or ''
                    except Exception:
                        pass
                # 尝试获取卖家昵称（优先使用账号备注）
                seller_name = ''
                try:
                    seller_info = db_manager.get_cookie_by_id(self.cookie_id)
                    if seller_info:
                        seller_name = seller_info.get('remark') or self.cookie_id or ''
                except Exception:
                    seller_name = self.cookie_id or ''
                # 买家昵称：备注中含 {buyer_name} 变量时，优先取闲鱼明文昵称
                # （与订单 buyer_fish_nick 同一套 mtop user.query 逻辑），
                # 取不到再回退到推送消息携带的昵称 send_user_name
                buyer_name = await self._resolve_buyer_name_for_variable(
                    card_description, chat_id, send_user_name
                )
                order_context = {
                    'order_id': order_id or '',
                    'item_id': item_id or '',
                    'item_title': real_item_title,
                    'buyer_name': buyer_name,
                    'buyer_id': send_user_id or '',
                    'seller_name': seller_name,
                }
                
                # 构建发货内容
                # 格式: __DELIVERY_WITH_IMAGES__卡券ID|图片数量|图片URL1|图片URL2|...|文字内容
                # 如果没有图片，则直接返回文字内容
                if image_urls:
                    # 多图片模式
                    urls_str = "|".join(image_urls)
                    # 处理文字内容和备注信息
                    if text_content:
                        text_part = process_delivery_content_with_description(text_content, card_description, order_context)
                    elif card_description:
                        # 图片类型卡券没有text_content，但有备注，直接使用备注作为文字内容
                        text_part = _replace_order_context_variables(card_description, order_context)
                    else:
                        text_part = ""
                    delivery_content = f"__DELIVERY_WITH_IMAGES__{rule['card_id']}|{len(image_urls)}|{urls_str}|{text_part}"
                    logger.info(f"准备发送多张图片({len(image_urls)}张)和文字内容 (卡券ID: {rule['card_id']})")
                elif single_image_url:
                    # 单图片模式
                    if text_content:
                        text_part = process_delivery_content_with_description(text_content, card_description, order_context)
                    elif card_description:
                        # 图片类型卡券没有text_content，但有备注，直接使用备注作为文字内容
                        text_part = _replace_order_context_variables(card_description, order_context)
                    else:
                        text_part = ""
                    delivery_content = f"__DELIVERY_WITH_IMAGES__{rule['card_id']}|1|{single_image_url}|{text_part}"
                    logger.info(f"准备发送图片和文字内容 (卡券ID: {rule['card_id']})")
                elif text_content:
                    # 没有图片，只有文字
                    delivery_content = process_delivery_content_with_description(text_content, card_description, order_context)
                elif card_description:
                    # 没有图片也没有text_content，但有备注（图片类型卡券只填了备注）
                    delivery_content = _replace_order_context_variables(card_description, order_context)
                else:
                    # 既没有图片也没有文字也没有备注
                    logger.warning(f"卡券没有配置图片和文字内容: 卡券ID={rule['card_id']}")
                    delivery_content = None

                if delivery_content:
                    # 增加发货次数统计
                    db_manager.increment_delivery_count(rule['card_id'])
                    logger.info(f"自动发货成功: 卡券ID={rule['card_id']}, 内容长度={len(delivery_content)}")
                    
                    # 如果是对接卡券，创建代理订单记录
                    card_source = card.get('card_source', 'own')
                    if card_source in ('dock_l1', 'dock_l2'):
                        try:
                            await self._create_agent_order(
                                order_id=order_id,
                                item_id=item_id,
                                card=card,
                                delivery_content=delivery_content,
                                buyer_id=send_user_id,
                            )
                        except Exception as agent_err:
                            logger.error(f"创建代理订单失败（不影响发货）: {self._safe_str(agent_err)}")
                    
                    return delivery_content
                else:
                    self._last_delivery_fail_reason = f"获取发货内容失败: 卡券ID={rule['card_id']}, 卡券名称={rule.get('card_name')}, 类型={rule.get('card_type')}"
                    logger.warning(f"获取发货内容失败: 卡券ID={rule['card_id']}")
                    return None
            else:
                # 没有订单ID，记录日志但不处理发货内容
                logger.info(f"⚠️ 未检测到订单ID，跳过发货内容处理。规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")
                return None

        except Exception as e:
            self._last_delivery_fail_reason = f"自动发货异常: {str(e)}"
            logger.error(f"自动发货失败: {self._safe_str(e)}")
            return None


    # ==================== 对接卡券发货校验 ====================

    async def _validate_dock_delivery(self, order_id: str, card: dict) -> bool:
        """
        校验对接卡券是否允许发货
        
        校验规则：
        1. 订单售价 >= 卡券最低售价（min_price）
        2. 订单售价 >= 手续费 + 各级代理成本
        3. 代理余额是否足够支付卡券成本（+手续费，若由分销商承担）
        
        Args:
            order_id: 订单号
            card: 卡券字典（含 card_source, dock_record_id, id 等）
            
        Returns:
            True=允许发货, False=不允许
        """
        from common.db.session import async_session_maker
        from common.models.dock_record import DockRecord
        from common.models.card import Card as CardModel
        from common.models.system_setting import SystemSetting
        from common.services.settlement_service import SettlementService
        from decimal import Decimal, InvalidOperation
        from sqlalchemy import select
        
        card_source = card.get('card_source', 'own')
        dock_record_id = card.get('dock_record_id')
        
        # 自有卡券不需要校验
        if card_source == 'own' or not dock_record_id:
            return True
        
        try:
            async with async_session_maker() as session:
                # 获取订单售价
                sale_price_str = '0.00'
                try:
                    from common.db.compat import db_manager
                    order_info = db_manager.get_order_by_id(order_id)
                    if order_info and order_info.get('amount'):
                        sale_price_str = str(order_info['amount'])
                except Exception as e:
                    logger.warning(f"校验-获取订单售价失败: {self._safe_str(e)}")
                
                sale_price = Decimal(sale_price_str)
                logger.info(f"📋 校验-订单售价: order_id={order_id}, sale_price_str='{sale_price_str}', sale_price={sale_price}")
                
                # 获取卡券信息
                card_stmt = select(CardModel).where(CardModel.id == card.get('id'))
                card_result = await session.execute(card_stmt)
                card_obj = card_result.scalars().first()
                
                if not card_obj:
                    self._last_delivery_fail_reason = f"对接卡券校验失败-未找到卡券 {card.get('id')}"
                    logger.warning(f"校验-未找到卡券 {card.get('id')}，跳过发货")
                    return False
                
                card_price = Decimal(card_obj.price or '0')  # 货主对接价（卡券成本）
                min_price = Decimal(card_obj.min_price or '0') if card_obj.min_price else Decimal('0')
                fee_payer = card_obj.fee_payer  # dealer/distributor
                
                # 获取系统手续费类型和数值
                fee_type = 'fixed'
                try:
                    fee_type_stmt = select(SystemSetting.value).where(SystemSetting.key == 'distribution.fee_type')
                    fee_type_result = await session.execute(fee_type_stmt)
                    fee_type = fee_type_result.scalar() or 'fixed'
                except Exception:
                    pass
                
                fee_stmt = select(SystemSetting.value).where(SystemSetting.key == 'distribution.fee_rate')
                fee_result = await session.execute(fee_stmt)
                fee_val = fee_result.scalar()
                fee_rate = Decimal(fee_val or '0')
                
                # 根据类型计算实际手续费金额
                if fee_type == 'percent':
                    # 百分比：fee_rate 是百分比值（如 5 表示 5%）
                    fee_amount = (sale_price * fee_rate / Decimal('100')).quantize(Decimal('0.01'))
                else:
                    # 固定金额
                    fee_amount = fee_rate
                
                # 获取对接记录
                dock_stmt = select(DockRecord).where(DockRecord.id == dock_record_id)
                dock_result = await session.execute(dock_stmt)
                dock_record = dock_result.scalars().first()
                
                if not dock_record:
                    self._last_delivery_fail_reason = f"对接卡券校验失败-未找到对接记录 {dock_record_id}"
                    logger.warning(f"校验-未找到对接记录 {dock_record_id}，跳过发货")
                    return False
                
                dock_level = dock_record.level
                
                # 获取当前用户ID（分销商/代理）
                from common.db.compat import db_manager
                cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
                dealer_user_id = cookie_info.get('user_id') if cookie_info else 0
                
                logger.info(
                    f"📋 对接发货校验参数: 订单={order_id}, 售价={sale_price}, "
                    f"卡券成本={card_price}, 最低售价={min_price}, "
                    f"手续费类型={fee_type}, 手续费={fee_amount}, "
                    f"手续费承担方={fee_payer}, 层级={dock_level}, "
                    f"代理用户={dealer_user_id}"
                )
                
                # 校验1：最低售价
                if min_price > 0 and sale_price < min_price:
                    self._last_delivery_fail_reason = f"对接卡券校验失败-售价低于最低售价: 售价={sale_price}, 最低售价={min_price}"
                    logger.warning(
                        f"❌ 对接卡券发货校验失败-售价低于最低售价: "
                        f"订单={order_id}, 售价={sale_price}, 最低售价={min_price}"
                    )
                    return False
                
                # 校验2：根据层级检查金额是否覆盖手续费和成本
                if dock_level == 1:
                    # 一级代理：售价 >= 手续费 + 卡券成本
                    required = fee_amount + card_price
                    if sale_price < required:
                        self._last_delivery_fail_reason = f"对接卡券校验失败-一级代理售价不足: 售价={sale_price}, 所需={required}（手续费{fee_amount} + 卡券成本{card_price}）"
                        logger.warning(
                            f"❌ 对接卡券发货校验失败-一级代理售价不足: "
                            f"订单={order_id}, 售价={sale_price}, "
                            f"所需={required}（手续费{fee_amount} + 卡券成本{card_price}）"
                        )
                        return False
                    
                    # 校验3：一级代理余额校验
                    settlement = SettlementService(session)
                    dealer_balance = await settlement.check_balance(dealer_user_id)
                    if fee_payer == 'dealer':
                        # 分销商付手续费：余额需 >= 卡券成本 + 手续费
                        required_balance = card_price + fee_amount
                    else:
                        # 货主付手续费：余额需 >= 卡券成本
                        required_balance = card_price
                    
                    logger.info(
                        f"📋 一级余额校验: 代理用户={dealer_user_id}, "
                        f"余额={dealer_balance}(type={type(dealer_balance).__name__}), "
                        f"所需={required_balance}(type={type(required_balance).__name__}), "
                        f"fee_payer={fee_payer}, 结果={'通过' if dealer_balance >= required_balance else '不通过'}"
                    )
                    
                    if dealer_balance < required_balance:
                        self._last_delivery_fail_reason = f"对接卡券校验失败-一级代理余额不足: 代理用户={dealer_user_id}, 当前余额={dealer_balance}, 所需余额={required_balance}"
                        logger.warning(
                            f"❌ 对接卡券发货校验失败-一级代理余额不足: "
                            f"订单={order_id}, 代理用户={dealer_user_id}, "
                            f"当前余额={dealer_balance}, 所需余额={required_balance}"
                        )
                        return False
                        
                elif dock_level == 2:
                    # 二级代理：获取一级的 sub_dock_price 作为二级拿货价
                    level2_cost = card_price  # 默认回退到卡券成本
                    if dock_record.parent_dock_id:
                        parent_stmt = select(DockRecord.sub_dock_price).where(
                            DockRecord.id == dock_record.parent_dock_id
                        )
                        parent_result = await session.execute(parent_stmt)
                        sub_dock_price = parent_result.scalar()
                        if sub_dock_price:
                            level2_cost = Decimal(sub_dock_price)
                    
                    # 售价 >= 手续费 + 二级拿货价
                    required = fee_amount + level2_cost
                    if sale_price < required:
                        self._last_delivery_fail_reason = f"对接卡券校验失败-二级代理售价不足: 售价={sale_price}, 所需={required}（手续费{fee_amount} + 二级拿货价{level2_cost}）"
                        logger.warning(
                            f"❌ 对接卡券发货校验失败-二级代理售价不足: "
                            f"订单={order_id}, 售价={sale_price}, "
                            f"所需={required}（手续费{fee_amount} + 二级拿货价{level2_cost}）"
                        )
                        return False
                    
                    # 二级拿货价 >= 卡券成本（一级也要有利润空间）
                    if level2_cost < card_price:
                        self._last_delivery_fail_reason = f"对接卡券校验失败-二级拿货价低于卡券成本: 二级拿货价={level2_cost}, 卡券成本={card_price}"
                        logger.warning(
                            f"❌ 对接卡券发货校验失败-二级拿货价低于卡券成本: "
                            f"订单={order_id}, 二级拿货价={level2_cost}, 卡券成本={card_price}"
                        )
                        return False
                    
                    # 校验3：二级代理余额校验
                    settlement = SettlementService(session)
                    dealer_balance = await settlement.check_balance(dealer_user_id)
                    if fee_payer == 'dealer':
                        # 分销商付手续费：余额需 >= 对接成本 + 手续费
                        required_balance = level2_cost + fee_amount
                    else:
                        # 货主付手续费：余额需 >= 对接成本
                        required_balance = level2_cost
                    
                    if dealer_balance < required_balance:
                        self._last_delivery_fail_reason = f"对接卡券校验失败-二级代理余额不足: 代理用户={dealer_user_id}, 当前余额={dealer_balance}, 所需余额={required_balance}"
                        logger.warning(
                            f"❌ 对接卡券发货校验失败-二级代理余额不足: "
                            f"订单={order_id}, 代理用户={dealer_user_id}, "
                            f"当前余额={dealer_balance}, 所需余额={required_balance}"
                        )
                        return False
                
                logger.info(
                    f"✅ 对接卡券发货校验通过: 订单={order_id}, 售价={sale_price}, "
                    f"手续费={fee_amount}, 层级={dock_level}"
                )
                return True
                
        except (InvalidOperation, ValueError) as e:
            self._last_delivery_fail_reason = f"对接卡券校验失败-金额解析异常: {str(e)}"
            logger.error(f"校验-金额解析异常: {self._safe_str(e)}")
            return False
        except Exception as e:
            self._last_delivery_fail_reason = f"对接卡券校验异常: {str(e)}"
            logger.error(f"校验-异常: {self._safe_str(e)}")
            return False

    # ==================== 代理订单 ====================

    async def _create_agent_order(self, order_id: str, item_id: str, card: dict, delivery_content: str, buyer_id: str = None):
        """
        创建代理订单记录并执行分润结算（对接卡券发货后调用）
        
        结算流程（按新规则）：
        - 一级代理（货主付费）：一级扣卡券成本 → 货主加卡券成本 → 货主扣手续费
        - 一级代理（分销商付费）：一级扣卡券成本 → 一级扣手续费 → 货主加卡券成本
        - 二级代理（货主付费）：二级扣对接成本 → 一级加对接成本 → 一级扣卡券成本 → 货主加卡券成本 → 货主扣手续费
        - 二级代理（分销商付费）：二级扣对接成本 → 二级扣手续费 → 一级加对接成本 → 一级扣卡券成本 → 货主加卡券成本
        
        Args:
            order_id: 闲鱼订单号
            item_id: 商品ID
            card: 卡券字典（含 card_source, dock_record_id 等）
            delivery_content: 发货内容
            buyer_id: 买家ID
        """
        from common.db.session import async_session_maker
        from common.models.agent_order import AgentOrder
        from common.models.dock_record import DockRecord
        from common.models.card import Card as CardModel
        from common.models.system_setting import SystemSetting
        from common.services.settlement_service import SettlementService
        from decimal import Decimal, InvalidOperation
        from sqlalchemy import select
        
        card_source = card.get('card_source', 'own')
        dock_record_id = card.get('dock_record_id')
        
        if not dock_record_id:
            logger.warning(f"对接卡券缺少 dock_record_id，跳过代理订单创建")
            return
        
        async with async_session_maker() as session:
            # 获取对接记录详情
            stmt = select(DockRecord).where(DockRecord.id == dock_record_id)
            result = await session.execute(stmt)
            dock_record = result.scalars().first()
            
            if not dock_record:
                logger.warning(f"未找到对接记录 {dock_record_id}，跳过代理订单创建")
                return
            
            dock_level = dock_record.level  # 1 or 2
            
            # 获取卡券信息（成本价、手续费支付方）
            card_stmt = select(CardModel).where(CardModel.id == card.get('id'))
            card_result = await session.execute(card_stmt)
            card_obj = card_result.scalars().first()
            
            card_price = card_obj.price or '0.00' if card_obj else '0.00'  # 货主的对接价（卡券成本）
            fee_payer = card_obj.fee_payer if card_obj else None  # dealer/distributor
            owner_user_id = card_obj.user_id if card_obj else None  # 货主用户ID
            
            # 获取订单售价（需要先获取，百分比手续费依赖售价）
            sale_price = '0.00'
            try:
                from common.db.compat import db_manager
                order_info = db_manager.get_order_by_id(order_id)
                if order_info and order_info.get('amount'):
                    sale_price = str(order_info['amount'])
            except Exception as e:
                logger.warning(f"获取订单售价失败: {self._safe_str(e)}")
            
            # 获取系统手续费类型和数值
            fee_amount = '0'
            try:
                fee_type = 'fixed'
                fee_type_stmt = select(SystemSetting.value).where(SystemSetting.key == 'distribution.fee_type')
                fee_type_result = await session.execute(fee_type_stmt)
                fee_type = fee_type_result.scalar() or 'fixed'
                
                fee_stmt = select(SystemSetting.value).where(SystemSetting.key == 'distribution.fee_rate')
                fee_result = await session.execute(fee_stmt)
                fee_val = fee_result.scalar()
                fee_rate = Decimal(fee_val or '0')
                
                if fee_type == 'percent':
                    # 百分比：fee_rate 是百分比值（如 5 表示 5%）
                    fee_amount = str((Decimal(sale_price) * fee_rate / Decimal('100')).quantize(Decimal('0.01')))
                else:
                    # 固定金额
                    fee_amount = str(fee_rate)
            except Exception as e:
                logger.warning(f"获取手续费配置失败: {self._safe_str(e)}")
            
            # 确定上级信息和对接价格
            upstream_user_id = None
            upstream_dock_record_id = None
            level1_user_id = None  # 一级分销商（二级结算用）
            level2_cost = '0.00'   # 二级拿货价（二级结算用）
            dock_price = '0.00'    # 代理的实际拿货价（对接价格）
            
            if dock_level == 1:
                # 一级对接：拿货价=卡券成本，上级是卡券拥有者
                dock_price = card_price
                upstream_user_id = owner_user_id
            elif dock_level == 2:
                # 二级对接：上级是一级分销商
                upstream_user_id = dock_record.source_user_id
                upstream_dock_record_id = dock_record.parent_dock_id
                level1_user_id = dock_record.source_user_id
                
                # 获取一级的 sub_dock_price 作为二级拿货价
                if dock_record.parent_dock_id:
                    parent_stmt = select(DockRecord.sub_dock_price).where(
                        DockRecord.id == dock_record.parent_dock_id
                    )
                    parent_result = await session.execute(parent_stmt)
                    sub_dock_price = parent_result.scalar()
                    level2_cost = sub_dock_price or card_price  # 回退到卡券成本
                
                # 二级拿货价即为对接价格
                dock_price = level2_cost
            
            # 计算利润（售价 - 拿货价）
            try:
                profit = str(Decimal(sale_price) - Decimal(dock_price))
            except (InvalidOperation, ValueError):
                profit = '0.00'
            
            # 获取当前用户ID（分销商）
            from common.db.compat import db_manager
            cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
            user_id = cookie_info.get('user_id') if cookie_info else 0
            
            # 截断发货内容（避免过长）
            truncated_content = delivery_content[:2000] if delivery_content else None
            
            # 创建代理订单记录（完整存储所有对接金额）
            agent_order = AgentOrder(
                user_id=user_id,
                order_no=order_id,
                item_id=item_id,
                card_id=card.get('id', 0),
                dock_record_id=dock_record_id,
                dock_level=dock_level,
                sale_price=sale_price,
                dock_price=dock_price,
                card_price=card_price,
                level2_cost=level2_cost if dock_level == 2 else None,
                profit=profit,
                fee_amount=fee_amount,
                fee_payer=fee_payer,
                upstream_user_id=upstream_user_id,
                upstream_dock_record_id=upstream_dock_record_id,
                owner_user_id=owner_user_id,
                delivery_content=truncated_content,
                buyer_id=buyer_id,
                status='delivered',
            )
            session.add(agent_order)
            await session.flush()  # flush 先获取 ID，但不 commit
            
            logger.info(
                f"✅ 代理订单已创建: order_no={order_id}, dock_level={dock_level}, "
                f"sale={sale_price}, dock={dock_price}, card_price={card_price}, "
                f"level2_cost={level2_cost}, fee={fee_amount}({fee_payer}), "
                f"profit={profit}, upstream_user={upstream_user_id}, owner={owner_user_id}"
            )
            
            # 执行分润结算（在同一个 session/事务中）
            settlement = SettlementService(session)
            
            try:
                if dock_level == 1 and owner_user_id:
                    # 一级结算
                    await settlement.settle_level1_order(
                        order_no=order_id,
                        dealer_user_id=user_id,
                        owner_user_id=owner_user_id,
                        dock_record_id=dock_record_id,
                        agent_order_id=agent_order.id,
                        sale_price=sale_price,
                        card_price=card_price,
                        fee_payer=fee_payer,
                        fee_amount=fee_amount,
                    )
                    agent_order.status = 'settled'
                    
                elif dock_level == 2 and level1_user_id and owner_user_id:
                    # 二级结算
                    await settlement.settle_level2_order(
                        order_no=order_id,
                        dealer_user_id=user_id,
                        level1_user_id=level1_user_id,
                        owner_user_id=owner_user_id,
                        dock_record_id=dock_record_id,
                        parent_dock_record_id=upstream_dock_record_id or 0,
                        agent_order_id=agent_order.id,
                        sale_price=sale_price,
                        level2_cost=level2_cost,
                        level1_cost=card_price,
                        fee_payer=fee_payer,
                        fee_amount=fee_amount,
                    )
                    agent_order.status = 'settled'
                    
            except Exception as settle_err:
                logger.error(f"分润结算失败（不影响代理订单记录）: {self._safe_str(settle_err)}")
                agent_order.settle_remark = f'结算失败: {self._safe_str(settle_err)}'
            
            await session.commit()

    # ==================== API卡券获取 ====================

    async def _get_api_card_content(self, rule, order_id=None, item_id=None, buyer_id=None, spec_name=None, spec_value=None, retry_count=0, chat_id=None, send_user_name=None):
        """调用API获取卡券内容，支持动态参数替换和重试机制"""
        max_retries = 4

        if retry_count >= max_retries:
            logger.error(f"API调用失败，已达到最大重试次数({max_retries})")
            return None

        try:
            # 兼容两种字段名: api_config 和 card_api_config
            api_config = rule.get('api_config') or rule.get('card_api_config')
            if not api_config:
                logger.error(f"API配置为空，规则ID: {rule.get('id')}, 卡券名称: {rule.get('card_name')}")
                logger.warning(f"规则详情: {rule}")
                return None

            # 解析API配置
            if isinstance(api_config, str):
                api_config = json.loads(api_config)

            url = api_config.get('url')
            method = api_config.get('method', 'GET').upper()
            timeout = api_config.get('timeout', 10)
            headers = api_config.get('headers', '{}')
            params = api_config.get('params', '{}')

            # 解析headers和params
            if isinstance(headers, str):
                headers = json.loads(headers)
            if isinstance(params, str):
                params = json.loads(params)

            # 如果是POST请求且没有指定Content-Type，则默认设为application/json
            if method == 'POST' and isinstance(headers, dict):
                has_content_type = any(k.lower() == 'content-type' for k in headers.keys())
                if not has_content_type:
                    headers['Content-Type'] = 'application/json'

            # 如果是POST请求且有动态参数，进行参数替换
            if method == 'POST' and params:
                params = await self._replace_api_dynamic_params(params, order_id, item_id, buyer_id, spec_name, spec_value, chat_id=chat_id, send_user_name=send_user_name)

            retry_info = f" (重试 {retry_count + 1}/{max_retries})" if retry_count > 0 else ""
            logger.info(f"调用API获取卡券: {method} {url}{retry_info}")
            if method == 'POST' and params:
                logger.warning(f"POST请求参数: {json.dumps(params, ensure_ascii=False)}")

            # 发起HTTP请求
            timeout_obj = aiohttp.ClientTimeout(total=timeout)

            # 使用临时的纯净 ClientSession，避免共用闲鱼 session 导致敏感 Cookie 泄露或 Headers 冲突（如 Content-Type 冲突返回 415）
            async with aiohttp.ClientSession() as http_session:
                if method == 'GET':
                    async with http_session.get(url, headers=headers, params=params, timeout=timeout_obj) as response:
                        status_code = response.status
                        response_text = await response.text()
                elif method == 'POST':
                    async with http_session.post(url, headers=headers, json=params, timeout=timeout_obj) as response:
                        status_code = response.status
                        response_text = await response.text()
                else:
                    logger.error(f"不支持的HTTP方法: {method}")
                    return None

            if status_code == 200:
                # 尝试解析JSON响应，如果失败则使用原始文本
                try:
                    result = json.loads(response_text)
                    # 如果返回的是对象，尝试提取常见的内容字段
                    if isinstance(result, dict):
                        content = result.get('data') or result.get('content') or result.get('card') or str(result)
                    else:
                        content = str(result)
                except Exception:
                    content = response_text

                logger.info(f"API调用成功，返回内容长度: {len(content)}")
                return content
            else:
                logger.warning(f"API调用失败: {status_code} - {response_text[:200]}...")

                # 如果是服务器错误(5xx)或请求超时，进行重试
                if status_code >= 500 or status_code == 408:
                    if retry_count < max_retries - 1:
                        wait_time = (retry_count + 1) * 2  # 递增等待时间: 2s, 4s, 6s
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                        return await self._get_api_card_content(rule, order_id, item_id, buyer_id, spec_name, spec_value, retry_count + 1, chat_id=chat_id, send_user_name=send_user_name)

                return None

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            logger.warning(f"API调用网络异常: {self._safe_str(e)}")

            # 网络异常也进行重试
            if retry_count < max_retries - 1:
                wait_time = (retry_count + 1) * 2  # 递增等待时间
                logger.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
                return await self._get_api_card_content(rule, order_id, item_id, buyer_id, spec_name, spec_value, retry_count + 1, chat_id=chat_id, send_user_name=send_user_name)
            else:
                logger.error(f"API调用网络异常，已达到最大重试次数: {self._safe_str(e)}")
                return None

        except Exception as e:
            logger.error(f"API调用异常: {self._safe_str(e)}")
            return None


    # ==================== 亦凡API卡券获取（委托给YifanApiHandler） ====================

    async def _get_yifan_api_card_content(self, rule, order_id=None, item_id=None, buyer_id=None, chat_id=None):
        """调用亦凡卡劵API获取内容 - 委托给YifanApiHandler处理"""
        return await self._yifan_api_handler.get_yifan_api_card_content(rule, order_id, item_id, buyer_id, chat_id)

    async def _call_yifan_api_with_account(self, rule, account, order_id=None, item_id=None, buyer_id=None, chat_id=None):
        """使用确认的账号调用亦凡API - 委托给YifanApiHandler处理"""
        return await self._yifan_api_handler.call_yifan_api_with_account(rule, account, order_id, item_id, buyer_id, chat_id)

    async def _ask_for_recharge_account(self, chat_id, buyer_id, rule, order_id=None, item_id=None):
        """询问客户充值账号并设置等待状态 - 委托给YifanApiHandler处理"""
        return await self._yifan_api_handler.ask_for_recharge_account(chat_id, buyer_id, rule, order_id, item_id)

    # ==================== API参数替换 ====================

    async def _replace_api_dynamic_params(self, params, order_id=None, item_id=None, buyer_id=None, spec_name=None, spec_value=None, chat_id=None, send_user_name=None):
        """替换API请求参数中的动态参数"""
        try:
            if not params or not isinstance(params, dict):
                return params

            # 获取订单和商品信息
            order_info = None
            item_info = None

            # 如果有订单ID，获取订单信息
            if order_id:
                try:
                    from common.db.compat import db_manager
                    # 尝试从数据库获取订单信息
                    order_info = db_manager.get_order_by_id(order_id)
                    if not order_info:
                        # 如果数据库中没有，尝试通过API获取
                        order_detail = await self.fetch_order_detail_info(order_id, item_id, buyer_id)
                        if order_detail:
                            order_info = order_detail
                            logger.warning(f"通过API获取到订单信息: {order_id}")
                        else:
                            logger.warning(f"无法获取订单信息: {order_id}")
                    else:
                        logger.warning(f"从数据库获取到订单信息: {order_id}")
                except Exception as e:
                    logger.warning(f"获取订单信息失败: {self._safe_str(e)}")

            # 如果有商品ID，获取商品信息
            if item_id:
                try:
                    from common.db.compat import db_manager
                    item_info = db_manager.get_item_info(self.cookie_id, item_id)
                    if item_info:
                        logger.warning(f"从数据库获取到商品信息: {item_id}")
                    else:
                        logger.warning(f"无法获取商品信息: {item_id}")
                except Exception as e:
                    logger.warning(f"获取商品信息失败: {self._safe_str(e)}")

            # 构建参数映射
            param_mapping = {
                'order_id': order_id or '',
                'item_id': item_id or '',
                'buyer_id': buyer_id or '',
                'cookie_id': self.cookie_id or '',
                'spec_name': spec_name or '',
                'spec_value': spec_value or '',
                'timestamp': str(int(time.time())),
            }

            # 买家明文昵称：仅当参数中含 {buyer_name} 时才解析（避免无谓的接口请求）
            # 复用备注变量同一套逻辑：优先已获取的明文昵称，再用 chat_id 实时查询，
            # 最后过滤系统提醒占位文案后回退到推送昵称
            params_text = json.dumps(params, ensure_ascii=False)
            if '{buyer_name}' in params_text:
                param_mapping['buyer_name'] = await self._resolve_buyer_name_for_variable(
                    params_text, chat_id, send_user_name
                )

            # 从订单信息中提取参数
            if order_info:
                param_mapping.update({
                    'order_amount': str(order_info.get('amount', '')),
                    'order_quantity': str(order_info.get('quantity', '')),
                })

            # 从商品信息中提取参数
            if item_info:
                # 处理商品详情，如果是JSON字符串则提取detail字段
                item_detail = item_info.get('item_detail', '')
                if item_detail:
                    try:
                        # 尝试解析JSON
                        detail_data = json.loads(item_detail)
                        if isinstance(detail_data, dict) and 'detail' in detail_data:
                            item_detail = detail_data['detail']
                    except (json.JSONDecodeError, TypeError):
                        # 如果不是JSON或解析失败，使用原始字符串
                        pass

                param_mapping.update({
                    'item_detail': item_detail,
                })

            # 递归替换参数
            replaced_params = recursive_replace_params(params, param_mapping)

            # 记录替换的参数
            replaced_keys = []
            for key, value in replaced_params.items():
                if isinstance(value, str) and '{' in str(params.get(key, '')):
                    replaced_keys.append(key)

            if replaced_keys:
                logger.info(f"API动态参数替换完成，替换的参数: {replaced_keys}")
                logger.warning(f"参数映射: {param_mapping}")

            return replaced_params

        except Exception as e:
            logger.error(f"替换API动态参数失败: {self._safe_str(e)}")
            return params

    # ==================== 买家信用/评价检查 ====================

    async def check_buyer_rate_count(self, buyer_id: str, retry_count: int = 0) -> int:
        """检查买家的信用/评价数（来自卖家维度的评价记录数）

        调用闲鱼接口 mtop.idle.web.trade.rate.list 获取买家被评价的总数。
        参照 `_fetch_order_detail_from_api` 实现：
        - 第一次拿到的 set-cookie 通过 `_handle_response_cookies` 写回，重试时使用更新后的 cookie 重新签名
        - 接口调用失败/网络异常时最多重试 3 次

        Args:
            buyer_id: 买家用户ID（不带 @goofish 后缀）
            retry_count: 当前重试次数（递归内部使用）

        Returns:
            买家评价总数 totalCount。
            - 成功调用且解析到 totalCount，返回该数字（>=0）
            - 调用失败/异常导致无法判断，返回 -1（调用方按"无法确认"处理，不应据此拒绝发货）
        """
        max_retry = 3

        if not buyer_id:
            logger.warning(f"【{self.cookie_id}】买家评价检查：buyer_id 为空，跳过")
            return -1

        if not self.cookies_str:
            logger.warning(f"【{self.cookie_id}】买家评价检查：未提供Cookie，跳过")
            return -1

        try:
            from common.utils.xianyu_utils import trans_cookies, generate_sign

            cookies = trans_cookies(self.cookies_str)
            timestamp = str(int(time.time() * 1000))
            data_payload = {
                "rateType": 0,
                "ratedUid": str(buyer_id),
                "raterType": 0,
                "rowsPerPage": 20,
                "pageNumber": 1,
                "foldFlag": 0,
                "fishAdCode": "330110",
                "extraTag": "",
            }
            data_val = json.dumps(data_payload, separators=(',', ':'), ensure_ascii=False)

            token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
            if not token:
                logger.warning(f"【{self.cookie_id}】买家评价检查：Cookie中未找到 _m_h5_tk")

            sign = generate_sign(timestamp, token, data_val)

            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': sign,
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.idle.web.trade.rate.list',
                'sessionOption': 'AutoLoginOnly',
                'spm_cnt': 'a21ybx.personal.0.0',
            }

            headers = {
                'accept': 'application/json',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded',
                'pragma': 'no-cache',
                'origin': 'https://www.goofish.com',
                'referer': 'https://www.goofish.com/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
                'cookie': self.cookies_str.replace('\n', '').replace('\r', '') if self.cookies_str else '',
            }

            api_url = 'https://h5api.m.goofish.com/h5/mtop.idle.web.trade.rate.list/1.0/'

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    params=params,
                    data={'data': data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    res_json = await response.json()

                    # 处理响应中的set-cookie，更新本地cookie（令牌过期时服务端会返回新cookie）
                    self._handle_response_cookies(response)

                    ret_list = res_json.get('ret', []) or []
                    logger.info(
                        f"【{self.cookie_id}】买家评价检查：buyer_id={buyer_id}，第{retry_count + 1}次响应 ret={ret_list}"
                    )

                    if not any('SUCCESS' in ret for ret in ret_list):
                        # 调用失败：使用更新后的 cookie 重试一次
                        if retry_count < max_retry - 1:
                            logger.info(
                                f"【{self.cookie_id}】买家评价检查失败，准备重试({retry_count + 1}/{max_retry - 1})..."
                            )
                            await asyncio.sleep(0.5)
                            return await self.check_buyer_rate_count(buyer_id, retry_count + 1)
                        logger.warning(
                            f"【{self.cookie_id}】买家评价检查多次失败：buyer_id={buyer_id}, ret={ret_list}"
                        )
                        return -1

                    data = res_json.get('data') or {}
                    total_count = data.get('totalCount')
                    if total_count is None:
                        logger.warning(
                            f"【{self.cookie_id}】买家评价响应缺少 totalCount 字段：data keys={list(data.keys())}"
                        )
                        return -1

                    try:
                        total_count_int = int(total_count)
                    except (TypeError, ValueError):
                        logger.warning(
                            f"【{self.cookie_id}】买家评价 totalCount 非数字：{total_count}"
                        )
                        return -1

                    logger.info(
                        f"【{self.cookie_id}】买家评价检查通过：buyer_id={buyer_id}, totalCount={total_count_int}"
                    )
                    return total_count_int

        except asyncio.TimeoutError:
            logger.warning(
                f"【{self.cookie_id}】买家评价检查超时（第{retry_count + 1}次）"
            )
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self.check_buyer_rate_count(buyer_id, retry_count + 1)
            return -1
        except Exception as e:
            logger.error(
                f"【{self.cookie_id}】买家评价检查异常（第{retry_count + 1}次）: {self._safe_str(e)}"
            )
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self.check_buyer_rate_count(buyer_id, retry_count + 1)
            return -1

    # ==================== 禁止发货统一拦截入口 ====================

    async def pre_delivery_check_and_close(
        self,
        websocket,
        order_no: str,
        buyer_id: str,
        chat_id: str | None = None,
        log_prefix: str = '',
        item_id: str | None = None,
    ) -> dict:
        """禁止发货预检查 + 主动关闭订单（统一收口入口）

        所有发货入口（手动发货 / 定时补发货 / 消息触发自动发货 / 卡片更新 / 小刀
        卡片 / 重发货关键字）调用此方法即可获得一致的拦截行为。

        流程（规则引擎化）：
          1. 从 xy_delivery_block_rules 表加载该账号所有已启用规则（按 priority 排序）
          2. 无已启用规则 → 直接放行 action='allow'
          3. 逐条执行规则检查：
             - 每条规则先检查自己的排除商品列表，命中则跳过本规则
             - 规则检查通过 → 继续下一条
             - 规则命中 → 执行拦截动作（发消息/写fail_reason/关单）
          4. 首条命中即停，用该规则自己的配置决定后续动作
          5. 全部通过 → 放行 action='allow'

        Args:
            websocket: 用于向买家发送禁止发货提示消息的 WebSocket 连接
            order_no: 订单号
            buyer_id: 买家用户ID
            chat_id: 聊天会话ID（缺失时不发消息但仍拦截 + 关闭订单）
            log_prefix: 日志前缀
            item_id: 当前订单对应的商品ID

        Returns:
            {
                'action': 'allow' | 'block' | 'card_only',
                'blocked': bool,             # 仅在 action=='block' 时为 True
                'reason_text': str,          # 配置的禁止发货原因
                'fail_record': str,          # 写入 delivery_fail_reason 的文案
                'auto_close_enabled': bool,  # 是否开启了主动关闭订单
                'order_closed': bool,        # 关闭订单是否成功
                'only_card_enabled': bool,   # 是否开启"关闭订单后继续发货"
                'total_count': int,          # 兼容字段（-1 表示未使用旧逻辑）
                'rule_code': str | None,     # 命中的规则编码
                'rule_name': str | None,     # 命中的规则名称
            }
        """
        pf = log_prefix or f'【{self.cookie_id}】'

        # 获取买家闲鱼昵称（明文），存到实例属性供后续写入订单
        self._current_buyer_fish_nick = None
        if chat_id:
            try:
                from common.utils.fish_nick_utils import get_buyer_fish_nick
                from common.utils.cookie_refresh import get_account_by_identity
                from common.db.session import async_session_maker

                latest_cookies = self.cookies_str
                try:
                    async with async_session_maker() as db_session:
                        account = await get_account_by_identity(self.cookie_id, session=db_session)
                        if account and account.cookie:
                            latest_cookies = account.cookie
                            if latest_cookies != self.cookies_str:
                                self.cookies_str = latest_cookies
                                from common.utils.xianyu_utils import trans_cookies
                                self.cookies = trans_cookies(latest_cookies)
                except Exception as db_e:
                    logger.warning(f'{pf}从数据库获取最新Cookie失败，使用内存Cookie: {db_e}')

                self._current_buyer_fish_nick = await get_buyer_fish_nick(
                    latest_cookies, chat_id, self.cookie_id
                )
            except Exception as nick_e:
                logger.warning(f'{pf}获取买家闲鱼昵称失败（不影响发货流程）: {nick_e}')

        # 调用规则引擎执行检查
        try:
            from app.services.xianyu.delivery_rules.rule_engine import execute_rules

            engine_result = await execute_rules(
                cookie_id=self.cookie_id,
                cookies_str=self.cookies_str,
                order_no=order_no,
                buyer_id=buyer_id,
                item_id=item_id,
                chat_id=chat_id,
                log_prefix=pf,
            )
        except Exception as e:
            logger.error(f'{pf}规则引擎执行异常: {self._safe_str(e)}，放行')
            return {
                'action': 'allow',
                'blocked': False,
                'reason_text': '',
                'fail_record': '',
                'auto_close_enabled': False,
                'order_closed': False,
                'only_card_enabled': False,
                'total_count': -1,
                'rule_code': None,
                'rule_name': None,
                'buyer_fish_nick': self._current_buyer_fish_nick,
            }

        # 未命中任何规则 → 放行
        if not engine_result.get('hit'):
            return {
                'action': 'allow',
                'blocked': False,
                'reason_text': '',
                'fail_record': '',
                'auto_close_enabled': False,
                'order_closed': False,
                'only_card_enabled': False,
                'total_count': -1,
                'rule_code': None,
                'rule_name': None,
                'buyer_fish_nick': self._current_buyer_fish_nick,
            }

        # 命中规则 → 执行拦截动作
        rule_code = engine_result.get('rule_code', '')
        rule_name = engine_result.get('rule_name', '')
        block_reason = engine_result.get('block_reason', '')
        auto_close_enabled = engine_result.get('auto_close_order', False)
        only_card_enabled = engine_result.get('only_card_after_close', False)
        hit_reason = engine_result.get('reason', '')

        # 1. 发送禁止发货提示消息给买家
        if block_reason and chat_id:
            try:
                await self._send_msg_with_retry(websocket, chat_id, buyer_id, block_reason)
            except Exception as send_err:
                logger.error(f'{pf}发送禁止发货提示消息异常: {self._safe_str(send_err)}')
        elif not block_reason:
            logger.info(f'{pf}规则 [{rule_name}] 未配置禁止发货原因，跳过发送消息: order_no={order_no}')
        elif not chat_id:
            logger.warning(f'{pf}缺少 chat_id，无法发送禁止发货提示: order_no={order_no}')

        # 2. 写订单 delivery_fail_reason
        fail_record = block_reason if block_reason else hit_reason
        try:
            await self._update_delivery_fail_reason(order_no, fail_record)
        except Exception as record_err:
            logger.warning(f'{pf}记录禁止发货原因到订单表失败: {self._safe_str(record_err)}')

        # 3. 按开关关闭订单
        order_closed = False
        if auto_close_enabled:
            try:
                order_closed = await self.close_order_by_seller(order_no)
                if not order_closed:
                    logger.warning(f'{pf}禁止发货后关闭订单失败：order_no={order_no}')
            except Exception as close_err:
                logger.error(f'{pf}禁止发货后关闭订单异常: {self._safe_str(close_err)}')
        else:
            logger.info(f'{pf}规则 [{rule_name}] 未开启"主动关闭订单"，跳过关闭: order_no={order_no}')

        # 4. 决定最终动作
        if auto_close_enabled and order_closed and only_card_enabled:
            action = 'card_only'
            logger.warning(
                f'{pf}❌ 命中规则 [{rule_name}] + 关闭订单成功 + 只发卡券：'
                f'order_no={order_no}, buyer_id={buyer_id}, reason={fail_record}'
            )
        else:
            action = 'block'
            logger.warning(
                f'{pf}❌ 命中规则 [{rule_name}]：order_no={order_no}, buyer_id={buyer_id}, '
                f'reason={fail_record}, auto_close={auto_close_enabled}, '
                f'order_closed={order_closed}, only_card={only_card_enabled}'
            )

        return {
            'action': action,
            'blocked': action == 'block',
            'reason_text': block_reason,
            'fail_record': fail_record,
            'auto_close_enabled': auto_close_enabled,
            'order_closed': order_closed,
            'only_card_enabled': only_card_enabled,
            'total_count': -1,
            'rule_code': rule_code,
            'rule_name': rule_name,
            'buyer_fish_nick': self._current_buyer_fish_nick,
        }

    # ==================== 卖家主动关闭订单 ====================

    # 订单关闭原因（闲鱼后台预设文案，不可随意修改）
    _CLOSE_ORDER_REASON = "其他原因"

    async def close_order_by_seller(self, order_no: str, retry_count: int = 0) -> bool:
        """卖家主动关闭订单

        调用闲鱼接口 mtop.taobao.idle.trade.merchant.close.by.seller 主动关闭指定订单。
        关闭原因固定为 `_CLOSE_ORDER_REASON`（"其他原因"），不接受外部传入。
        参照 `_fetch_order_detail_from_api` 的重试模式：
        - 第一次拿到的 set-cookie 通过 `_handle_response_cookies` 写回，重试时使用更新后的 cookie 重新签名
        - 接口调用失败/网络异常时最多重试 3 次

        Args:
            order_no: 订单号（同时作为 tid 和 bizOrderId）
            retry_count: 当前重试次数（递归内部使用）

        Returns:
            True 表示关闭成功，False 表示失败或异常（不抛异常，由调用方决定后续）
        """
        max_retry = 3
        close_reason = self._CLOSE_ORDER_REASON

        if not order_no:
            logger.warning(f"【{self.cookie_id}】关闭订单：order_no 为空，跳过")
            return False

        if not self.cookies_str:
            logger.warning(f"【{self.cookie_id}】关闭订单：未提供Cookie，跳过")
            return False

        try:
            from common.utils.xianyu_utils import trans_cookies, generate_sign

            cookies = trans_cookies(self.cookies_str)
            timestamp = str(int(time.time() * 1000))
            data_payload = {
                "tid": str(order_no),
                "bizOrderId": str(order_no),
                "closeReason": close_reason,
            }
            data_val = json.dumps(data_payload, separators=(',', ':'), ensure_ascii=False)

            token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
            if not token:
                logger.warning(f"【{self.cookie_id}】关闭订单：Cookie中未找到 _m_h5_tk")

            sign = generate_sign(timestamp, token, data_val)

            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': sign,
                'v': '2.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idle.trade.merchant.close.by.seller',
                'sessionOption': 'AutoLoginOnly',
                'spm_cnt': 'a21107h.44911108.0.0',
                'spm_pre': 'a21107h.44911108.0.0',
            }

            headers = {
                'accept': 'application/json',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded',
                'idle_site_biz_code': 'COMMONPRO',
                'idle_user_group_member_id': '',
                'pragma': 'no-cache',
                'origin': 'https://seller.goofish.com',
                'referer': 'https://seller.goofish.com/?site=COMMONPRO&spm=a21107h.44911108.0.0',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
                'cookie': self.cookies_str.replace('\n', '').replace('\r', '') if self.cookies_str else '',
            }

            api_url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idle.trade.merchant.close.by.seller/2.0/'

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    params=params,
                    data={'data': data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    res_json = await response.json()

                    # 处理响应中的set-cookie，更新本地cookie（令牌过期时服务端会返回新cookie）
                    self._handle_response_cookies(response)

                    ret_list = res_json.get('ret', []) or []
                    logger.info(
                        f"【{self.cookie_id}】关闭订单：order_no={order_no}，第{retry_count + 1}次响应 ret={ret_list}"
                    )

                    if any('SUCCESS' in ret for ret in ret_list):
                        logger.warning(
                            f"【{self.cookie_id}】✅ 订单关闭成功：order_no={order_no}, reason={close_reason}"
                        )
                        return True

                    # 调用失败：使用更新后的 cookie 重试
                    if retry_count < max_retry - 1:
                        logger.info(
                            f"【{self.cookie_id}】关闭订单失败，准备重试({retry_count + 1}/{max_retry - 1})..."
                        )
                        await asyncio.sleep(0.5)
                        return await self.close_order_by_seller(order_no, retry_count + 1)

                    logger.warning(
                        f"【{self.cookie_id}】关闭订单多次失败：order_no={order_no}, ret={ret_list}"
                    )
                    return False

        except asyncio.TimeoutError:
            logger.warning(
                f"【{self.cookie_id}】关闭订单超时（第{retry_count + 1}次）：order_no={order_no}"
            )
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self.close_order_by_seller(order_no, retry_count + 1)
            return False
        except Exception as e:
            logger.error(
                f"【{self.cookie_id}】关闭订单异常（第{retry_count + 1}次）：order_no={order_no}, {self._safe_str(e)}"
            )
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self.close_order_by_seller(order_no, retry_count + 1)
            return False
