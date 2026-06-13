"""
重发货触发处理

从 xianyu_async.py 的 on_chat_message 中提取的重发货逻辑。
当卖家发送包含重发货关键词和订单号的消息时，触发自动重发货流程。
"""

import asyncio
from loguru import logger


class RedeliveryHandler:
    """重发货触发处理器

    检测卖家自己发送的消息中是否包含重发货触发关键词+订单号，
    若命中则查询订单信息并调用自动发货流程。
    """

    def __init__(self, parent):
        """
        Args:
            parent: XianyuAsync 实例，用于访问 cookie_id、auto_delivery_handler 等属性
        """
        self.parent = parent

    async def handle(self, parsed_message: dict, ws) -> bool:
        """检查并处理重发货触发

        Args:
            parsed_message: 解析后的消息数据，需包含 send_message, send_user_id, item_id 等字段
            ws: WebSocket 连接对象

        Returns:
            True 表示命中重发货逻辑（调用方应 return 不再继续处理），
            False 表示未命中，继续正常流程。
        """
        parent = self.parent
        send_message = parsed_message.get("send_message", "")
        send_user_id = parsed_message.get("send_user_id", "")
        item_id = parsed_message.get("item_id", "")
        msg_time = parsed_message.get("msg_time", "")
        raw_message = parsed_message.get("raw_message", {})

        myid = getattr(parent, 'myid', parent.cookie_id)
        if send_user_id != myid or not send_message:
            return False

        try:
            from common.db.compat import db_manager
            redelivery_keyword = db_manager.get_user_setting_by_cookie_id(
                parent.cookie_id, 'redelivery_trigger_keyword'
            )
            if not redelivery_keyword:
                return False

            redelivery_keyword = redelivery_keyword.strip()
            if not redelivery_keyword or redelivery_keyword not in send_message:
                return False

            # 去除关键词，剩余部分去除前后空格
            remaining = send_message.replace(redelivery_keyword, '', 1).strip()
            if not remaining or not remaining.isdigit():
                if remaining:
                    logger.info(
                        f"【{parent.cookie_id}】重发货触发: 去除关键词后剩余内容"
                        f"'{remaining}'不是纯数字订单号，忽略"
                    )
                return False

            order_no = remaining
            logger.info(
                f"【{parent.cookie_id}】✅ 检测到重发货触发: "
                f"关键词='{redelivery_keyword}', 订单号={order_no}"
            )

            # 从数据库查询订单信息
            order_info = db_manager.get_order_by_id(order_no)
            if not order_info:
                logger.info(
                    f"【{parent.cookie_id}】重发货触发: 订单 {order_no} 不在数据库中，创建基本记录"
                )
                try:
                    current_chat_id = parsed_message.get('chat_id', '')
                    db_manager.insert_or_update_order(
                        order_id=order_no,
                        item_id=item_id,
                        buyer_id='',
                        cookie_id=parent.cookie_id,
                        chat_id=current_chat_id,
                    )
                except Exception as insert_e:
                    logger.warning(
                        f"【{parent.cookie_id}】重发货触发: 创建订单记录失败: {insert_e}"
                    )

            # 无论订单是否已存在，都通过 API 刷新订单详情
            try:
                from common.services.order_service import OrderDetailService
                order_detail_service = OrderDetailService(parent.cookie_id, parent.cookies_str)
                await order_detail_service.fetch_and_update_order_detail(order_id=order_no)
            except Exception as fetch_e:
                logger.warning(
                    f"【{parent.cookie_id}】重发货触发: API刷新订单 {order_no} 详情失败: {fetch_e}"
                )

            # 重新获取最新的订单信息
            order_info = db_manager.get_order_by_id(order_no)
            logger.info(
                f"【{parent.cookie_id}】重发货触发: 订单 {order_no} "
                f"get_order_by_id 完整返回结果: {order_info}"
            )

            if not order_info:
                logger.warning(
                    f"【{parent.cookie_id}】重发货触发: 订单 {order_no} 无法获取信息，跳过"
                )
                return True

            order_item_id = order_info.get('item_id', '') or item_id
            order_buyer_id = order_info.get('buyer_id', '')
            order_chat_id = (
                order_info.get('chat_id', '')
                or parsed_message.get('chat_id', '')
            )

            if not (hasattr(parent, 'auto_delivery_handler') and parent.auto_delivery_handler):
                logger.warning(f"【{parent.cookie_id}】auto_delivery_handler未初始化，跳过重发货")
                return True

            # item 归属检查
            if order_item_id and order_item_id != "未知商品":
                try:
                    item_info = db_manager.get_item_info(parent.cookie_id, order_item_id)
                    if not item_info:
                        logger.warning(
                            f"【{parent.cookie_id}】重发货触发：商品 {order_item_id} 不属于当前账号，"
                            f"跳过 pre_check / freeshipping / 自动发货"
                        )
                        return True
                except Exception as e:
                    logger.error(
                        f"【{parent.cookie_id}】重发货触发：检查商品归属失败，跳过: {e}"
                    )
                    return True

            # 禁止发货预检查
            pre_check = await parent.auto_delivery_handler.pre_delivery_check_and_close(
                websocket=ws,
                order_no=order_no,
                buyer_id=order_buyer_id,
                chat_id=order_chat_id,
                log_prefix=f"【{parent.cookie_id}】重发货触发：",
                item_id=order_item_id,
            )
            pre_action = pre_check.get('action', 'allow')
            if pre_action == 'block':
                logger.info(
                    f"【{parent.cookie_id}】重发货触发：禁止发货命中，订单 {order_no} 拦截结束"
                )
                return True

            # 小刀订单 + allow：先免拼再走自动发货流程
            if order_info.get('is_bargain') and order_buyer_id and pre_action == 'allow':
                logger.info(
                    f"【{parent.cookie_id}】重发货触发: 检测到小刀订单，"
                    f"先调用免拼接口: order_id={order_no}, buyer_id={order_buyer_id}"
                )
                freeshipping_result = await parent.auto_delivery_handler.auto_freeshipping(
                    order_no, order_item_id, order_buyer_id
                )
                if freeshipping_result and freeshipping_result.get('success'):
                    success_msg = freeshipping_result.get('message', '')
                    if 'ORDER_ALREADY_DELIVERY' in success_msg or '已发货成功' in success_msg:
                        logger.info(
                            f"【{parent.cookie_id}】重发货触发: 订单 {order_no} 已发货过，只更新数据库状态"
                        )
                        try:
                            from common.services.order_service import OrderService
                            from common.db.session import async_session_maker
                            async with async_session_maker() as db_session:
                                order_service = OrderService(db_session)
                                await order_service.update_order_status(order_no, "shipped")
                        except Exception as e:
                            logger.error(f"【{parent.cookie_id}】重发货触发: 更新订单状态失败: {e}")
                        await parent.auto_delivery_handler.mark_delivery_sent(order_no)
                        return True
                    logger.info(f"【{parent.cookie_id}】重发货触发: 免拼发货成功，继续自动发货流程")
                else:
                    error_msg = (
                        freeshipping_result.get('error', '未知错误')
                        if freeshipping_result else '未知错误'
                    )
                    logger.warning(
                        f"【{parent.cookie_id}】重发货触发: 免拼发货失败: {error_msg}，继续尝试自动发货"
                    )
            elif order_info.get('is_bargain') and pre_action == 'card_only':
                logger.info(
                    f"【{parent.cookie_id}】重发货触发：小刀订单 + card_only 模式，"
                    f"订单 {order_no} 已被关闭，跳过免拼接口，直接进入卡券补发流程"
                )

            await parent.auto_delivery_handler._handle_auto_delivery(
                websocket=ws,
                message=raw_message,
                send_user_name="重发货触发",
                send_user_id=order_buyer_id,
                item_id=order_item_id,
                chat_id=order_chat_id,
                msg_time=msg_time,
                override_order_id=order_no,
                pre_check_result=pre_check,
            )
            return True

        except Exception as e:
            logger.warning(f"【{parent.cookie_id}】重发货触发关键字检查异常: {e}")
            return False
