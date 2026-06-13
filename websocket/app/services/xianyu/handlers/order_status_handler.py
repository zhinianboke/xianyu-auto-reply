"""
订单状态处理

从 xianyu_async.py 提取的订单状态相关逻辑：
- _extract_order_id: 从消息中提取订单ID
- _process_order_status: 处理付款消息，创建订单记录
- _fetch_order_detail_async: 异步获取订单详情
"""

import asyncio
import json
import re
from loguru import logger


class OrderStatusHandler:
    """订单状态处理器

    负责从消息中提取订单ID、识别付款消息、创建/更新订单记录、
    异步获取订单详情。
    """

    def __init__(self, parent):
        """
        Args:
            parent: XianyuAsync 实例
        """
        self.parent = parent

    def extract_order_id(self, message: dict) -> str:
        """从消息中提取订单ID（参照旧框架utils.py的extract_order_id实现）

        Args:
            message: 原始消息数据

        Returns:
            订单ID字符串，未找到返回空字符串
        """
        parent = self.parent
        try:
            order_id = None

            # 方法1: 从message['1']['6']中提取
            message_1 = message.get('1', {})
            if isinstance(message_1, dict):
                message_1_6 = message_1.get('6', {})
                if isinstance(message_1_6, dict):
                    content_json_str = ''
                    inner_3 = message_1_6.get('3', {})
                    if isinstance(inner_3, dict):
                        content_json_str = inner_3.get('5', '')

                    if content_json_str:
                        try:
                            content_data = json.loads(content_json_str)

                            # 从button的targetUrl中提取orderId
                            target_url = (
                                content_data.get('dxCard', {})
                                .get('item', {})
                                .get('main', {})
                                .get('exContent', {})
                                .get('button', {})
                                .get('targetUrl', '')
                            )
                            if target_url:
                                order_match = re.search(r'orderId=(\d+)', target_url)
                                if order_match:
                                    order_id = order_match.group(1)

                            # 从main的targetUrl中提取
                            if not order_id:
                                main_target_url = (
                                    content_data.get('dxCard', {})
                                    .get('item', {})
                                    .get('main', {})
                                    .get('targetUrl', '')
                                )
                                if main_target_url:
                                    order_match = re.search(
                                        r'order_detail\?id=(\d+)', main_target_url
                                    )
                                    if order_match:
                                        order_id = order_match.group(1)

                        except Exception:
                            pass

            # 方法2: 在整个消息中搜索订单ID模式
            if not order_id:
                message_str = str(message)
                patterns = [
                    r'orderId[=:](\d{10,})',
                    r'order_detail\?id=(\d{10,})',
                    r'"id"\s*:\s*"?(\d{10,})"?',
                    r'bizOrderId[=:](\d{10,})',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, message_str)
                    if matches:
                        order_id = matches[0]
                        break

            if order_id:
                logger.info(f'【{parent.cookie_id}】🎯 提取到订单ID: {order_id}')

            return order_id or ""
        except Exception as e:
            logger.error(f"【{parent.cookie_id}】提取订单ID失败: {e}")
            return ""

    async def process_order_status(
        self, message: dict, send_message: str, item_id: str, buyer_id: str, msg_time: str
    ) -> None:
        """处理订单状态（参照旧框架_process_order_status_handler）

        当检测到付款相关消息时：
        1. 先创建订单记录（如果不存在）
        2. 异步获取订单详情（用于获取规格信息）

        Args:
            message: 原始消息数据
            send_message: 消息内容
            item_id: 商品ID
            buyer_id: 买家ID
            msg_time: 消息时间
        """
        parent = self.parent
        try:
            fetch_detail_messages = [
                '[我已拍下，待付款]',
                '[我已付款，等待你发货]',
                '[买家已付款]',
                '[付款完成]',
                '[已付款，待发货]',
            ]

            if send_message not in fetch_detail_messages:
                return

            order_id = self.extract_order_id(message)
            logger.info(
                f"【{parent.cookie_id}】付款消息检测: {send_message}, 提取订单ID: {order_id}"
            )

            if not order_id:
                logger.warning(f"【{parent.cookie_id}】付款消息无法提取订单ID: {send_message}")
                return

            logger.info(f"【{parent.cookie_id}】提取到: item_id={item_id}, buyer_id={buyer_id}")

            # 提取chat_id
            chat_id = ""
            try:
                msg_1 = message.get("1", {})
                if isinstance(msg_1, dict):
                    chat_id_raw = msg_1.get("2", "")
                    chat_id = (
                        chat_id_raw.split('@')[0]
                        if '@' in str(chat_id_raw)
                        else str(chat_id_raw)
                    )
                if not chat_id:
                    chat_id_raw = message.get("2", "")
                    if chat_id_raw:
                        chat_id = (
                            str(chat_id_raw).split('@')[0]
                            if '@' in str(chat_id_raw)
                            else str(chat_id_raw)
                        )
            except Exception:
                pass

            # 根据消息类型确定订单状态
            if send_message == '[我已拍下，待付款]':
                order_status = "pending_payment"
            else:
                order_status = "pending_ship"

            # 先创建订单记录
            try:
                from common.services.order_service import OrderService
                from common.db.session import async_session_maker

                async with async_session_maker() as session:
                    order_service = OrderService(session)
                    await order_service.create_order_from_message(
                        order_no=order_id,
                        account_id=parent.cookie_id,
                        status=order_status,
                        item_id=item_id,
                        buyer_id=buyer_id,
                        chat_id=chat_id,
                    )
                    logger.info(
                        f"【{parent.cookie_id}】订单 {order_id} 创建/更新成功，状态: {order_status}"
                    )
            except Exception as e:
                logger.error(f"【{parent.cookie_id}】创建订单失败: {e}")

            # 异步获取订单详情，不阻塞主流程
            asyncio.create_task(
                self._fetch_order_detail_async(order_id, item_id, buyer_id)
            )

        except Exception as e:
            logger.error(f"【{parent.cookie_id}】处理订单状态失败: {e}")

    async def _fetch_order_detail_async(
        self, order_id: str, item_id: str = None, buyer_id: str = None
    ) -> None:
        """异步获取订单详情

        不阻塞主流程，用于获取订单的规格、数量、收货人等信息。

        Args:
            order_id: 订单ID
            item_id: 商品ID
            buyer_id: 买家ID
        """
        parent = self.parent
        try:
            await asyncio.sleep(1)

            logger.info(
                f"【{parent.cookie_id}】开始异步获取订单详情: "
                f"{order_id}, item_id={item_id}, buyer_id={buyer_id}"
            )

            from common.services.order_service import OrderDetailService

            order_detail_service = OrderDetailService(parent.cookie_id, parent.cookies_str)
            result = await order_detail_service.fetch_and_update_order_detail(
                order_id=order_id,
                item_id=item_id,
                buyer_id=buyer_id,
            )

            if result:
                logger.info(f"【{parent.cookie_id}】订单详情获取成功: {order_id}")
            else:
                logger.warning(f"【{parent.cookie_id}】订单详情获取失败: {order_id}")

        except Exception as e:
            logger.error(f"【{parent.cookie_id}】异步获取订单详情失败: {e}")
