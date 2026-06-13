"""
订单服务

功能：
1. 订单列表查询（支持按账号、状态筛选）
2. 订单详情查询
3. 订单状态更新
4. 待发货订单查询
5. 关联商品表获取商品标题

此服务位于common目录下，供backend-web和websocket服务共同使用
"""
from __future__ import annotations

import asyncio
from typing import Optional, Dict

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from common.models.xy_order import XYOrder
from common.models.xy_catalog_item import XYCatalogItem
from common.models.auto_reply_message_log import XYAutoReplyMessageLog


class OrderService:
    """订单服务 - 读写xy_orders表"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_item_titles(self, owner_id: int | None, item_ids: list[str]) -> Dict[str, str]:
        """批量获取商品标题
        
        Args:
            owner_id: 用户ID，None表示不限制用户（管理员）
            item_ids: 商品ID列表
            
        Returns:
            {item_id: title} 字典
        """
        if not item_ids:
            return {}
        
        try:
            unique_item_ids = list(set(item_ids))
            stmt = select(XYCatalogItem.item_id, XYCatalogItem.title).where(
                XYCatalogItem.item_id.in_(unique_item_ids)
            )
            if owner_id is not None:
                stmt = stmt.where(XYCatalogItem.owner_id == owner_id)
            result = await self.session.execute(stmt)
            return {row.item_id: row.title or "" for row in result.all()}
        except Exception as e:
            logger.warning(f"获取商品标题失败: {e}")
            return {}

    async def list_orders(
        self,
        owner_id: int | None,
        *,
        account_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        delivery_method: str | None = None,
        is_bargain: bool | None = None,
        is_rated: bool | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        delivery_send_status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[XYOrder], int, Dict[str, str]]:
        """获取订单列表（分页），支持多条件筛选
        
        Args:
            owner_id: 用户ID，None表示查询所有用户（管理员）
            account_id: 账号ID筛选
            status: 订单状态筛选
            search: 搜索关键词（匹配订单号、商品ID、买家ID）
            delivery_method: 发货方式筛选（manual/auto/scheduled）
            is_bargain: 是否小刀筛选
            is_rated: 是否已评价筛选
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            delivery_send_status: 关联自动发货消息日志的发送状态筛选（success/failed/unknown/timeout）
            page: 页码
            page_size: 每页数量
            
        Returns:
            (订单列表, 总数, 商品标题字典)
        """
        from sqlalchemy import and_, or_
        from datetime import datetime, timedelta
        
        base_stmt = select(XYOrder)
        conditions = []
        
        if owner_id is not None:
            conditions.append(XYOrder.owner_id == owner_id)
        if account_id:
            conditions.append(XYOrder.account_id == account_id)
        if status:
            conditions.append(XYOrder.status == status)
        
        # 搜索关键词（模糊匹配订单号、商品ID、买家ID）
        if search:
            conditions.append(
                or_(
                    XYOrder.order_no.ilike(f"%{search}%"),
                    XYOrder.item_id.ilike(f"%{search}%"),
                    XYOrder.buyer_id.ilike(f"%{search}%"),
                )
            )
        
        # 发货方式筛选
        if delivery_method is not None:
            if delivery_method == "none":
                # 未发货：delivery_method 为空或 None
                conditions.append(
                    or_(
                        XYOrder.delivery_method.is_(None),
                        XYOrder.delivery_method == ""
                    )
                )
            else:
                conditions.append(XYOrder.delivery_method == delivery_method)
        
        # 是否小刀筛选
        if is_bargain is not None:
            conditions.append(XYOrder.is_bargain == is_bargain)
        
        # 是否已评价筛选
        if is_rated is not None:
            conditions.append(XYOrder.is_rated == is_rated)
        
        # 时间范围筛选
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                conditions.append(XYOrder.placed_at >= start_dt)
            except ValueError:
                logger.warning(f"无效的开始日期格式: {start_date}")
        
        if end_date:
            try:
                # 结束日期需要加一天，以包含当天的所有数据
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                conditions.append(XYOrder.placed_at < end_dt)
            except ValueError:
                logger.warning(f"无效的结束日期格式: {end_date}")
        
        # 关联自动发货消息日志的发送状态筛选
        # 取每个订单号最新一条自动发货日志（以 max(id) 近似最新，与发送状态展示口径一致），
        # 再按发送状态过滤，使列表筛选结果与“发送状态”列显示保持一致。
        if delivery_send_status and delivery_send_status.strip():
            latest_log_subq = (
                select(
                    XYAutoReplyMessageLog.order_no.label("order_no"),
                    func.max(XYAutoReplyMessageLog.id).label("max_id"),
                )
                .where(
                    XYAutoReplyMessageLog.reply_strategy == "auto_delivery",
                    XYAutoReplyMessageLog.order_no.isnot(None),
                )
                .group_by(XYAutoReplyMessageLog.order_no)
                .subquery()
            )
            matched_order_nos = (
                select(XYAutoReplyMessageLog.order_no)
                .join(latest_log_subq, XYAutoReplyMessageLog.id == latest_log_subq.c.max_id)
                .where(XYAutoReplyMessageLog.send_status == delivery_send_status.strip())
            )
            conditions.append(XYOrder.order_no.in_(matched_order_nos))
        
        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))
        
        # 查询总数：直接基于条件统计，避免把整表 SELECT 包进子查询
        count_stmt = select(func.count(XYOrder.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        
        offset = (page - 1) * page_size
        # MySQL 不支持 NULLS LAST，用 CASE WHEN 实现 NULL 排最后
        from sqlalchemy import case
        stmt = base_stmt.order_by(
            case((XYOrder.placed_at.is_(None), 1), else_=0),
            XYOrder.placed_at.desc()
        ).offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        orders = list(result.scalars().all())
        
        item_ids = [order.item_id for order in orders if order.item_id]
        item_titles = await self._get_item_titles(owner_id, item_ids)
        
        return orders, total, item_titles

    async def get_delivery_log_status_map(self, order_nos: list[str]) -> Dict[str, Dict[str, str | None]]:
        """批量查询订单对应的自动发货消息日志发送状态

        以订单号关联自动发货日志（reply_strategy == 'auto_delivery'），取每个订单号
        最新一条日志的发送状态与发送失败原因，供订单列表关联展示。

        Args:
            order_nos: 订单号列表

        Returns:
            { 订单号: {"send_status": ..., "send_fail_reason": ...} }
            没有对应日志的订单号不会出现在返回结果中。
        """
        result_map: Dict[str, Dict[str, str | None]] = {}
        valid_order_nos = [no for no in order_nos if no]
        if not valid_order_nos:
            return result_map

        try:
            # 先取每个订单号最新一条自动发货日志的主键（max(id) 即最新插入），
            # 再回查该日志的发送状态与失败原因，保证与"发送状态"筛选口径完全一致。
            latest_log_subq = (
                select(
                    XYAutoReplyMessageLog.order_no.label("order_no"),
                    func.max(XYAutoReplyMessageLog.id).label("max_id"),
                )
                .where(
                    XYAutoReplyMessageLog.order_no.in_(valid_order_nos),
                    XYAutoReplyMessageLog.reply_strategy == "auto_delivery",
                )
                .group_by(XYAutoReplyMessageLog.order_no)
                .subquery()
            )
            stmt = (
                select(
                    XYAutoReplyMessageLog.order_no,
                    XYAutoReplyMessageLog.send_status,
                    XYAutoReplyMessageLog.send_fail_reason,
                )
                .join(latest_log_subq, XYAutoReplyMessageLog.id == latest_log_subq.c.max_id)
            )
            rows = (await self.session.execute(stmt)).all()
            for order_no, send_status, send_fail_reason in rows:
                result_map[order_no] = {
                    "send_status": send_status,
                    "send_fail_reason": send_fail_reason,
                }
        except Exception as e:
            logger.error(f"查询订单自动发货日志发送状态失败: {e}")

        return result_map

    async def get_order_by_id(self, order_no: str) -> Optional[XYOrder]:
        """根据订单号获取订单"""
        stmt = select(XYOrder).where(XYOrder.order_no == order_no)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_item_title(self, owner_id: int, item_id: str) -> str:
        """获取单个商品标题"""
        if not item_id:
            return ""
        
        try:
            stmt = select(XYCatalogItem.title).where(
                XYCatalogItem.owner_id == owner_id,
                XYCatalogItem.item_id == item_id
            ).limit(1)
            result = await self.session.execute(stmt)
            row = result.scalar()
            return row or ""
        except Exception as e:
            logger.warning(f"获取商品标题失败: {e}")
            return ""

    async def get_order_by_no(self, order_no: str) -> Optional[XYOrder]:
        """根据订单号获取订单（别名方法）"""
        return await self.get_order_by_id(order_no)

    async def update_order_status(self, order_no: str, status: str) -> bool:
        """更新订单状态"""
        try:
            stmt = (
                update(XYOrder)
                .where(XYOrder.order_no == order_no)
                .values(status=status)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            await self.session.rollback()
            return False

    async def update_order_chat_id(self, order_no: str, chat_id: str) -> bool:
        """更新订单的聊天会话ID（chat_id）
        
        场景：订单手动发货时发现 chat_id 为空，
        调用闲鱼 LWP 接口创建会话后，补写回订单表。
        
        Args:
            order_no: 订单号
            chat_id: 聊天会话ID（不带 @goofish 后缀）
            
        Returns:
            是否更新成功
        """
        if not chat_id:
            logger.warning(f"更新订单 chat_id 失败: chat_id 为空 (order_no={order_no})")
            return False
        try:
            stmt = (
                update(XYOrder)
                .where(XYOrder.order_no == order_no)
                .values(chat_id=chat_id)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"更新订单 chat_id 失败: order_no={order_no}, chat_id={chat_id}, 错误={e}")
            await self.session.rollback()
            return False

    async def get_pending_order_by_buyer(
        self,
        account_pk: int,
        buyer_id: str,
        item_id: Optional[str] = None,
    ) -> Optional[XYOrder]:
        """根据买家ID获取待发货订单
        
        Args:
            account_pk: 账号主键
            buyer_id: 买家ID
            item_id: 商品ID（可选）
            
        Returns:
            待发货订单或None
        """
        try:
            from common.models.xy_account import XYAccount
            
            account_stmt = select(XYAccount).where(XYAccount.id == account_pk)
            account_result = await self.session.execute(account_stmt)
            account = account_result.scalars().first()
            
            if not account:
                return None
            
            stmt = select(XYOrder).where(
                XYOrder.owner_id == account.owner_id,
                XYOrder.account_id == account.account_id,
                XYOrder.buyer_id == buyer_id,
                XYOrder.status.in_(["pending", "paid", "待发货"]),
            )
            
            if item_id:
                stmt = stmt.where(XYOrder.item_id == item_id)
            
            stmt = stmt.order_by(XYOrder.created_at.desc()).limit(1)
            result = await self.session.execute(stmt)
            return result.scalars().first()
            
        except Exception as e:
            logger.error(f"获取待发货订单失败: {e}")
            return None

    async def update_order_delivery_info(
        self,
        order_no: str,
        status: str,
        delivery_method: str,
        delivery_content: str | None = None,
        buyer_fish_nick: str | None = None,
    ) -> bool:
        """更新订单发货信息
        
        Args:
            order_no: 订单号
            status: 新状态
            delivery_method: 发货方式 (manual-手动发货, auto-自动发货, scheduled-定时发货)
            delivery_content: 发货内容（卡券内容）
            buyer_fish_nick: 买家闲鱼昵称（明文）
            
        Returns:
            是否更新成功
        """
        try:
            if delivery_content and len(delivery_content) > 2000:
                delivery_content = delivery_content[:1997] + "..."
            
            values = {
                "status": status,
                "delivery_method": delivery_method,
                "delivery_content": delivery_content,
                "delivery_fail_reason": None,  # 发货成功，清空失败原因
            }
            if buyer_fish_nick:
                values["buyer_fish_nick"] = buyer_fish_nick

            stmt = (
                update(XYOrder)
                .where(XYOrder.order_no == order_no)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"更新订单发货信息失败: {e}")
            await self.session.rollback()
            return False

    async def record_delivery_for_closed_order(
        self,
        order_no: str,
        delivery_method: str,
        delivery_content: str | None = None,
        buyer_fish_nick: str | None = None,
    ) -> bool:
        """专为「禁止发货 + 主动关闭订单 + 关闭后只发卡券」场景设计的记录方法

        与 update_order_delivery_info 的区别：
          - 不修改 status：因为订单已经被卖家主动关闭（status 已由关闭流程更新），
            这里再标记为 'shipped' 会导致与闲鱼平台真实状态冲突
          - 不清空 delivery_fail_reason：保留 pre_delivery_check_and_close 写入的
            "禁止发货原因"，便于后续追溯为什么走了 card_only 流程

        仅更新 delivery_method 和 delivery_content，让卖家能在订单详情看到补发的卡券内容。

        Args:
            order_no: 订单号
            delivery_method: 发货方式（沿用 'auto' / 'manual' / 'scheduled' 等）
            delivery_content: 补发的卡券内容（>2000 字会截断）
            buyer_fish_nick: 买家闲鱼昵称（明文）

        Returns:
            是否更新成功
        """
        try:
            if delivery_content and len(delivery_content) > 2000:
                delivery_content = delivery_content[:1997] + "..."

            values = {
                "delivery_method": delivery_method,
                "delivery_content": delivery_content,
            }
            if buyer_fish_nick:
                values["buyer_fish_nick"] = buyer_fish_nick

            stmt = (
                update(XYOrder)
                .where(XYOrder.order_no == order_no)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"记录已关闭订单的卡券补发信息失败: {e}")
            await self.session.rollback()
            return False

    async def update_order_delivery_fail_reason(
        self,
        order_no: str,
        fail_reason: str
    ) -> bool:
        """更新订单发货失败原因
        
        Args:
            order_no: 订单号
            fail_reason: 发货失败原因
            
        Returns:
            是否更新成功
        """
        try:
            if fail_reason and len(fail_reason) > 2000:
                fail_reason = fail_reason[:1997] + "..."
            
            stmt = (
                update(XYOrder)
                .where(XYOrder.order_no == order_no)
                .values(delivery_fail_reason=fail_reason)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"更新订单发货失败原因失败: {e}")
            await self.session.rollback()
            return False

    async def create_order_from_message(
        self,
        order_no: str,
        account_id: str,
        status: str,
        item_id: str = None,
        buyer_id: str = None,
        chat_id: str = None,
        price: str = None,
    ) -> bool:
        """从消息创建订单记录
        
        Args:
            order_no: 订单号
            account_id: 账号ID
            status: 订单状态
            item_id: 商品ID（可选）
            buyer_id: 买家ID（可选）
            chat_id: 聊天会话ID（可选）
            price: 价格（可选）
            
        Returns:
            是否创建成功
        """
        try:
            from common.models.xy_account import XYAccount
            from common.models.xy_catalog_item import XYCatalogItem
            
            # 获取账号信息
            account_stmt = select(XYAccount).where(XYAccount.account_id == account_id)
            account_result = await self.session.execute(account_stmt)
            account = account_result.scalars().first()
            
            if not account:
                logger.warning(f"创建订单失败：账号 {account_id} 不存在")
                return False
            
            # 如果提供了商品ID，验证商品是否属于当前账号
            if item_id:
                item_stmt = select(XYCatalogItem).where(
                    XYCatalogItem.item_id == item_id,
                    XYCatalogItem.account_pk == account.id
                )
                item_result = await self.session.execute(item_stmt)
                item = item_result.scalars().first()
                
                if not item:
                    logger.warning(
                        f"创建订单失败：商品 {item_id} 不属于账号 {account_id} "
                        f"(account_pk={account.id})，跳过处理"
                    )
                    return False
            
            # 检查订单是否已存在
            existing_stmt = select(XYOrder).where(XYOrder.order_no == order_no)
            existing_result = await self.session.execute(existing_stmt)
            existing_order = existing_result.scalars().first()
            
            if existing_order:
                # 订单已存在，准备更新字段
                update_values = {}
                stale_statuses = {"pending_payment", "pending_ship", "pending", "paid"}
                terminal_statuses = {"shipped", "completed", "cancelled", "closed", "refunded"}
                is_stale_downgrade = (
                    existing_order.status in terminal_statuses and status in stale_statuses
                ) or (
                    existing_order.status in {"pending_ship", "pending", "paid"}
                    and status == "pending_payment"
                )
                if status and status != existing_order.status and not is_stale_downgrade:
                    update_values['status'] = status
                
                # 如果要更新item_id，需要验证商品归属
                if item_id and not existing_order.item_id:
                    item_stmt = select(XYCatalogItem).where(
                        XYCatalogItem.item_id == item_id,
                        XYCatalogItem.account_pk == account.id
                    )
                    item_result = await self.session.execute(item_stmt)
                    item = item_result.scalars().first()
                    
                    if not item:
                        logger.warning(
                            f"更新订单失败：商品 {item_id} 不属于账号 {account_id} "
                            f"(account_pk={account.id})，跳过更新"
                        )
                        return False
                    
                    update_values['item_id'] = item_id
                
                if buyer_id and not existing_order.buyer_id:
                    update_values['buyer_id'] = buyer_id
                if chat_id and not existing_order.chat_id:
                    update_values['chat_id'] = chat_id
                
                if update_values:
                    update_stmt = update(XYOrder).where(XYOrder.order_no == order_no).values(**update_values)
                    await self.session.execute(update_stmt)
                    await self.session.commit()
                    logger.info(f"订单 {order_no} 已存在，更新字段: {update_values}")
                else:
                    logger.info(f"订单 {order_no} 已存在，无需更新")
                return True
            
            # 创建新订单（使用当前北京时间作为下单时间）
            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            now_beijing = datetime.now(beijing_tz).replace(tzinfo=None)
            
            new_order = XYOrder(
                owner_id=account.owner_id,
                account_id=account_id,
                order_no=order_no,
                item_id=item_id or "",
                buyer_id=buyer_id or "",
                chat_id=chat_id or "",
                amount=price or None,
                status=status,
                placed_at=now_beijing,
            )
            self.session.add(new_order)
            await self.session.commit()
            logger.info(f"订单 {order_no} 创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            await self.session.rollback()
            return False

    async def delete_order(self, order_id: int, owner_id: int) -> bool:
        """删除订单
        
        Args:
            order_id: 订单ID（主键）
            owner_id: 用户ID（用于权限验证）
            
        Returns:
            是否删除成功
        """
        try:
            stmt = select(XYOrder).where(
                XYOrder.id == order_id,
                XYOrder.owner_id == owner_id
            )
            result = await self.session.execute(stmt)
            order = result.scalars().first()
            
            if not order:
                return False
            
            delete_stmt = delete(XYOrder).where(XYOrder.id == order_id)
            await self.session.execute(delete_stmt)
            await self.session.commit()
            logger.info(f"订单 {order_id} 删除成功")
            return True
            
        except Exception as e:
            logger.error(f"删除订单失败: {e}")
            await self.session.rollback()
            return False

    async def batch_delete_orders(self, order_ids: list[int], owner_id: int) -> dict:
        """批量删除订单
        
        Args:
            order_ids: 订单ID列表（主键）
            owner_id: 用户ID（用于权限验证，None表示管理员）
            
        Returns:
            { deleted: int, failed: int }
        """
        deleted = 0
        failed = 0
        try:
            conditions = [XYOrder.id.in_(order_ids)]
            if owner_id is not None:
                conditions.append(XYOrder.owner_id == owner_id)
            
            delete_stmt = delete(XYOrder).where(*conditions)
            result = await self.session.execute(delete_stmt)
            await self.session.commit()
            deleted = result.rowcount
            failed = len(order_ids) - deleted
            logger.info(f"批量删除订单: 删除{deleted}条, 失败{failed}条")
        except Exception as e:
            logger.error(f"批量删除订单失败: {e}")
            await self.session.rollback()
            failed = len(order_ids)
        
        return {'deleted': deleted, 'failed': failed}

    # ---- 获取闲鱼卖家订单列表 ----

    # 闲鱼订单状态 → 系统状态映射
    _XIANYU_STATUS_MAP = {
        '待付款': 'pending_payment',
        '待发货': 'pending_ship',
        '已发货': 'shipped',
        '交易成功': 'completed',
        '交易关闭': 'cancelled',
        '退款中': 'refunding',
        '退款成功': 'refunded',
        '已退款': 'refunded',
        '退款关闭': 'cancelled',
    }
    _XIANYU_ORDER_PAGE_SIZE = 30

    async def fetch_xianyu_orders(
        self,
        account,
        query_code: str = "ALL",
        max_pages: int | None = None,
    ) -> dict:
        """获取闲鱼卖家已售订单并同步到数据库（账号级加锁入口）

        通过 Redis 账号级互斥锁，保证同一账号同一时刻只有一个同步流程在
        拉取+落库，避免「定时获取闲鱼订单(ALL)」与「获取待发货订单(NOT_SHIP)」
        两个任务并发 upsert 同一订单。Redis 不可用时降级为无锁执行，
        由 xy_orders 的 (account_id, order_no) 唯一约束做最终兜底。

        Args:
            account: XYAccount 对象，需要 cookie / account_id / owner_id
            query_code: 闲鱼订单查询类型，"ALL"=全部订单，"NOT_SHIP"=待发货订单
            max_pages: 最大拉取页数；None 表示按 totalCount 翻页直到结束，
                       传入正整数则最多只拉该页数（如待发货任务只拉 1 页）

        Returns:
            { total_fetched, new_inserted, updated, failed, errors }
        """
        from common.db.redis_client import distributed_lock

        account_id = account.account_id
        lock_name = f"order_sync:{account_id}"
        try:
            async with distributed_lock(
                lock_name, expire=180, blocking=True, timeout=8
            ) as lock:
                if not lock.is_locked:
                    logger.info(
                        f"获取闲鱼订单: 账号 {account_id} 同步锁被占用，"
                        f"跳过本次（避免与其他同步任务并发）"
                    )
                    return {
                        'total_fetched': 0,
                        'new_inserted': 0,
                        'updated': 0,
                        'failed': 0,
                        'errors': ['账号同步锁被占用，已跳过'],
                    }
                return await self._fetch_xianyu_orders_impl(
                    account, query_code, max_pages
                )
        except Exception as e:
            # Redis 不可用等异常时降级为无锁执行，靠唯一约束兜底防止重复插入
            logger.warning(
                f"获取闲鱼订单: 账号 {account_id} 获取同步锁异常，"
                f"降级无锁执行（依赖唯一约束兜底）: {e}"
            )
            return await self._fetch_xianyu_orders_impl(
                account, query_code, max_pages
            )

    async def _fetch_xianyu_orders_impl(
        self,
        account,
        query_code: str = "ALL",
        max_pages: int | None = None,
    ) -> dict:
        """获取闲鱼卖家已售订单并同步到数据库（实际实现，调用方需已持有账号锁）
        
        Args:
            account: XYAccount 对象，需要 cookie / account_id / owner_id
            query_code: 闲鱼订单查询类型，"ALL"=全部订单，"NOT_SHIP"=待发货订单
            max_pages: 最大拉取页数；None 表示按 totalCount 翻页直到结束，
                       传入正整数则最多只拉该页数（如待发货任务只拉 1 页）
            
        Returns:
            { total_fetched, new_inserted, updated, failed, errors }
        """
        import asyncio
        
        cookies_str = account.cookie
        total_fetched = 0
        new_inserted = 0
        updated = 0
        failed = 0
        errors = []
        try:
            first_page_data = await self._fetch_sold_orders_page(
                cookies_str, 1, account_id=account.account_id, query_code=query_code
            )
        except Exception as e:
            errors.append(f"第1页请求失败: {str(e)}")
            logger.error(f"获取闲鱼订单第1页失败: {e}")
            return {
                'total_fetched': total_fetched,
                'new_inserted': new_inserted,
                'updated': updated,
                'failed': failed,
                'errors': errors,
            }

        if not first_page_data:
            errors.append("第1页返回空数据")
            return {
                'total_fetched': total_fetched,
                'new_inserted': new_inserted,
                'updated': updated,
                'failed': failed,
                'errors': errors,
            }

        if first_page_data.get('cookies_str') and first_page_data['cookies_str'] != cookies_str:
            cookies_str = first_page_data['cookies_str']
            logger.info("获取闲鱼订单: Cookie已通过Set-Cookie刷新，后续页使用最新Cookie")

        if first_page_data.get('error'):
            errors.append(first_page_data['error'])
            return {
                'total_fetched': total_fetched,
                'new_inserted': new_inserted,
                'updated': updated,
                'failed': failed,
                'errors': errors,
            }

        total_count = first_page_data.get('total_count', 0)
        total_pages = max(1, (total_count + self._XIANYU_ORDER_PAGE_SIZE - 1) // self._XIANYU_ORDER_PAGE_SIZE)
        # max_pages 限制最大拉取页数（如待发货任务只拉首页）
        if max_pages is not None and max_pages > 0:
            total_pages = min(total_pages, max_pages)
        logger.info(
            f"获取闲鱼订单: 账号 {account.account_id} 查询类型{query_code} "
            f"总数{total_count}, 预计共{total_pages}页"
        )

        for page in range(1, total_pages + 1):
            if page == 1:
                page_data = first_page_data
            else:
                try:
                    page_data = await self._fetch_sold_orders_page(
                        cookies_str, page, account_id=account.account_id, query_code=query_code
                    )
                except Exception as e:
                    errors.append(f"第{page}页请求失败: {str(e)}")
                    logger.error(f"获取闲鱼订单第{page}页失败: {e}")
                    break

                if not page_data:
                    errors.append(f"第{page}页返回空数据")
                    break

                if page_data.get('cookies_str') and page_data['cookies_str'] != cookies_str:
                    cookies_str = page_data['cookies_str']
                    logger.info("获取闲鱼订单: Cookie已通过Set-Cookie刷新，后续页使用最新Cookie")

                if page_data.get('error'):
                    errors.append(page_data['error'])
                    break

            items = page_data.get('items', [])
            next_page = page_data.get('next_page', False)

            if not items:
                logger.info(f"获取闲鱼订单: 第{page}/{total_pages}页无数据，结束获取")
                break

            parsed_items = []
            unique_order_nos = []
            seen_order_nos = set()
            page_parse_failed = 0

            for item in items:
                parsed = self._parse_sold_order_item(item)
                if not parsed or not parsed.get('order_no'):
                    failed += 1
                    page_parse_failed += 1
                    continue
                parsed_items.append(parsed)
                order_no = parsed['order_no']
                if order_no not in seen_order_nos:
                    seen_order_nos.add(order_no)
                    unique_order_nos.append(order_no)

            existing_orders_map = {}
            if unique_order_nos:
                existing_stmt = select(XYOrder).where(
                    XYOrder.account_id == account.account_id,
                    XYOrder.order_no.in_(unique_order_nos)
                )
                existing_result = await self.session.execute(existing_stmt)
                existing_orders_map = {
                    existing.order_no: existing
                    for existing in existing_result.scalars().all()
                }

            page_all_existing = (
                page_parse_failed == 0
                and bool(unique_order_nos)
                and len(existing_orders_map) == len(unique_order_nos)
            )

            page_updated = 0
            for parsed in parsed_items:
                try:
                    result = await self._upsert_order(
                        parsed,
                        account,
                        existing=existing_orders_map.get(parsed['order_no'])
                    )
                    total_fetched += 1
                    if result == 'inserted':
                        new_inserted += 1
                    elif result == 'updated':
                        updated += 1
                        page_updated += 1
                except Exception as e:
                    await self.session.rollback()
                    failed += 1
                    logger.error(f"处理订单异常: {e}")

            logger.info(
                f"获取闲鱼订单: 第{page}/{total_pages}页完成, 本页{len(items)}条, "
                f"累计{total_fetched}条, 总数{total_count}, 全页已存在={page_all_existing}"
            )

            # 仅当本页全部订单已存在且无状态变更时才停止翻页；
            # 若有订单被更新（如退款导致状态变更），需继续翻页以免遗漏更早订单的状态变化。
            if page_all_existing and page_updated == 0:
                logger.info(f"获取闲鱼订单: 第{page}页订单已全部存在且无状态变更，停止继续获取更早页")
                break

            if not next_page or page >= total_pages:
                break

            await asyncio.sleep(1.5)

        return {
            'total_fetched': total_fetched,
            'new_inserted': new_inserted,
            'updated': updated,
            'failed': failed,
            'errors': errors,
        }

    async def _fetch_sold_orders_page(
        self, cookies_str: str, page: int,
        account_id: str = None, is_retry: bool = False,
        query_code: str = "ALL",
    ) -> Optional[dict]:
        """获取闲鱼卖家已售订单的单页数据
        
        支持令牌过期自动刷新Cookie并重试一次
        
        Args:
            cookies_str: Cookie字符串
            page: 页码（从1开始）
            account_id: 账号ID，用于令牌过期时更新数据库Cookie（可选）
            is_retry: 是否为令牌过期后的重试请求
            query_code: 查询类型，"ALL"=全部，"NOT_SHIP"=待发货
            
        Returns:
            { items, next_page, total_count, error }
        """
        import json
        import time
        import aiohttp
        from common.utils.xianyu_utils import trans_cookies, generate_sign
        from common.utils.cookie_refresh import (
            is_token_expired_error, handle_token_expired_response,
            update_account_cookies_in_db,
            is_session_expired_error, trigger_password_login_async,
            mark_account_session_expired
        )
        
        cookies = trans_cookies(cookies_str)
        timestamp = str(int(time.time() * 1000))
        data_val = json.dumps({
            "pageNumber": page,
            "rowsPerPage": self._XIANYU_ORDER_PAGE_SIZE,
            "orderIds": "",
            "queryCode": query_code,
            "orderSearchParam": "{}"
        }, separators=(',', ':'))
        
        token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
        sign = generate_sign(timestamp, token, data_val)
        
        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': timestamp,
            'sign': sign,
            'v': '1.0',
            'type': 'json',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idle.trade.merchant.sold.get',
            'valueType': 'string',
            'sessionOption': 'AutoLoginOnly',
        }
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'idle_site_biz_code': 'COMMONPRO',
            'cookie': cookies_str,
            'Referer': 'https://seller.goofish.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://h5api.m.goofish.com/h5/mtop.taobao.idle.trade.merchant.sold.get/1.0/',
                params=params,
                data={'data': data_val},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                res_json = await response.json()
                
                ret = res_json.get('ret', [])
                ret_str = ret[0] if ret else ''
                retry_tag = '[令牌过期重试] ' if is_retry else ''
                
                if 'SUCCESS' not in ret_str:
                    # 检测令牌过期，尝试刷新Cookie并重试
                    if not is_retry and is_token_expired_error(ret):
                        logger.warning(
                            f"账号 {account_id or '未知账号'} 获取闲鱼订单列表第{page}页令牌过期，"
                            f"接口返回: ret={ret}，准备刷新Cookie后重试"
                        )
                        has_new, new_cookies_str = handle_token_expired_response(
                            response, cookies_str
                        )
                        if has_new:
                            if account_id:
                                await update_account_cookies_in_db(account_id, new_cookies_str)
                            # 用新Cookie重试，并将最新Cookie传递给调用方
                            retry_result = await self._fetch_sold_orders_page(
                                new_cookies_str, page, account_id, is_retry=True,
                                query_code=query_code
                            )
                            if retry_result and 'cookies_str' not in retry_result:
                                retry_result['cookies_str'] = new_cookies_str
                            return retry_result
                        else:
                            logger.warning(f"账号 {account_id or '未知账号'} 获取闲鱼订单列表第{page}页令牌过期，但响应中没有Set-Cookie，无法重试")
                    
                    # 检测Session过期，标记账号冷却并触发后台异步密码登录（不阻塞、不重试）
                    if is_session_expired_error(ret):
                        logger.warning(
                            f"账号 {account_id or '未知账号'} 获取闲鱼订单列表第{page}页Session过期，"
                            f"接口返回: ret={ret}，触发后台异步密码登录"
                        )
                        if account_id:
                            mark_account_session_expired(account_id)
                            trigger_password_login_async(account_id)
                    
                    error_msg = ret_str or '未知错误'
                    logger.warning(
                        f"账号 {account_id or '未知账号'} {retry_tag}获取闲鱼订单列表第{page}页失败: "
                        f"ret={ret}, response={res_json}"
                    )
                    return {'items': [], 'next_page': False, 'total_count': 0, 'error': error_msg}
                
                # 成功时也打印返回值摘要
                logger.info(f"账号 {account_id or '未知账号'} {retry_tag}获取闲鱼订单列表第{page}页成功: ret={ret_str}")
        
        module = res_json.get('data', {}).get('module', {})
        items = module.get('items', [])
        next_page = module.get('nextPage', 'false') == 'true'
        total_count = int(module.get('totalCount', '0'))
        
        return {
            'items': items,
            'next_page': next_page,
            'total_count': total_count,
            'cookies_str': cookies_str,
        }

    def _parse_sold_order_item(self, item: dict) -> Optional[dict]:
        """解析闲鱼卖家订单列表中的单条订单
        
        Args:
            item: API返回的单条订单数据
            
        Returns:
            解析后的订单字典
        """
        from decimal import Decimal
        from datetime import datetime
        
        common = item.get('commonData', {})
        buyer_info = item.get('buyerInfoVO', {})
        price_vo = item.get('priceVO', {})
        right_vo = item.get('rightVO', {})
        
        order_no = common.get('orderId', '')
        if not order_no:
            return None
        
        # 状态映射
        raw_status = common.get('orderStatus', '')
        # 退款中特殊处理
        if common.get('inRefund') == 'true':
            status = 'refunding'
        else:
            status = self._XIANYU_STATUS_MAP.get(raw_status, 'unknown')
        
        # 小刀判断：btnList中存在tradeAction=SKIP_PIN
        is_bargain = False
        btn_list = right_vo.get('btnList', [])
        for btn in btn_list:
            if btn.get('tradeAction') == 'SKIP_PIN':
                is_bargain = True
                break
        
        # 评价状态
        seller_rate_status = common.get('sellerRateStatus', '')
        is_rated = seller_rate_status == '4'
        
        # 金额
        total_price = price_vo.get('totalPrice', '0')
        try:
            amount = Decimal(total_price)
        except Exception:
            amount = None
        
        # 数量
        try:
            quantity = int(price_vo.get('buyNum', '1'))
        except (ValueError, TypeError):
            quantity = 1
        
        # 下单时间
        placed_at = None
        create_time_str = common.get('createTime', '')
        if create_time_str:
            try:
                placed_at = datetime.strptime(create_time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        
        return {
            'order_no': order_no,
            'status': status,
            'item_id': common.get('itemId', ''),
            'buyer_id': buyer_info.get('buyerId', ''),
            'buyer_nick': buyer_info.get('userNick', ''),
            'receiver_name': buyer_info.get('name', ''),
            'receiver_phone': buyer_info.get('phone', ''),
            'receiver_address': buyer_info.get('address', ''),
            'amount': amount,
            'quantity': quantity,
            'is_bargain': is_bargain,
            'is_rated': is_rated,
            'placed_at': placed_at,
        }

    async def _upsert_order(self, parsed: dict, account, existing: XYOrder | None = None) -> str:
        """比对并插入或更新订单
        
        Args:
            parsed: 解析后的订单字典
            account: XYAccount 对象
            
        Returns:
            'inserted' / 'updated' / 'skipped'
        """
        order_no = parsed['order_no']

        if existing is None:
            stmt = select(XYOrder).where(
                XYOrder.order_no == order_no,
                XYOrder.account_id == account.account_id
            )
            result = await self.session.execute(stmt)
            existing = result.scalars().first()

        if existing:
            update_values = {}
            # 始终更新状态
            if parsed.get('status') and parsed['status'] != (existing.status or ''):
                update_values['status'] = parsed['status']
            # 补充缺失数据
            if parsed.get('buyer_id') and not existing.buyer_id:
                update_values['buyer_id'] = parsed['buyer_id']
            if parsed.get('buyer_nick') and not existing.buyer_nick:
                update_values['buyer_nick'] = parsed['buyer_nick']
            if parsed.get('item_id') and not existing.item_id:
                update_values['item_id'] = parsed['item_id']
            if parsed.get('amount') is not None and not existing.amount:
                update_values['amount'] = parsed['amount']
            # quantity 同步策略：
            # 旧条件 `not existing.quantity or existing.quantity == 0` 在 existing.quantity=1
            # （Integer 列默认值）时永远为 False，导致一旦订单首次写入就不再同步 quantity，
            # 后续买家改件数（1→2）/ 同步路径首次写入用了默认值 1 等场景都无法纠正。
            # 改为：parsed quantity 解析为正整数且与 DB 现值不同就覆盖，让后续同步能纠正。
            if parsed.get('quantity'):
                try:
                    parsed_qty = int(parsed['quantity'])
                except (TypeError, ValueError):
                    parsed_qty = 0
                if parsed_qty > 0 and parsed_qty != (existing.quantity or 0):
                    update_values['quantity'] = parsed_qty
            # 收货人信息：有新数据且非空时更新
            if parsed.get('receiver_name') and not existing.receiver_name:
                update_values['receiver_name'] = parsed['receiver_name']
            if parsed.get('receiver_phone') and not existing.receiver_phone:
                update_values['receiver_phone'] = parsed['receiver_phone']
            if parsed.get('receiver_address') and not existing.receiver_address:
                update_values['receiver_address'] = parsed['receiver_address']
            # 小刀标记：只标记为True不回退
            if parsed.get('is_bargain') and not existing.is_bargain:
                update_values['is_bargain'] = True
            # 评价状态：始终更新
            if parsed.get('is_rated') != existing.is_rated:
                update_values['is_rated'] = parsed['is_rated']
            # 下单时间
            if parsed.get('placed_at') and not existing.placed_at:
                update_values['placed_at'] = parsed['placed_at']
            
            if update_values:
                update_stmt = (
                    update(XYOrder)
                    .where(XYOrder.id == existing.id)
                    .values(**update_values)
                )
                await self.session.execute(update_stmt)
                await self.session.commit()
                return 'updated'
            return 'skipped'
        else:
            new_order = XYOrder(
                owner_id=account.owner_id,
                account_id=account.account_id,
                order_no=order_no,
                status=parsed.get('status', 'unknown'),
                item_id=parsed.get('item_id', ''),
                buyer_id=parsed.get('buyer_id', ''),
                buyer_nick=parsed.get('buyer_nick', ''),
                receiver_name=parsed.get('receiver_name', ''),
                receiver_phone=parsed.get('receiver_phone', ''),
                receiver_address=parsed.get('receiver_address', ''),
                amount=parsed.get('amount'),
                quantity=parsed.get('quantity', 1),
                is_bargain=parsed.get('is_bargain', False),
                is_rated=parsed.get('is_rated', False),
                placed_at=parsed.get('placed_at'),
                source='fetch_xianyu',
            )
            self.session.add(new_order)
            try:
                await self.session.commit()
                return 'inserted'
            except IntegrityError:
                # 并发兜底：(account_id, order_no) 唯一约束命中，说明另一个任务
                # （如定时获取闲鱼订单 / 获取待发货订单）已抢先插入同一订单。
                # 回滚后改走更新分支，避免重复插入，也保证收货信息得到补充。
                await self.session.rollback()
                logger.info(
                    f"订单 {order_no} 并发插入命中唯一约束，转为更新已存在记录"
                )
                stmt = select(XYOrder).where(
                    XYOrder.order_no == order_no,
                    XYOrder.account_id == account.account_id
                )
                result = await self.session.execute(stmt)
                concurrent_existing = result.scalars().first()
                if concurrent_existing is None:
                    # 理论上不会发生（唯一约束刚命中），保守跳过
                    logger.warning(
                        f"订单 {order_no} 唯一约束命中但未查到已存在记录，跳过"
                    )
                    return 'skipped'
                return await self._upsert_order(parsed, account, existing=concurrent_existing)


class OrderDetailService:
    """订单详情服务 - 用于异步获取和更新订单详情信息
    
    功能：
    1. 通过API获取订单详情（规格、数量、收货人等）
    2. 更新订单信息到数据库
    """
    
    def __init__(self, cookie_id: str, cookies_str: str):
        """初始化订单详情服务
        
        Args:
            cookie_id: 账号ID
            cookies_str: Cookie字符串
        """
        self.cookie_id = cookie_id
        # 清洗 cookies_str 中的换行符，防止 header injection
        self.cookies_str = (cookies_str or "").replace("\r", "").replace("\n", "")
    
    async def fetch_and_update_order_detail(
        self,
        order_id: str,
        item_id: str = None,
        buyer_id: str = None
    ) -> bool:
        """获取订单详情并更新到数据库
        
        Args:
            order_id: 订单ID
            item_id: 商品ID（可选，用于更新）
            buyer_id: 买家ID（可选，用于更新）
            
        Returns:
            是否成功
        """
        try:
            from datetime import datetime
            from common.db.session import async_session_maker
            
            # 获取订单详情
            detail = await self._fetch_order_detail(order_id)
            api_failed = detail is None
            
            async with async_session_maker() as session:
                # 查询现有订单
                stmt = select(XYOrder).where(XYOrder.order_no == order_id)
                result = await session.execute(stmt)
                existing_order = result.scalars().first()
                
                if not existing_order:
                    logger.warning(f"【{self.cookie_id}】订单 {order_id} 不存在，无法更新")
                    return False
                
                # 构建更新字段
                update_values = {}
                
                # 更新item_id和buyer_id（如果数据库中为空）
                if item_id and not existing_order.item_id:
                    update_values['item_id'] = item_id
                if buyer_id and not existing_order.buyer_id:
                    update_values['buyer_id'] = buyer_id
                
                # 从API详情中补充item_id和buyer_id（如果参数未传入且数据库中为空）
                if detail:
                    if detail.get('item_id') and not existing_order.item_id and 'item_id' not in update_values:
                        update_values['item_id'] = detail['item_id']
                    if detail.get('buyer_id') and not existing_order.buyer_id and 'buyer_id' not in update_values:
                        update_values['buyer_id'] = detail['buyer_id']
                    # 从API状态节点中检测小刀订单
                    if detail.get('is_bargain') and not existing_order.is_bargain:
                        update_values['is_bargain'] = True
                
                # 更新从API获取的详情
                if detail:
                    if detail.get('spec_name'):
                        update_values['spec_name'] = detail['spec_name']
                    if detail.get('spec_value'):
                        update_values['spec_value'] = detail['spec_value']
                    if detail.get('amount'):
                        update_values['amount'] = detail['amount']
                    if detail.get('quantity'):
                        update_values['quantity'] = detail['quantity']
                    
                    # 下单时间：如果API返回了时间且数据库中为空，则更新
                    placed_at_str = detail.get('placed_at_str', '')
                    if placed_at_str and not existing_order.placed_at:
                        try:
                            placed_at = datetime.strptime(placed_at_str, '%Y-%m-%d %H:%M:%S')
                            update_values['placed_at'] = placed_at
                        except ValueError:
                            logger.warning(f"【{self.cookie_id}】订单 {order_id} 下单时间格式不匹配: {placed_at_str}")
                    
                    # 收货人信息：如果新获取的不为空，且（数据库为空 或 数据库中包含脱敏字符*），则更新
                    if self._should_update_receiver_field(detail.get('receiver_name', ''), existing_order.receiver_name):
                        update_values['receiver_name'] = detail['receiver_name']
                    if self._should_update_receiver_field(detail.get('receiver_phone', ''), existing_order.receiver_phone):
                        update_values['receiver_phone'] = detail['receiver_phone']
                    if self._should_update_receiver_field(detail.get('receiver_address', ''), existing_order.receiver_address):
                        update_values['receiver_address'] = detail['receiver_address']
                
                if update_values:
                    stmt = update(XYOrder).where(XYOrder.order_no == order_id).values(**update_values)
                    await session.execute(stmt)
                    await session.commit()
                    if api_failed:
                        logger.warning(f"【{self.cookie_id}】订单 {order_id} API获取详情失败，仅通过参数更新了: {list(update_values.keys())}")
                    else:
                        logger.info(f"【{self.cookie_id}】订单 {order_id} 信息已更新: {list(update_values.keys())}")
                    return True
                else:
                    if api_failed:
                        logger.warning(f"【{self.cookie_id}】订单 {order_id} API获取详情失败，且无可更新字段（请查看上方API调用失败日志）")
                        return False
                    logger.info(f"【{self.cookie_id}】订单 {order_id} 无需更新")
                    return True
                    
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取并更新订单详情失败: {e}")
            return False
    
    def _should_update_receiver_field(self, new_value: str, old_value: str) -> bool:
        """判断是否需要更新收货人字段
        
        Args:
            new_value: 新值
            old_value: 旧值
            
        Returns:
            是否需要更新
        """
        if not new_value:
            return False
        if not old_value:
            return True
        # 如果旧值包含脱敏字符，且新值不包含，则更新
        if '*' in old_value and '*' not in new_value:
            return True
        return False
    
    async def _fetch_order_detail(self, order_id: str, retry_count: int = 0) -> Optional[Dict]:
        """通过API获取订单详情
        
        参照发货服务的模式：每次请求后存储set-cookie，令牌过期时用新cookie重试
        
        Args:
            order_id: 订单ID
            retry_count: 当前重试次数
            
        Returns:
            订单详情字典，包含spec_name, spec_value, amount, quantity, receiver_name等
        """
        max_retry = 3
        
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
                'cookie': self.cookies_str,
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
                    
                    # 处理响应中的set-cookie，更新本地cookie并写入数据库
                    await self._handle_response_cookies(response)
                    
                    # 打印API返回结果用于分析
                    logger.info(f"【{self.cookie_id}】订单 {order_id} API返回: ret={res_json.get('ret', [])}")
                    
                    # 检查响应是否成功
                    ret_list = res_json.get('ret', [])
                    if not any('SUCCESS' in ret for ret in ret_list):
                        # 打印详细的失败原因
                        ret_str = ', '.join(ret_list) if ret_list else '无返回信息'
                        logger.warning(f"【{self.cookie_id}】订单 {order_id} API调用失败: {ret_str}")
                        
                        # 令牌过期时，用更新后的cookie重试
                        from common.utils.cookie_refresh import is_token_expired_error
                        if is_token_expired_error(ret_list):
                            if retry_count < max_retry - 1:
                                logger.info(f"【{self.cookie_id}】订单 {order_id} 令牌过期，已更新Cookie，准备重试({retry_count + 1}/{max_retry - 1})...")
                                await asyncio.sleep(0.5)
                                return await self._fetch_order_detail(order_id, retry_count + 1)
                        
                        return None
                    
                    # 解析返回数据
                    return self._parse_order_detail_response(order_id, res_json)
                    
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取订单详情异常: {type(e).__name__}: {e}")
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self._fetch_order_detail(order_id, retry_count + 1)
            return None
    
    async def _handle_response_cookies(self, response) -> None:
        """处理响应中的set-cookie，更新本地cookie并写入数据库
        
        令牌过期时服务端会在响应头中返回新的cookie（包含新的_m_h5_tk），
        存储后重试请求即可使用新的token签名
        
        Args:
            response: HTTP响应对象
        """
        try:
            from common.utils.cookie_refresh import (
                extract_cookies_from_response, merge_cookies,
                update_account_cookies_in_db
            )
            
            new_cookies = extract_cookies_from_response(response)
            if new_cookies:
                self.cookies_str = merge_cookies(self.cookies_str, new_cookies)
                # 写入数据库
                await update_account_cookies_in_db(self.cookie_id, self.cookies_str)
                logger.info(
                    f"【{self.cookie_id}】已从响应中合并 {len(new_cookies)} 个Cookie字段并更新到数据库"
                )
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】处理响应Cookie失败: {e}")
    
    def _parse_order_detail_response(self, order_id: str, res_json: dict) -> Optional[Dict]:
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
                'item_id': '',
                'buyer_id': '',
                'spec_name': '',
                'spec_value': '',
                'quantity': '1',
                'amount': '',
                'receiver_name': '',
                'receiver_phone': '',
                'receiver_address': '',
                'is_bargain': False,
            }
            
            # 从顶层data中提取buyer_id和item_id（作为兜底）
            top_peer_user_id = data.get('peerUserId', '')
            top_item_id = data.get('itemId', '')
            if top_peer_user_id:
                result['buyer_id'] = str(top_peer_user_id)
            if top_item_id:
                result['item_id'] = str(top_item_id)
            
            for component in components:
                render_type = component.get('render', '')
                comp_data = component.get('data', {})
                
                # 解析订单信息（包含商品信息）
                if render_type == 'orderInfoVO':
                    logger.info(f"【{self.cookie_id}】订单 {order_id} orderInfoVO keys: {list(comp_data.keys())}")
                    item_info = comp_data.get('itemInfo', {})
                    logger.info(f"【{self.cookie_id}】订单 {order_id} itemInfo keys: {list(item_info.keys())}")
                    
                    # 从orderInfoList中提取下单时间
                    order_info_list = comp_data.get('orderInfoList', [])
                    if order_info_list:
                        logger.info(f"【{self.cookie_id}】订单 {order_id} orderInfoList: {order_info_list}")
                        for info_item in order_info_list:
                            label = info_item.get('label', '') or info_item.get('key', '') or info_item.get('name', '')
                            value = info_item.get('value', '') or info_item.get('text', '')
                            if '时间' in label or 'time' in label.lower() or 'Time' in label:
                                result['placed_at_str'] = value
                                logger.info(f"【{self.cookie_id}】订单 {order_id} 提取到下单时间: {value}")
                    
                    # 获取商品ID
                    api_item_id = item_info.get('itemId', '') or comp_data.get('itemId', '')
                    if api_item_id:
                        result['item_id'] = str(api_item_id)
                    
                    # 获取买家ID
                    api_buyer_id = comp_data.get('buyerUserId', '') or comp_data.get('buyerId', '')
                    if api_buyer_id:
                        result['buyer_id'] = str(api_buyer_id)
                    
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
                
                # 解析收货地址信息
                elif render_type == 'addressInfoVO':
                    result['receiver_name'] = comp_data.get('name', '')
                    result['receiver_phone'] = comp_data.get('phoneNumber', '')
                    result['receiver_address'] = comp_data.get('address', '')
                
                # 解析订单状态，检测小刀订单
                elif render_type == 'orderStatusVO':
                    status_nodes = comp_data.get('orderStatusNodeList', [])
                    for node in status_nodes:
                        node_title = node.get('title', '')
                        if node_title in ('已刀成', '待刀成'):
                            result['is_bargain'] = True
                            break
            
            logger.info(f"【{self.cookie_id}】订单 {order_id} 详情解析成功: item_id={result['item_id']}, buyer_id={result['buyer_id']}, 价格={result['amount']}, 规格={result['spec_name']}:{result['spec_value']}, 小刀={result['is_bargain']}")
            return result
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】订单 {order_id} 解析API响应失败: {e}")
            return None


class OrderStatusChecker:
    """订单状态检查服务
    
    功能：
    1. check_can_ship - 检查订单是否可以发货
    2. check_can_rate - 检查订单是否可以评价
    
    通过调用闲鱼API获取订单状态节点，分析是否满足发货/评价条件
    支持令牌过期自动刷新Cookie并重试
    """
    
    def __init__(self, cookies_str: str, account_id: str = None):
        """初始化订单状态检查服务
        
        Args:
            cookies_str: Cookie字符串
            account_id: 账号ID，用于令牌过期时更新数据库Cookie（可选）
        """
        # 清洗 cookies_str 中的换行符，防止 header injection
        self.cookies_str = (cookies_str or "").replace("\r", "").replace("\n", "")
        self.account_id = account_id
    
    async def check_can_ship(self, order_id: str) -> Dict:
        """检查订单是否可以发货
        
        判断逻辑：
        - 已付款 + 待发货状态 → 可以发货
        - 小刀订单：已付款 + (已刀成/待发货) → 可以发货
        
        Args:
            order_id: 订单号
            
        Returns:
            {
                'success': bool,  # 请求是否成功
                'can_ship': bool,  # 是否可以发货
                'reason': str,  # 原因说明
                'order_status': str  # 当前订单状态描述
            }
        """
        try:
            # 获取原始API响应
            raw_response = await self._fetch_raw_order_detail(order_id)
            if not raw_response:
                return {
                    'success': False,
                    'can_ship': False,
                    'reason': '无法获取订单状态信息',
                    'order_status': '未知'
                }
            
            # 解析订单状态节点
            status_nodes = self._extract_order_status_nodes(raw_response)
            
            # 如果状态节点为空，尝试从 orderStatusInfo 获取状态
            if not status_nodes:
                order_status_title = self._extract_order_status_title(raw_response)
                if order_status_title:
                    if '交易关闭' in order_status_title:
                        await self._update_order_status_to_cancelled(order_id)
                        return {
                            'success': True,
                            'can_ship': False,
                            'reason': '订单已关闭',
                            'order_status': order_status_title
                        }
                    elif '交易成功' in order_status_title:
                        return {
                            'success': True,
                            'can_ship': False,
                            'reason': '订单已交易成功',
                            'order_status': order_status_title
                        }
                
                return {
                    'success': False,
                    'can_ship': False,
                    'reason': '订单状态节点解析失败',
                    'order_status': '未知'
                }
            
            # 分析订单状态
            can_ship, reason, order_status = self._analyze_can_ship(status_nodes)
            
            return {
                'success': True,
                'can_ship': can_ship,
                'reason': reason,
                'order_status': order_status
            }
            
        except Exception as e:
            logger.error(f"检查订单 {order_id} 是否可发货失败: {e}")
            return {
                'success': False,
                'can_ship': False,
                'reason': f'检查失败: {str(e)}',
                'order_status': '未知'
            }
    
    async def check_can_rate(self, order_id: str) -> Dict:
        """检查订单是否可以评价
        
        判断逻辑：
        - 交易成功 + 待评价状态 → 可以评价
        
        Args:
            order_id: 订单号
            
        Returns:
            {
                'success': bool,  # 请求是否成功
                'can_rate': bool,  # 是否可以评价
                'reason': str,  # 原因说明
                'order_status': str  # 当前订单状态描述
            }
        """
        try:
            # 获取原始API响应
            raw_response = await self._fetch_raw_order_detail(order_id)
            if not raw_response:
                return {
                    'success': False,
                    'can_rate': False,
                    'reason': '无法获取订单状态信息',
                    'order_status': '未知'
                }
            
            # 解析订单状态节点
            status_nodes = self._extract_order_status_nodes(raw_response)
            
            # 如果状态节点为空，尝试从 orderStatusInfo 获取状态
            if not status_nodes:
                order_status_title = self._extract_order_status_title(raw_response)
                if order_status_title:
                    if '交易关闭' in order_status_title:
                        await self._update_order_status_to_cancelled(order_id)
                        return {
                            'success': True,
                            'can_rate': False,
                            'reason': '订单已关闭',
                            'order_status': order_status_title
                        }
                    elif '交易成功' in order_status_title:
                        return {
                            'success': True,
                            'can_rate': False,
                            'reason': '订单已交易成功，但无法确定是否可评价',
                            'order_status': order_status_title
                        }
                
                return {
                    'success': False,
                    'can_rate': False,
                    'reason': '订单状态节点解析失败',
                    'order_status': '未知'
                }
            
            # 分析订单状态
            can_rate, reason, order_status = self._analyze_can_rate(status_nodes)
            
            return {
                'success': True,
                'can_rate': can_rate,
                'reason': reason,
                'order_status': order_status
            }
            
        except Exception as e:
            logger.error(f"检查订单 {order_id} 是否可评价失败: {e}")
            return {
                'success': False,
                'can_rate': False,
                'reason': f'检查失败: {str(e)}',
                'order_status': '未知'
            }
    
    async def _fetch_raw_order_detail(self, order_id: str, is_retry: bool = False) -> Optional[Dict]:
        """获取订单详情的原始API响应
        
        支持令牌过期自动刷新Cookie并重试一次
        
        Args:
            order_id: 订单号
            is_retry: 是否为令牌过期后的重试请求
            
        Returns:
            原始API响应JSON，失败返回None
        """
        try:
            import json
            import time
            import aiohttp
            from common.utils.xianyu_utils import trans_cookies, generate_sign
            from common.utils.cookie_refresh import (
                is_token_expired_error, handle_token_expired_response,
                update_account_cookies_in_db,
                is_session_expired_error, trigger_password_login_async,
                mark_account_session_expired
            )
            
            cookies = trans_cookies(self.cookies_str)
            timestamp = str(int(time.time() * 1000))
            data_val = json.dumps({"tid": order_id}, separators=(',', ':'))
            
            token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
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
                'cookie': self.cookies_str,
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
                    
                    ret_list = res_json.get('ret', [])
                    retry_tag = '[令牌过期重试] ' if is_retry else ''
                    
                    if not any('SUCCESS' in ret for ret in ret_list):
                        # 检测令牌过期，尝试刷新Cookie并重试
                        if not is_retry and is_token_expired_error(ret_list):
                            logger.warning(
                                f"账号 {self.account_id or '未知账号'} 订单 {order_id} 查询详情令牌过期，"
                                f"接口返回: ret={ret_list}，准备刷新Cookie后重试"
                            )
                            has_new, new_cookies_str = handle_token_expired_response(
                                response, self.cookies_str
                            )
                            if has_new:
                                # 更新数据库
                                if self.account_id:
                                    await update_account_cookies_in_db(self.account_id, new_cookies_str)
                                # 更新本地Cookie并重试
                                self.cookies_str = new_cookies_str
                                return await self._fetch_raw_order_detail(order_id, is_retry=True)
                            else:
                                logger.warning(f"账号 {self.account_id or '未知账号'} 订单 {order_id} 查询详情令牌过期，但响应中没有Set-Cookie，无法重试")
                        
                        # 检测Session过期，标记账号冷却并触发后台异步密码登录（不阻塞、不重试）
                        if is_session_expired_error(ret_list):
                            logger.warning(
                                f"账号 {self.account_id or '未知账号'} 订单 {order_id} 查询详情Session过期，"
                                f"接口返回: ret={ret_list}，触发后台异步密码登录"
                            )
                            if self.account_id:
                                mark_account_session_expired(self.account_id)
                                trigger_password_login_async(self.account_id)
                        
                        logger.warning(
                            f"账号 {self.account_id or '未知账号'} {retry_tag}订单 {order_id} 查询详情API失败: "
                            f"ret={ret_list}, response={res_json}"
                        )
                        return None
                    
                    # 成功时也打印返回值摘要
                    logger.info(f"账号 {self.account_id or '未知账号'} {retry_tag}订单 {order_id} 查询详情API成功: ret={ret_list}")
                    return res_json
                    
        except Exception as e:
            logger.error(f"账号 {self.account_id or '未知账号'} 获取订单 {order_id} 原始详情失败: {e}")
            return None
    
    def _extract_order_status_nodes(self, raw_response: Dict) -> Optional[list]:
        """从原始API响应中提取订单状态节点列表
        
        Args:
            raw_response: 原始API响应
            
        Returns:
            订单状态节点列表
        """
        try:
            data = raw_response.get('data', {})
            components = data.get('components', [])
            
            for component in components:
                render_type = component.get('render', '')
                if render_type == 'orderStatusVO':
                    comp_data = component.get('data', {})
                    status_nodes = comp_data.get('orderStatusNodeList', [])
                    if status_nodes:
                        return status_nodes
                    else:
                        logger.debug(f"orderStatusNodeList 为空，将尝试从 orderStatusInfo.title 获取状态")
                        return None
            
            return None
            
        except Exception as e:
            logger.error(f"提取订单状态节点异常: {e}")
            return None
    
    def _extract_order_status_title(self, raw_response: Dict) -> Optional[str]:
        """从原始API响应中提取订单状态标题
        
        Args:
            raw_response: 原始API响应
            
        Returns:
            订单状态标题
        """
        try:
            data = raw_response.get('data', {})
            components = data.get('components', [])
            
            for component in components:
                render_type = component.get('render', '')
                if render_type == 'orderStatusVO':
                    comp_data = component.get('data', {})
                    order_status_info = comp_data.get('orderStatusInfo', {})
                    title = order_status_info.get('title', '')
                    if title:
                        logger.info(f"从 orderStatusInfo 提取到状态标题: {title}")
                        return title
            
            return None
            
        except Exception as e:
            logger.error(f"提取订单状态标题异常: {e}")
            return None
    
    async def _update_order_status_to_cancelled(self, order_id: str) -> None:
        """更新订单状态为已关闭
        
        Args:
            order_id: 订单号
        """
        try:
            from common.db.session import async_session_maker
            
            async with async_session_maker() as session:
                stmt = update(XYOrder).where(XYOrder.order_no == order_id).values(status="cancelled")
                await session.execute(stmt)
                await session.commit()
                logger.info(f"订单 {order_id} 状态已更新为 cancelled（交易关闭）")
        except Exception as e:
            logger.error(f"更新订单 {order_id} 状态失败: {e}")
    
    def _analyze_can_ship(self, status_nodes: list) -> tuple:
        """分析订单状态节点，判断是否可以发货
        
        可发货条件：
        1. 普通订单：已付款(completed=True) + 待发货(completed=False)
        2. 小刀订单：已付款(completed=True) + 已刀成/待发货(任意状态) + 待收货(completed=False)
        
        Args:
            status_nodes: 订单状态节点列表
            
        Returns:
            (can_ship: bool, reason: str, order_status: str)
        """
        # 构建状态映射
        status_map = {}
        for node in status_nodes:
            title = node.get('title', '')
            completed = node.get('completed', False)
            status_map[title] = completed
        
        # 获取当前订单状态描述
        current_status_parts = []
        for node in status_nodes:
            title = node.get('title', '')
            completed = node.get('completed', False)
            if completed:
                current_status_parts.append(title)
        order_status = ' → '.join(current_status_parts) if current_status_parts else '未知'
        
        # 检查是否已付款
        is_paid = status_map.get('已付款', False)
        if not is_paid:
            return False, '订单未付款', order_status
        
        # 检查是否已发货
        is_shipped = status_map.get('已发货', False)
        if is_shipped:
            return False, '订单已发货', order_status
        
        # 检查是否交易成功/已完成
        is_success = status_map.get('交易成功', False)
        if is_success:
            return False, '订单已交易成功', order_status
        
        # 检查是否待发货状态
        has_pending_ship = '待发货' in status_map
        has_bargain_done = '已刀成' in status_map  # 小刀订单特有状态
        has_bargain_pending = '待刀成' in status_map  # 小刀订单等待刀成
        
        if has_bargain_pending and not status_map.get('待刀成', False):
            # 小刀订单还在等待刀成
            return False, '小刀订单等待刀成', order_status
        
        if has_pending_ship or has_bargain_done:
            # 已付款且处于待发货状态
            return True, '订单已付款，可以发货', order_status
        
        return False, '订单状态不满足发货条件', order_status
    
    def _analyze_can_rate(self, status_nodes: list) -> tuple:
        """分析订单状态节点，判断是否可以评价
        
        可评价条件：
        - 交易成功(completed=True) + 待评价(completed=False)
        
        Args:
            status_nodes: 订单状态节点列表
            
        Returns:
            (can_rate: bool, reason: str, order_status: str)
        """
        # 构建状态映射
        status_map = {}
        for node in status_nodes:
            title = node.get('title', '')
            completed = node.get('completed', False)
            status_map[title] = completed
        
        # 获取当前订单状态描述
        current_status_parts = []
        for node in status_nodes:
            title = node.get('title', '')
            completed = node.get('completed', False)
            if completed:
                current_status_parts.append(title)
        order_status = ' → '.join(current_status_parts) if current_status_parts else '未知'
        
        # 检查是否交易成功
        is_success = status_map.get('交易成功', False)
        if not is_success:
            return False, '订单未交易成功', order_status
        
        # 检查是否已评价
        is_rated = status_map.get('已评价', False)
        if is_rated:
            return False, '订单已评价', order_status
        
        # 检查是否待评价状态
        has_pending_rate = '待评价' in status_map
        is_pending_rate_completed = status_map.get('待评价', False)
        
        if has_pending_rate and not is_pending_rate_completed:
            # 交易成功且处于待评价状态
            return True, '订单已交易成功，可以评价', order_status
        
        return False, '订单状态不满足评价条件', order_status


# 便捷函数
async def check_can_ship(order_id: str, cookie_string: str, account_id: str = None) -> Dict:
    """检查订单是否可以发货（便捷函数）
    
    Args:
        order_id: 订单号
        cookie_string: Cookie字符串
        account_id: 账号ID，用于令牌过期时更新数据库Cookie（可选）
        
    Returns:
        检查结果字典
    """
    checker = OrderStatusChecker(cookie_string, account_id)
    result = await checker.check_can_ship(order_id)
    # 将更新后的cookies字符串附加到结果中，方便调用方同步
    result['cookies_str'] = checker.cookies_str
    return result


async def check_can_rate(order_id: str, cookie_string: str, account_id: str = None) -> Dict:
    """检查订单是否可以评价（便捷函数）
    
    Args:
        order_id: 订单号
        cookie_string: Cookie字符串
        account_id: 账号ID，用于令牌过期时更新数据库Cookie（可选）
        
    Returns:
        检查结果字典
    """
    checker = OrderStatusChecker(cookie_string, account_id)
    result = await checker.check_can_rate(order_id)
    # 将更新后的cookies字符串附加到结果中，方便调用方同步
    result['cookies_str'] = checker.cookies_str
    return result
