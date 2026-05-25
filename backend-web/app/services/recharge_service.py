"""
充值服务

功能：
1. 创建充值订单并调用支付宝当面付生成二维码
2. 处理支付宝异步通知回调
3. 充值成功后更新用户余额并插入资金流水（基于用户加锁防并发）
4. 查询充值订单状态
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fund_flow import FundFlow
from common.models.recharge_order import RechargeOrder
from common.models.user_setting import UserSetting
from app.services.alipay_service import AlipayService

from common.utils.time_utils import safe_isoformat
logger = logging.getLogger(__name__)

# 余额在 user_settings 中的 key
BALANCE_KEY = 'balance'


class RechargeService:
    """充值服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_recharge_order(
        self, user_id: int, amount: str
    ) -> Dict[str, Any]:
        """创建充值订单并生成支付宝二维码

        Args:
            user_id: 用户ID
            amount: 充值金额

        Returns:
            包含订单信息和二维码的字典
        """
        # 校验金额
        try:
            amt = Decimal(amount)
            if amt <= 0:
                return {'success': False, 'message': '充值金额必须大于0'}
            if amt > Decimal('10000'):
                return {'success': False, 'message': '单次充值金额不能超过10000元'}
        except Exception:
            return {'success': False, 'message': '充值金额格式不正确'}

        # 加载支付宝配置
        try:
            config = await AlipayService.load_config(self.session)
            alipay = AlipayService(config)
        except ValueError as e:
            logger.error(f"支付宝配置错误: {e}")
            return {'success': False, 'message': f'支付宝配置错误: {e}'}

        # 生成订单号
        order_no = AlipayService.generate_order_no()

        # 调用当面付接口
        order_data = {
            'out_trade_no': order_no,
            'total_amount': str(amt),
            'subject': f'余额充值 - {order_no}',
            'body': '用户余额充值',
            'timeout_express': '30m',
        }
        result = alipay.create_f2f_pay(order_data)

        if not result or not result.get('success'):
            error_msg = result.get('error', '生成支付二维码失败') if result else '生成支付二维码失败'
            return {'success': False, 'message': error_msg}

        # 保存充值订单
        order = RechargeOrder(
            order_no=order_no,
            user_id=user_id,
            amount=str(amt),
            status='pending',
            qr_code=result['qr_code'],
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)

        return {
            'success': True,
            'data': {
                'order_id': order.id,
                'order_no': order_no,
                'amount': str(amt),
                'qr_code': result['qr_code'],
            },
        }

    async def handle_alipay_notify(
        self, notify_data: Dict[str, Any]
    ) -> bool:
        """处理支付宝异步通知

        Args:
            notify_data: 支付宝通知数据

        Returns:
            处理是否成功
        """
        out_trade_no = notify_data.get('out_trade_no', '')
        trade_no = notify_data.get('trade_no', '')
        trade_status = notify_data.get('trade_status', '')

        logger.info(f"收到支付宝通知: 订单号={out_trade_no}, 状态={trade_status}")

        # 验签
        try:
            config = await AlipayService.load_config(self.session)
            alipay = AlipayService(config)
        except ValueError as e:
            logger.error(f"支付宝配置错误，无法验签: {e}")
            return False

        if not alipay.verify_notify(notify_data):
            logger.error(f"支付宝通知验签失败: {out_trade_no}")
            return False

        # 查询充值订单
        stmt = select(RechargeOrder).where(RechargeOrder.order_no == out_trade_no)
        result = await self.session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            logger.error(f"充值订单不存在: {out_trade_no}")
            return False

        # 已处理过则直接返回成功
        if order.status == 'paid':
            logger.info(f"充值订单已处理过: {out_trade_no}")
            return True

        # 判断交易状态
        if not AlipayService.is_trade_success(trade_status):
            logger.info(f"交易状态非成功: {trade_status}")
            return True

        # 充值成功，更新余额和插入流水（加锁）
        await self._process_recharge_success(order, trade_no)
        return True

    async def _process_recharge_success(
        self, order: RechargeOrder, trade_no: str
    ) -> None:
        """充值成功处理：更新余额+插入流水（基于用户行锁防并发）

        Args:
            order: 充值订单
            trade_no: 支付宝交易号
        """
        user_id = order.user_id
        amount = Decimal(order.amount)

        # 使用 SELECT ... FOR UPDATE 对用户余额行加锁，防止并发
        lock_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        result = await self.session.execute(lock_stmt)
        balance_setting = result.scalar_one_or_none()

        # 获取当前余额
        if balance_setting:
            balance_before = Decimal(balance_setting.value or '0')
        else:
            balance_before = Decimal('0')

        balance_after = balance_before + amount

        # 更新或创建余额设置
        if balance_setting:
            balance_setting.value = str(balance_after)
        else:
            balance_setting = UserSetting(
                user_id=user_id,
                key=BALANCE_KEY,
                value=str(balance_after),
                description='用户余额',
            )
            self.session.add(balance_setting)

        # 插入资金流水
        flow = FundFlow(
            user_id=user_id,
            type='income',
            amount=str(amount),
            balance_before=str(balance_before),
            balance_after=str(balance_after),
            description=f'余额充值（支付宝当面付）订单号: {order.order_no}',
        )
        self.session.add(flow)

        # 更新充值订单状态
        order.status = 'paid'
        order.trade_no = trade_no
        order.paid_at = datetime.now()

        await self.session.commit()
        logger.info(
            f"充值成功: 用户={user_id}, 金额={amount}, "
            f"余额: {balance_before} -> {balance_after}"
        )

    async def get_order_status(
        self, order_no: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """查询充值订单状态

        Args:
            order_no: 订单号
            user_id: 用户ID

        Returns:
            订单信息字典
        """
        stmt = select(RechargeOrder).where(
            RechargeOrder.order_no == order_no,
            RechargeOrder.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            return None

        return {
            'order_id': order.id,
            'order_no': order.order_no,
            'amount': order.amount,
            'status': order.status,
            'trade_no': order.trade_no,
            'paid_at': safe_isoformat(order.paid_at),
            'created_at': safe_isoformat(order.created_at),
        }
