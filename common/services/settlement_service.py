"""
代理订单结算服务

核心规则：
- 手续费从承担方余额中实际扣除
- fee_payer 决定谁承担手续费：dealer=分销商承担，distributor=货主承担
- 代理（一级/二级）需要从余额扣除卡券成本/对接成本支付给上级
- 每笔流水基于上一笔流水的 balance_after，保证余额连续
- 发货前须校验代理余额是否足够支付成本（+手续费，若由分销商承担）

一级代理结算（货主付手续费 fee_payer=distributor）：
  1. 一级代理余额 -= card_price（卡券成本支付给货主）
  2. 货主余额 += card_price
  3. 货主余额 -= fee（手续费）

一级代理结算（分销商付手续费 fee_payer=dealer）：
  1. 一级代理余额 -= card_price（卡券成本支付给货主）
  2. 一级代理余额 -= fee（手续费）
  3. 货主余额 += card_price

二级代理结算（货主付手续费 fee_payer=distributor）：
  1. 二级代理余额 -= level2_cost（对接成本支付给一级）
  2. 一级代理余额 += level2_cost（收到二级的对接成本）
  3. 一级代理余额 -= card_price（卡券成本支付给货主）
  4. 货主余额 += card_price
  5. 货主余额 -= fee（手续费）

二级代理结算（分销商付手续费 fee_payer=dealer）：
  1. 二级代理余额 -= level2_cost（对接成本支付给一级）
  2. 二级代理余额 -= fee（手续费）
  3. 一级代理余额 += level2_cost（收到二级的对接成本）
  4. 一级代理余额 -= card_price（卡券成本支付给货主）
  5. 货主余额 += card_price

所有余额操作使用 SELECT ... FOR UPDATE 行级锁防并发
所有操作在同一事务中，由调用方 commit 保证原子性
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fund_flow import FundFlow
from common.models.user_setting import UserSetting

logger = logging.getLogger(__name__)

BALANCE_KEY = 'balance'


class SettlementService:
    """代理订单结算服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==================== 余额查询（供发货前校验） ====================

    async def check_balance(self, user_id: int) -> Decimal:
        """查询用户当前余额（不加锁，仅用于发货前预检）
        
        Args:
            user_id: 用户ID
            
        Returns:
            当前余额
        """
        stmt = select(UserSetting.value).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        )
        result = await self.session.execute(stmt)
        val = result.scalar()
        try:
            return Decimal(val or '0')
        except (InvalidOperation, ValueError):
            return Decimal('0')

    # ==================== 一级代理结算 ====================

    async def settle_level1_order(
        self,
        order_no: str,
        dealer_user_id: int,
        owner_user_id: int,
        dock_record_id: int,
        agent_order_id: int,
        sale_price: str,
        card_price: str,
        fee_payer: Optional[str],
        fee_amount: str,
    ) -> dict:
        """一级代理订单结算
        
        Args:
            order_no: 订单号
            dealer_user_id: 一级代理用户ID（发货方）
            owner_user_id: 货主用户ID（卡券拥有者）
            dock_record_id: 对接记录ID
            agent_order_id: 代理订单ID（关联到流水）
            sale_price: 售价
            card_price: 卡券成本（货主的对接价）
            fee_payer: 手续费承担方：dealer-分销商承担, distributor-货主承担
            fee_amount: 手续费金额
            
        Returns:
            结算结果字典
        """
        try:
            fee = Decimal(fee_amount or '0')
            cost = Decimal(card_price or '0')
            sale = Decimal(sale_price or '0')
        except (InvalidOperation, ValueError):
            logger.error(f"结算参数异常: fee={fee_amount}, card_price={card_price}, sale={sale_price}")
            return {'success': False, 'message': '结算参数异常'}

        if fee_payer == 'distributor':
            # ===== 货主付手续费场景 =====
            # 1. 一级代理余额 -= card_price（支付卡券成本给货主）
            if cost > 0:
                await self._deduct_balance(
                    user_id=dealer_user_id,
                    amount=cost,
                    description=f'支付卡券成本给货主（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                )
            # 2. 货主余额 += card_price
            if cost > 0:
                await self._add_balance(
                    user_id=owner_user_id,
                    amount=cost,
                    description=f'收到一级代理卡券成本（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                )
            # 3. 货主余额 -= fee（手续费）
            if fee > 0:
                await self._deduct_balance(
                    user_id=owner_user_id,
                    amount=fee,
                    description=f'分销手续费-货主承担（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                    flow_type='fee',
                )
        else:
            # ===== 分销商付手续费场景（dealer） =====
            # 1. 一级代理余额 -= card_price（支付卡券成本给货主）
            if cost > 0:
                await self._deduct_balance(
                    user_id=dealer_user_id,
                    amount=cost,
                    description=f'支付卡券成本给货主（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                )
            # 2. 一级代理余额 -= fee（手续费）
            if fee > 0:
                await self._deduct_balance(
                    user_id=dealer_user_id,
                    amount=fee,
                    description=f'分销手续费-分销商承担（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                    flow_type='fee',
                )
            # 3. 货主余额 += card_price
            if cost > 0:
                await self._add_balance(
                    user_id=owner_user_id,
                    amount=cost,
                    description=f'收到一级代理卡券成本（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                )

        logger.info(
            f"一级结算完成: 订单={order_no}, 一级代理={dealer_user_id}, "
            f"货主={owner_user_id}, 售价={sale}, 卡券成本={cost}, "
            f"手续费={fee}({fee_payer or 'distributor'}承担)"
        )
        return {'success': True, 'message': '一级结算完成'}

    # ==================== 二级代理结算 ====================

    async def settle_level2_order(
        self,
        order_no: str,
        dealer_user_id: int,
        level1_user_id: int,
        owner_user_id: int,
        dock_record_id: int,
        parent_dock_record_id: int,
        agent_order_id: int,
        sale_price: str,
        level2_cost: str,
        level1_cost: str,
        fee_payer: Optional[str],
        fee_amount: str,
    ) -> dict:
        """二级代理订单结算
        
        Args:
            order_no: 订单号
            dealer_user_id: 二级代理用户ID
            level1_user_id: 一级代理用户ID
            owner_user_id: 货主用户ID
            dock_record_id: 二级对接记录ID
            parent_dock_record_id: 一级对接记录ID
            agent_order_id: 代理订单ID（关联到流水）
            sale_price: 售价
            level2_cost: 二级拿货价（一级的 sub_dock_price，即对接成本）
            level1_cost: 一级拿货价（Card.price，即卡券成本）
            fee_payer: 手续费承担方
            fee_amount: 手续费金额
            
        Returns:
            结算结果字典
        """
        try:
            fee = Decimal(fee_amount or '0')
            l2_cost = Decimal(level2_cost or '0')
            l1_cost = Decimal(level1_cost or '0')
            sale = Decimal(sale_price or '0')
        except (InvalidOperation, ValueError):
            logger.error(f"二级结算参数异常: fee={fee_amount}, l2_cost={level2_cost}, l1_cost={level1_cost}")
            return {'success': False, 'message': '结算参数异常'}

        if fee_payer == 'distributor':
            # ===== 货主付手续费场景 =====
            # 1. 二级代理余额 -= level2_cost（对接成本支付给一级）
            if l2_cost > 0:
                await self._deduct_balance(
                    user_id=dealer_user_id,
                    amount=l2_cost,
                    description=f'支付对接成本给一级代理（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                )
            # 2. 一级代理余额 += level2_cost（收到二级的对接成本）
            if l2_cost > 0:
                await self._add_balance(
                    user_id=level1_user_id,
                    amount=l2_cost,
                    description=f'收到二级代理对接成本（订单: {order_no}）',
                    dock_record_id=parent_dock_record_id,
                    order_id=agent_order_id,
                )
            # 3. 一级代理余额 -= card_price（卡券成本支付给货主）
            if l1_cost > 0:
                await self._deduct_balance(
                    user_id=level1_user_id,
                    amount=l1_cost,
                    description=f'支付卡券成本给货主（订单: {order_no}）',
                    dock_record_id=parent_dock_record_id,
                    order_id=agent_order_id,
                )
            # 4. 货主余额 += card_price
            if l1_cost > 0:
                await self._add_balance(
                    user_id=owner_user_id,
                    amount=l1_cost,
                    description=f'收到一级代理卡券成本（订单: {order_no}）',
                    dock_record_id=parent_dock_record_id,
                    order_id=agent_order_id,
                )
            # 5. 货主余额 -= fee（手续费）
            if fee > 0:
                await self._deduct_balance(
                    user_id=owner_user_id,
                    amount=fee,
                    description=f'分销手续费-货主承担（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                    flow_type='fee',
                )
        else:
            # ===== 分销商付手续费场景（dealer） =====
            # 1. 二级代理余额 -= level2_cost（对接成本支付给一级）
            if l2_cost > 0:
                await self._deduct_balance(
                    user_id=dealer_user_id,
                    amount=l2_cost,
                    description=f'支付对接成本给一级代理（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                )
            # 2. 二级代理余额 -= fee（手续费）
            if fee > 0:
                await self._deduct_balance(
                    user_id=dealer_user_id,
                    amount=fee,
                    description=f'分销手续费-分销商承担（订单: {order_no}）',
                    dock_record_id=dock_record_id,
                    order_id=agent_order_id,
                    flow_type='fee',
                )
            # 3. 一级代理余额 += level2_cost（收到二级的对接成本）
            if l2_cost > 0:
                await self._add_balance(
                    user_id=level1_user_id,
                    amount=l2_cost,
                    description=f'收到二级代理对接成本（订单: {order_no}）',
                    dock_record_id=parent_dock_record_id,
                    order_id=agent_order_id,
                )
            # 4. 一级代理余额 -= card_price（卡券成本支付给货主）
            if l1_cost > 0:
                await self._deduct_balance(
                    user_id=level1_user_id,
                    amount=l1_cost,
                    description=f'支付卡券成本给货主（订单: {order_no}）',
                    dock_record_id=parent_dock_record_id,
                    order_id=agent_order_id,
                )
            # 5. 货主余额 += card_price
            if l1_cost > 0:
                await self._add_balance(
                    user_id=owner_user_id,
                    amount=l1_cost,
                    description=f'收到一级代理卡券成本（订单: {order_no}）',
                    dock_record_id=parent_dock_record_id,
                    order_id=agent_order_id,
                )

        logger.info(
            f"二级结算完成: 订单={order_no}, 二级代理={dealer_user_id}, "
            f"一级代理={level1_user_id}, 货主={owner_user_id}, "
            f"售价={sale}, 对接成本={l2_cost}, 卡券成本={l1_cost}, "
            f"手续费={fee}({fee_payer or 'distributor'}承担)"
        )
        return {'success': True, 'message': '二级结算完成'}

    # ==================== 内部方法（带行锁） ====================

    async def _add_balance(
        self,
        user_id: int,
        amount: Decimal,
        description: str,
        dock_record_id: Optional[int] = None,
        order_id: Optional[int] = None,
    ) -> bool:
        """增加用户余额（SELECT ... FOR UPDATE 行锁）
        
        Args:
            user_id: 用户ID
            amount: 增加金额
            description: 流水描述
            dock_record_id: 关联对接记录ID
            order_id: 关联代理订单ID
            
        Returns:
            是否成功
        """
        # 加行锁读取余额
        lock_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        result = await self.session.execute(lock_stmt)
        balance_setting = result.scalar_one_or_none()

        if balance_setting:
            balance_before = Decimal(balance_setting.value or '0')
        else:
            balance_before = Decimal('0')

        balance_after = balance_before + amount

        # 更新或创建余额
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

        # 插入流水
        flow = FundFlow(
            user_id=user_id,
            type='income',
            amount=str(amount),
            balance_before=str(balance_before),
            balance_after=str(balance_after),
            dock_record_id=dock_record_id,
            order_id=order_id,
            description=description,
        )
        self.session.add(flow)

        logger.info(
            f"余额增加: 用户={user_id}, 金额={amount}, "
            f"余额: {balance_before} -> {balance_after}, "
            f"描述={description}"
        )
        return True

    async def _deduct_balance(
        self,
        user_id: int,
        amount: Decimal,
        description: str,
        dock_record_id: Optional[int] = None,
        order_id: Optional[int] = None,
        flow_type: str = 'expense',
    ) -> bool:
        """扣减用户余额（SELECT ... FOR UPDATE 行锁）
        
        Args:
            user_id: 用户ID
            amount: 扣减金额
            description: 流水描述
            dock_record_id: 关联对接记录ID
            order_id: 关联代理订单ID
            flow_type: 流水类型，默认 expense，手续费扣除时传 fee
            
        Returns:
            是否成功
        """
        # 加行锁读取余额
        lock_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        result = await self.session.execute(lock_stmt)
        balance_setting = result.scalar_one_or_none()

        if balance_setting:
            balance_before = Decimal(balance_setting.value or '0')
        else:
            balance_before = Decimal('0')

        balance_after = balance_before - amount

        # 更新或创建余额
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

        # 插入流水
        flow = FundFlow(
            user_id=user_id,
            type=flow_type,
            amount=str(amount),
            balance_before=str(balance_before),
            balance_after=str(balance_after),
            dock_record_id=dock_record_id,
            order_id=order_id,
            description=description,
        )
        self.session.add(flow)

        logger.info(
            f"余额扣减: 用户={user_id}, 金额={amount}, 类型={flow_type}, "
            f"余额: {balance_before} -> {balance_after}, "
            f"描述={description}"
        )
        return True
