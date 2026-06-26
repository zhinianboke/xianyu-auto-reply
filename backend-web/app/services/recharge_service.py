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
from app.services.alipay_service import AlipayService

from common.utils.time_utils import get_beijing_now_naive, safe_isoformat
logger = logging.getLogger(__name__)

# 续期单价的系统设置 key
RENEW_MONTH_PRICE_KEY = 'user.renew_month_price'
# 续期最大月数（一次性续期上限，防止误操作或溢出）
MAX_RENEW_MONTHS = 120

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
        order.paid_at = get_beijing_now_naive()

        await self.session.commit()
        logger.info(
            f"充值成功: 用户={user_id}, 金额={amount}, "
            f"余额: {balance_before} -> {balance_after}"
        )

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
