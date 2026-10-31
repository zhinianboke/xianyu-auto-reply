"""广告订单查询与支付时效，统一保护已生成订单的申请信息。"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.advertisement import Advertisement
from common.models.recharge_order import RechargeOrder
from common.utils.time_utils import get_beijing_now_naive

AD_PAYMENT_TIMEOUT = timedelta(minutes=30)


def payment_expired(order: RechargeOrder) -> bool:
    """按支付宝预下单的30分钟时限判断待付款二维码是否失效。"""
    return bool(order.created_at and order.created_at + AD_PAYMENT_TIMEOUT <= get_beijing_now_naive())


async def payment_locked_ids(session: AsyncSession, ad_ids: list[int], *, lock: bool = False) -> set[int]:
    """批量查找已有订单的广告ID，修改时先锁广告再当前读订单，避免旧事务快照漏单。"""
    if not ad_ids:
        return set()
    statement = select(RechargeOrder.ad_id).where(
        RechargeOrder.order_type == "ad", RechargeOrder.ad_id.in_(ad_ids),
    )
    rows = await session.execute(statement.with_for_update() if lock else statement.distinct())
    return set(rows.scalars())


async def find_payment_order(session: AsyncSession, ad_id: int, user_id: int, status: str) -> RechargeOrder | None:
    """读取广告最近一笔指定状态订单；所有支付与修改入口统一先锁广告，再锁订单。"""
    return (await session.execute(select(RechargeOrder).where(
        RechargeOrder.ad_id == ad_id, RechargeOrder.user_id == user_id,
        RechargeOrder.order_type == "ad", RechargeOrder.status == status,
    ).order_by(RechargeOrder.id.desc()).limit(1).with_for_update()
        .execution_options(populate_existing=True))).scalar_one_or_none()


async def lock_order_advertisement(session: AsyncSession, order_no: str, *, user_id: int | None = None,
    fallback_ad_id: int | None = None) -> None:
    """付款查询和回调在锁订单之前锁定关联广告，与二维码创建和申请修改保持同一锁顺序。"""
    statement = select(RechargeOrder.ad_id, RechargeOrder.user_id).where(
        RechargeOrder.order_no == order_no, RechargeOrder.order_type == "ad",
    )
    if user_id is not None:
        statement = statement.where(RechargeOrder.user_id == user_id)
    row = (await session.execute(statement)).one_or_none()
    if row:
        ad_id = row.ad_id if row.ad_id is not None else fallback_ad_id
        if ad_id is not None:
            await session.execute(select(Advertisement).where(
                Advertisement.id == ad_id, Advertisement.user_id == row.user_id,
            ).with_for_update().execution_options(populate_existing=True))
