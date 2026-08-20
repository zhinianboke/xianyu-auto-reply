"""
订单发货内容查询服务（公开接口专用）

功能：
1. 通过「分销秘钥 + 闲鱼订单号」免登录查询订单的发货内容
2. 校验秘钥是否存在（对应到具体用户）
3. 校验订单是否归属于该秘钥对应的用户，防止越权查询他人订单

说明：
    此服务供公开接口调用，不依赖登录态，身份与权限完全由分销秘钥承载。
    分销秘钥为用户表 xy_users.secret_key（个人设置-分销管理-秘钥），全局唯一。
    发货内容取自订单表 xy_orders.delivery_content。
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User, UserStatus
from common.models.xy_order import XYOrder


class OrderDeliveryQueryService:
    """订单发货内容查询服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def query_delivery_content(
        self, order_no: str, secret_key: str
    ) -> Tuple[bool, str, Optional[dict[str, Any]]]:
        """根据分销秘钥查询订单发货内容

        校验流程：
        1. 秘钥、订单号非空校验
        2. 秘钥必须存在且对应有效用户
        3. 订单必须存在，且归属人必须为该秘钥对应的用户

        Args:
            order_no: 闲鱼订单号
            secret_key: 分销秘钥（个人设置-分销管理-秘钥）

        Returns:
            (success, message, data)
            - success=True 时 data 含订单发货内容等信息
            - success=False 时 message 为中文错误提示，data 为 None
        """
        order_no = (order_no or "").strip()
        secret_key = (secret_key or "").strip()

        # 1. 基础参数校验
        if not secret_key:
            return False, "秘钥不能为空", None
        if not order_no:
            return False, "订单号不能为空", None

        try:
            # 2. 校验秘钥是否存在（定位到具体用户）
            user_stmt = select(User).where(User.secret_key == secret_key)
            user_result = await self.session.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            if not user:
                return False, "秘钥无效或不存在", None
            if user.status == UserStatus.DELETED:
                return False, "秘钥对应的用户不可用", None

            # 3. 校验订单是否存在，并校验归属
            # 按「订单号 + 归属人」精确匹配，避免同一订单号跨用户时误取到他人订单
            order_stmt = select(XYOrder).where(
                XYOrder.order_no == order_no,
                XYOrder.owner_id == user.id,
            )
            order_result = await self.session.execute(order_stmt)
            order = order_result.scalars().first()
            if not order:
                # 区分「订单不存在」与「订单存在但不属于当前秘钥用户」
                exists_stmt = select(XYOrder.id).where(XYOrder.order_no == order_no).limit(1)
                exists = (await self.session.execute(exists_stmt)).scalar_one_or_none()
                if exists is not None:
                    # 不泄露订单真实归属，仅提示越权
                    return False, "该订单不属于当前秘钥对应的用户", None
                return False, "订单不存在", None

            # 4. 组装发货内容返回
            delivery_content = order.delivery_content or ""
            data = {
                "order_no": order.order_no,
                "delivery_content": delivery_content,
                "delivery_method": order.delivery_method or "",
                "status": (order.status or "").lower(),
                "delivered": bool(delivery_content),
            }
            return True, "获取成功", data
        except Exception as e:
            logger.error(f"查询订单发货内容失败: order_no={order_no}, error={e}")
            return False, "查询订单发货内容失败，请稍后重试", None
