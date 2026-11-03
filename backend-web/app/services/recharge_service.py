"""
充值服务

功能：
1. 委托支付结账服务创建充值订单并处理异步回调
2. 管理员手动调整用户余额和用户续期
3. 查询充值订单状态
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fund_flow import FundFlow
from common.models.recharge_order import RechargeOrder
from common.models.system_setting import SystemSetting
from common.models.user import User
from common.models.user_setting import UserSetting
from app.services.payment_checkout_service import PaymentCheckoutService
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat
logger = logging.getLogger(__name__)

# 续期单价的系统设置 key
RENEW_MONTH_PRICE_KEY = 'user.renew_month_price'
# 续期最大月数（一次性续期上限，防止误操作或溢出）
MAX_RENEW_MONTHS = 120
RECHARGE_PAYMENT_TIMEOUT = timedelta(minutes=30)

# 余额在 user_settings 中的 key
BALANCE_KEY = 'balance'


class RechargeService:
    """充值服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_recharge_order(self, user_id: int, amount: str, pay_type: str | None = None) -> Dict[str, Any]:
        """按当前启用渠道创建充值订单。"""
        return await PaymentCheckoutService(self.session).create_recharge_order(user_id, amount, pay_type)

    async def handle_alipay_notify(self, notify_data: Dict[str, Any]) -> bool:
        """委托支付结账服务处理支付宝异步通知。"""
        return await PaymentCheckoutService(self.session).handle_alipay_notify(notify_data)

    async def handle_zzcode_notify(self, notify_data: dict[str, str]) -> bool:
        """委托支付结账服务处理码支付异步通知。"""
        return await PaymentCheckoutService(self.session).handle_zzcode_notify(notify_data)

    async def manual_recharge(
        self,
        admin_user_id: int,
        target_user_id: int,
        amount: str,
        remark: str = '',
    ) -> Dict[str, Any]:
        """管理员手动调整用户余额（正数充值 / 负数扣减），加锁防并发

        复用与支付宝充值一致的加锁改余额 + 写流水模式：
        SELECT ... FOR UPDATE 锁定 balance 行 -> 计算 balance_before/after ->
        upsert UserSetting -> 插入 FundFlow -> commit。

        与支付宝充值的差异：
        - 金额允许为负（扣减），FundFlow.amount 存绝对值，方向靠 type 区分
          （正=income，负=expense）。
        - 不允许扣成负余额：balance_after < 0 直接拒绝。
        - description 不含"充值"字样，避免触发提现风控的"充值订单核验"
          （见 withdraw_risk_check.py，其按 '充值' in description 匹配充值订单）。

        Args:
            admin_user_id: 操作管理员ID（记入流水描述，便于审计）
            target_user_id: 目标用户ID
            amount: 调整金额字符串，正数为充值，负数为扣减
            remark: 备注（可选）

        Returns:
            {'success': bool, 'message': str, 'data': {...}}
        """
        # 校验金额：解析失败 / 为零 / 绝对值超上限均拒绝
        try:
            amt = Decimal(amount)
        except (InvalidOperation, ValueError):
            return {'success': False, 'message': '金额格式不正确'}
        if amt == 0:
            return {'success': False, 'message': '调整金额不能为0'}
        if abs(amt) > Decimal('10000'):
            return {'success': False, 'message': '单次调整金额不能超过10000元'}

        # SELECT ... FOR UPDATE 锁定目标用户余额行，防止并发
        lock_stmt = select(UserSetting).where(
            UserSetting.user_id == target_user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        result = await self.session.execute(lock_stmt)
        balance_setting = result.scalar_one_or_none()

        if balance_setting:
            balance_before = Decimal(balance_setting.value or '0')
        else:
            balance_before = Decimal('0')

        balance_after = balance_before + amt

        # 不允许扣成负余额
        if balance_after < 0:
            return {
                'success': False,
                'message': f'当前余额 ¥{balance_before:.2f}，扣减 ¥{abs(amt):.2f} 后将为负，操作被拒绝',
            }

        # upsert 余额
        if balance_setting:
            balance_setting.value = str(balance_after)
        else:
            balance_setting = UserSetting(
                user_id=target_user_id,
                key=BALANCE_KEY,
                value=str(balance_after),
                description='用户余额',
            )
            self.session.add(balance_setting)

        # 写流水：金额存绝对值，方向靠 type 区分；description 不含"充值"字样
        direction = '增加' if amt > 0 else '扣减'
        flow_type = 'income' if amt > 0 else 'expense'
        desc = f'管理员手动调整余额（{direction}），操作人ID: {admin_user_id}'
        if remark:
            # 净化备注中的"充值"字样：手动调整流水一旦含"充值"会被提现风控
            # （withdraw_risk_check._check_recharge_flows 按 '充值' in description 匹配）
            # 当作充值流水核验，进而因找不到对应充值订单而误报。
            safe_remark = remark.replace('充值', '入账')
            desc += f'，备注: {safe_remark}'
        flow = FundFlow(
            user_id=target_user_id,
            type=flow_type,
            amount=str(abs(amt)),
            balance_before=str(balance_before),
            balance_after=str(balance_after),
            description=desc,
        )
        self.session.add(flow)

        await self.session.commit()
        logger.info(
            f"管理员手动调整余额: 操作人={admin_user_id}, 目标用户={target_user_id}, "
            f"调整={amt}, 余额: {balance_before} -> {balance_after}"
        )
        return {
            'success': True,
            'message': '余额调整成功',
            'data': {
                'balance_before': f'{balance_before:.2f}',
                'balance_after': f'{balance_after:.2f}',
                'amount': f'{amt:.2f}',
            },
        }

    async def renew_membership(
        self, user_id: int, months: int
    ) -> Dict[str, Any]:
        """用户续期：扣减余额并延长到期日（基于余额行锁防并发）

        复用与充值一致的加锁改余额 + 写流水模式：
        SELECT ... FOR UPDATE 锁定 balance 行 -> 校验余额充足 ->
        扣减余额 + 写 FundFlow(expense) -> 延长 User.expire_at -> commit。

        到期日延长规则：
        - 未到期用户（expire_at 存在且晚于当前时间）：在原到期日基础上加 months 个月
        - 已到期 / 从未设置到期日的用户：从当前时间开始加 months 个月

        Args:
            user_id: 用户ID
            months: 续期月数（1 ~ MAX_RENEW_MONTHS）

        Returns:
            {'success': bool, 'message': str, 'data': {...}}
        """
        # 校验月数
        if not isinstance(months, int) or months <= 0:
            return {'success': False, 'message': '续期月数必须为正整数'}
        if months > MAX_RENEW_MONTHS:
            return {'success': False, 'message': f'单次续期不能超过{MAX_RENEW_MONTHS}个月'}

        # 读取续期单价
        price_stmt = select(SystemSetting.value).where(
            SystemSetting.key == RENEW_MONTH_PRICE_KEY
        )
        price_raw = (await self.session.execute(price_stmt)).scalar_one_or_none()
        price_text = str(price_raw or '').strip()
        if not price_text:
            return {'success': False, 'message': '续期功能未开放，请联系管理员配置续期单价'}
        try:
            unit_price = Decimal(price_text)
        except (InvalidOperation, ValueError):
            return {'success': False, 'message': '续期单价配置有误，请联系管理员'}
        if unit_price <= 0:
            return {'success': False, 'message': '续期单价配置有误，请联系管理员'}

        total = unit_price * months

        # SELECT ... FOR UPDATE 锁定用户余额行，防止并发
        lock_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        balance_setting = (await self.session.execute(lock_stmt)).scalar_one_or_none()

        if balance_setting:
            balance_before = Decimal(balance_setting.value or '0')
        else:
            balance_before = Decimal('0')

        # 余额不足直接拒绝
        if balance_before < total:
            return {
                'success': False,
                'message': f'余额不足，续期 {months} 个月需 ¥{total:.2f}，当前余额 ¥{balance_before:.2f}',
            }

        balance_after = balance_before - total

        # upsert 余额
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

        # 写流水：续期为支出，金额存绝对值
        flow = FundFlow(
            user_id=user_id,
            type='expense',
            amount=str(total),
            balance_before=str(balance_before),
            balance_after=str(balance_after),
            description=f'账户续期 {months} 个月（单价 ¥{unit_price:.2f}/月）',
        )
        self.session.add(flow)

        # 延长到期日
        user = await self.session.get(User, user_id)
        if not user:
            await self.session.rollback()
            return {'success': False, 'message': '用户不存在'}

        now = get_beijing_now_naive()
        # 未到期则从原到期日累加，已到期 / 无到期日则从当前时间累加
        if user.expire_at and user.expire_at > now:
            base_time = user.expire_at
        else:
            base_time = now
        new_expire_at = base_time + relativedelta(months=months)
        user.expire_at = new_expire_at

        await self.session.commit()
        logger.info(
            f"用户续期成功: 用户={user_id}, 月数={months}, 扣减={total}, "
            f"余额: {balance_before} -> {balance_after}, 到期日 -> {new_expire_at}"
        )
        return {
            'success': True,
            'message': f'续期成功，已延长 {months} 个月',
            'data': {
                'months': months,
                'unit_price': f'{unit_price:.2f}',
                'total': f'{total:.2f}',
                'balance_before': f'{balance_before:.2f}',
                'balance_after': f'{balance_after:.2f}',
                'expire_at': safe_isoformat(new_expire_at),
            },
        }

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
            RechargeOrder.order_type == 'recharge',
        ).with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            return None

        if (
            order.status == 'pending'
            and order.created_at
            and order.created_at + RECHARGE_PAYMENT_TIMEOUT <= get_beijing_now_naive()
        ):
            order.status = 'expired'
            await self.session.commit()

        return {
            'order_id': order.id,
            'order_no': order.order_no,
            'amount': order.amount,
            'status': order.status,
            'trade_no': order.trade_no,
            'paid_at': safe_isoformat(order.paid_at),
            'created_at': safe_isoformat(order.created_at),
        }
