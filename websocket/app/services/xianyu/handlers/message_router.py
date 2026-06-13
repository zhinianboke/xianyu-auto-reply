"""
消息路由和分发

从 xianyu_async.py 的 handle_message 方法中提取的主消息分发逻辑。
负责设置消息处理回调、分类消息类型、分发到对应的处理器。
"""

from loguru import logger

from app.services.xianyu.handlers.redelivery_handler import RedeliveryHandler
from app.services.xianyu.handlers.order_status_handler import OrderStatusHandler


class MessageRouter:
    """消息路由器

    管理消息处理回调的注册和分发，将不同类型的聊天消息
    （普通聊天、卡片消息、卡片更新消息）路由到对应的处理器。
    """

    def __init__(self, parent):
        """
        Args:
            parent: XianyuAsync 实例
        """
        self.parent = parent
        self.redelivery_handler = RedeliveryHandler(parent)
        self.order_status_handler = OrderStatusHandler(parent)
        self._initialized = False
        self._auto_reply_service = None

    def _ensure_initialized(self):
        """延迟初始化 MessageHandler 和 AutoReplyService"""
        if self._initialized:
            return

        parent = self.parent

        # 初始化 MessageHandler
        if not hasattr(parent, 'message_handler'):
            from app.services.xianyu.message_handler import MessageHandler
            parent.message_handler = MessageHandler(parent.cookie_id, parent.myid)

        # 初始化 AutoReplyService
        from app.services.xianyu.auto_reply_service import AutoReplyService
        self._auto_reply_service = AutoReplyService(parent.cookie_id, parent)

        # 注册回调
        self._register_chat_message_handler()
        self._register_card_message_handler()
        self._register_card_update_message_handler()

        self._initialized = True

    def _register_chat_message_handler(self):
        """注册聊天消息处理回调"""
        parent = self.parent
        auto_reply_service = self._auto_reply_service

        async def on_chat_message(parsed_message, ws):
            """处理聊天消息

            处理流程：
            0. 检查自己发出的消息是否包含重发货触发关键字 -> 提取订单号触发自动发货
            1. 处理订单状态（付款消息时异步获取订单详情）
            2. 检查评价请求消息 -> 触发自动评价流程（同时触发确认收货消息）
            3. 检查自动发货触发消息 -> 触发自动发货流程
            4. 其他消息 -> 交给auto_reply_service处理自动回复
            """
            send_message = parsed_message.get("send_message", "")
            raw_message = parsed_message.get("raw_message", {})
            item_id = parsed_message.get("item_id", "")
            send_user_id = parsed_message.get("send_user_id", "")
            msg_time = parsed_message.get("msg_time", "")

            # 0. 重发货触发检查
            if await self.redelivery_handler.handle(parsed_message, ws):
                return

            # 1. 处理订单状态
            await self.order_status_handler.process_order_status(
                raw_message, send_message, item_id, send_user_id, msg_time
            )

            # 2. 检查评价请求消息
            if auto_reply_service.is_rate_request_message(send_message):
                logger.info(f"【{parent.cookie_id}】✅ 检测到评价请求消息: {send_message}")
                await parent._handle_rate_request_message(parsed_message, ws)
                return

            # 3. 检查自动发货触发消息
            if auto_reply_service.is_auto_delivery_trigger(send_message):
                if parent.is_auto_confirm_enabled():
                    logger.info(f"【{parent.cookie_id}】✅ 触发自动发货流程: {send_message}")
                    await parent._handle_auto_delivery_from_message(parsed_message, ws)
                else:
                    logger.info(f"【{parent.cookie_id}】⚠️ 自动确认发货已关闭，跳过自动发货")
                return

            # 4. 其他消息交给 auto_reply_service 处理
            await auto_reply_service.handle_chat_message(parsed_message, ws)

        parent.message_handler.set_chat_message_handler(on_chat_message)

    def _register_card_message_handler(self):
        """注册卡片消息处理回调（小刀等）"""
        parent = self.parent

        async def on_card_message(parsed_message, ws):
            await parent._handle_card_message(parsed_message, ws)

        parent.message_handler.set_card_message_handler(on_card_message)

    def _register_card_update_message_handler(self):
        """注册卡片更新消息处理回调（付款状态变更等）"""
        parent = self.parent
        auto_reply_service = self._auto_reply_service

        async def on_card_update_message(parsed_message, ws):
            """处理卡片更新消息（付款状态变更等）

            处理流程：
            1. 获取订单详情
            2. 检查是否触发自动发货
            """
            send_message = parsed_message.get("send_message", "")
            raw_message = parsed_message.get("raw_message", {})
            item_id = parsed_message.get("item_id", "")
            send_user_id = parsed_message.get("send_user_id", "")
            msg_time = parsed_message.get("msg_time", "")

            # 处理订单状态
            await self.order_status_handler.process_order_status(
                raw_message, send_message, item_id, send_user_id, msg_time
            )

            # 检查是否是自动发货触发消息
            if auto_reply_service.is_auto_delivery_trigger(send_message):
                if parent.is_auto_confirm_enabled():
                    logger.info(
                        f"【{parent.cookie_id}】✅ 卡片更新消息触发自动发货流程: {send_message}"
                    )
                    await parent._handle_auto_delivery_from_message(parsed_message, ws)
                else:
                    logger.info(f"【{parent.cookie_id}】⚠️ 自动确认发货已关闭，跳过自动发货")
            else:
                logger.info(f"【{parent.cookie_id}】卡片更新消息触发自动回复: {send_message}")
                await auto_reply_service.handle_chat_message(parsed_message, ws)

        parent.message_handler.set_card_update_message_handler(on_card_update_message)

    async def route(self, message_data: dict, websocket) -> None:
        """消息路由入口

        确保回调已注册后，将消息交给 MessageHandler 处理。

        Args:
            message_data: 原始 WebSocket 消息数据
            websocket: WebSocket 连接对象
        """
        parent = self.parent
        try:
            self._ensure_initialized()
            await parent.message_handler.handle_message(message_data, websocket)
        except Exception as e:
            logger.error(f"【{parent.cookie_id}】处理消息异常: {e}")
