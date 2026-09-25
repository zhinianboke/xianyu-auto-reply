"""
同意后发货 - 提货页服务（backend-web 公开层）

功能：
1. 校验提货页订单：按订单主键(orderId) + 订单号(orderNo) 双重校验
   （不存在 / 不匹配 均返回明确中文提示）
2. 买家点击「同意」：Redis 锁串行 + 幂等 → 调 websocket 内部接口触发真实发货并返回卡券内容
3. 回显商品信息：商品标题（商品表 xy_items，缺失时用自动回复日志记录的标题兜底）
   + 闲鱼商品详情页地址 + 商品展示入口（商品自身 metadata_json.display_links 与用户默认
   通用模板按名称去重合并，商品条目优先）

说明：
- 本层为无认证公开接口的业务实现，仅读取展示所需的最小订单信息，不下发敏感字段。
- 实际的确认发货/免拼/取卡在 websocket 服务完成（需在线账号实例）。
- 跨进程并发（买家重复点击、与定时补发货争抢）由 Redis 发货锁保证串行。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.services.display_link_service import (
    merge_display_links,
    normalize_display_links,
    template_row_to_entry,
)
from app.services.websocket_client import websocket_client
from app.services.item_query_service import ItemQueryService
from common.db.redis_client import release_delivery_lock, try_acquire_delivery_lock
from common.models.display_link_template import DisplayLinkTemplate
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.services.order_service import OrderService
from common.utils.xianyu_utils import canonical_goofish_item_url


class AgreePickupService:
    """同意后发货提货页服务"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_and_validate(
        self, order_no: str, order_id: str
    ) -> Tuple[bool, str, Optional[XYOrder]]:
        """按订单主键查订单并校验订单号匹配。返回 (ok, message, order)。

        order_id 以字符串入参并在此安全解析为整数，非法/缺失一律返回明确提示
        （遵循全站「无论成败均 HTTP 200，业务错误走响应体」约定，避免框架抛 422）。
        """
        order_no = (order_no or "").strip()
        try:
            order_pk = int(str(order_id).strip())
        except (TypeError, ValueError):
            order_pk = 0
        if not order_no or order_pk <= 0:
            return False, "链接无效，缺少订单参数", None
        result = await self.session.execute(select(XYOrder).where(XYOrder.id == order_pk))
        order = result.scalars().first()
        if not order:
            return False, "订单不存在", None
        if (order.order_no or "").strip() != order_no:
            return False, "订单号与订单id不匹配", None
        return True, "", order

    @staticmethod
    def _order_view(
        order: XYOrder,
        item_title: str = "",
        query_buttons: Optional[list] = None,
        display_links: Optional[list] = None,
    ) -> Dict[str, Any]:
        """提货页可展示的订单信息（最小必要字段）

        Args:
            order: 订单对象
            item_title: 商品标题（由调用方查商品表取得，取不到传空字符串）
            query_buttons: 商品配置的通用查询按钮（只含 name 字段；无配置传空列表）
            display_links: 商品配置的展示入口（完整内容含 name/type/url/title/content/note，
                均为展示文案不敏感，可下发；无配置传空列表）
        Returns:
            提货页展示字段字典
        """
        return {
            "order_no": order.order_no,
            "amount": str(order.amount) if order.amount is not None else None,
            "quantity": order.quantity,
            "spec_name": order.spec_name,
            "spec_value": order.spec_value,
            "item_id": order.item_id,
            # 标题取不到时前端退化展示商品ID，不展示空白
            "item_title": item_title or None,
            # 闲鱼商品详情页地址，供买家点击核对商品；无商品ID时为空
            "item_url": canonical_goofish_item_url(order.item_id) if order.item_id else None,
            "already_agreed": bool(order.agree_deliver_agreed),
            # 已同意时回显发货内容，未同意时不下发
            "content": order.delivery_content if order.agree_deliver_agreed else None,
            "query_buttons": query_buttons or [],
            # 展示入口不做 enabled 过滤：该体系没有启用开关，数组里有就展示
            "display_links": display_links or [],
        }

    async def _load_query_buttons(self, order: XYOrder) -> Tuple[list, list]:
        """读取商品配置的通用查询按钮与展示入口（商品自身条目 + 用户默认模板合并）。

        查询按钮含启用标记（只取 name/enabled 下发给买家）：
        停用的按钮也会下发（enabled=False），提货页据此隐藏跳转按钮本身，
        但保留工具下载/API 等配套入口的展示。
        任何异常都按空数组处理，不阻断提货主流程。

        Returns:
            (query_buttons, display_links)
        """
        try:
            buttons = await ItemQueryService(self.session).get_buttons_for_item(
                order.owner_id, order.item_id or ""
            )
            query_buttons = [
                {"name": button.get("name") or "查询", "enabled": button.get("enabled", True) is not False}
                for button in buttons
            ]
        except Exception as e:
            logger.warning(f"[同意提货] 查询按钮配置读取失败 order={order.order_no}: {e}")
            query_buttons = []

        display_links = await self._load_display_links(order)
        return query_buttons, display_links

    async def _load_display_links(self, order: XYOrder) -> list:
        """读取商品展示入口 = 商品自身条目 + 用户默认模板条目（规范化后按名称去重，商品优先）。

        读取时重新过一遍 validate_display_link_entry（经 normalize_display_links）：
        既收敛字段白名单（metadata 里可能残留 passthrough/导入写入的 headers/Cookie 等键），
        也让非法商品条目不再遮蔽同名默认模板。
        完整内容下发给买家；name/type/url/title/content/note 均为展示文案，不含敏感信息；
        不做 enabled 过滤（该体系没有启用开关，数组里有就展示）。
        任何异常都按空数组处理，不阻断提货主流程。
        """
        try:
            if not order.item_id:
                return []
            result = await self.session.execute(
                select(XYCatalogItem).where(
                    XYCatalogItem.owner_id == order.owner_id,
                    XYCatalogItem.item_id == order.item_id,
                )
            )
            item = result.scalars().first()
            links = (item.metadata_json or {}).get("display_links") if item else None

            # 默认模板：读取时合并，改动即时全店生效
            template_rows = (
                await self.session.execute(
                    select(DisplayLinkTemplate).where(
                        DisplayLinkTemplate.user_id == order.owner_id,
                        DisplayLinkTemplate.is_default.is_(True),
                    ).order_by(DisplayLinkTemplate.id)
                )
            ).scalars().all()

            # 先各自规范化（丢弃脏数据/多余键）再合并，避免非法商品条目按名称占位遮蔽模板
            return merge_display_links(
                normalize_display_links(links),
                normalize_display_links([template_row_to_entry(r) for r in template_rows]),
            )
        except Exception as e:
            logger.warning(f"[同意提货] 展示入口配置读取失败 order={order.order_no}: {e}")
            return []

    async def query_order(
        self, order_no: str, order_id: str
    ) -> Tuple[bool, str, Optional[dict]]:
        """提货页加载：校验订单并返回展示信息 + 是否已同意/发货内容。"""
        ok, message, order = await self._load_and_validate(order_no, order_id)
        if not ok:
            return False, message, None
        # 商品标题复用公共订单服务的多来源解析（商品表 → 自动回复日志兜底，取不到返回空串）
        item_title = await OrderService(self.session).resolve_item_title(
            order.owner_id, order.item_id or ""
        )
        query_buttons, display_links = await self._load_query_buttons(order)
        return True, "查询成功", self._order_view(order, item_title, query_buttons, display_links)

    async def agree(
        self, order_no: str, order_id: str
    ) -> Tuple[bool, str, Optional[dict]]:
        """买家点击「同意」：Redis 锁 + 幂等 → 调 websocket 触发发货并返回卡券内容。"""
        ok, message, order = await self._load_and_validate(order_no, order_id)
        if not ok:
            return False, message, None

        real_order_no = order.order_no

        # 幂等快速路径：已同意且已有内容，直接回显，不再触发发货
        if order.agree_deliver_agreed and order.delivery_content:
            return True, "您已同意发货，以下为发货内容", {
                "order_no": real_order_no,
                "content": order.delivery_content,
                "already_agreed": True,
            }

        # Redis 发货锁：与买家重复点击、定时补发货互斥（key 内部为 order:{order_no}）
        lock_result = await try_acquire_delivery_lock(
            real_order_no, expire=120, holder_info="agree_pickup", wait_timeout=5
        )
        if lock_result.is_locked_by_other:
            return False, "订单正在处理中，请稍后再试", None
        if lock_result.has_error:
            return False, "系统繁忙，请稍后再试", None
        if not lock_result.success:
            return False, "订单正在处理中，请稍后再试", None

        try:
            # 触发真实发货（websocket 侧再做本地锁 + 幂等，权威处理确认发货/免拼/取卡）
            resp = await websocket_client.agree_pickup_deliver(real_order_no)
            if not isinstance(resp, dict):
                return False, "发货失败，请稍后重试或联系卖家", None
            success = bool(resp.get("success"))
            msg = resp.get("message") or ("发货成功" if success else "发货失败，请稍后重试或联系卖家")

            # 发卡成功后按账号配置主动提醒买家确认收货（账号级 agree_pickup_notice_*，默认关闭）
            if success and order.account_id and order.chat_id:
                try:
                    acct_result = await self.session.execute(
                        select(XYAccount).where(XYAccount.account_id == order.account_id)
                    )
                    account = acct_result.scalars().first()
                    if account and account.agree_pickup_notice_enabled:
                        content = (account.agree_pickup_notice_content or "").strip()
                        if content:
                            await websocket_client.send_message(
                                order.account_id, order.chat_id, content
                            )
                except Exception as e:
                    logger.error(f"[同意提货] 确认收货提醒发送失败 order={real_order_no}: {e}")

            return success, msg, resp.get("data")
        finally:
            await release_delivery_lock(lock_result)
