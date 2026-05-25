"""
提现风控检测服务

对提现申请进行多维度真实性核验，结果仅用于邮件提醒，不限制提现操作。

检验项目：
1. 余额一致性 - 流水总收入 - 总支出是否等于当前余额
2. 充值订单核验 - 充值流水是否有对应已支付的充值订单
3. 代销/分销订单核验 - 代销收入流水是否有对应真实的代理订单
4. 流水余额序列完整性 - 每笔流水的 balance_before 是否接续上一笔 balance_after
5. 提现记录与流水一致性 - 结算记录提现总额是否与支出流水匹配
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.agent_order import AgentOrder
from common.models.fund_flow import FundFlow
from common.models.recharge_order import RechargeOrder
from common.models.settlement_record import SettlementRecord
from common.models.user_setting import UserSetting

import logging
logger = logging.getLogger(__name__)

# 允许余额计算的浮点误差（分）
TOLERANCE = Decimal('0.01')


@dataclass
class RiskItem:
    """单项风控检验结果"""
    title: str                          # 检验项名称
    passed: bool                        # 是否通过
    summary: str                        # 一句话结论
    issues: List[str] = field(default_factory=list)  # 具体异常描述列表


@dataclass
class RiskCheckResult:
    """全部风控检验结果"""
    items: List[RiskItem] = field(default_factory=list)

    @property
    def has_issue(self) -> bool:
        return any(not item.passed for item in self.items)


def _to_dec(val: Optional[str]) -> Decimal:
    """安全转换为 Decimal，失败返回 0"""
    try:
        return Decimal((val or '0').strip())
    except InvalidOperation:
        return Decimal('0')


async def run_all_checks(user_id: int, current_balance: str, record_id: int) -> RiskCheckResult:
    """
    对指定用户执行全部风控检验。

    Args:
        user_id: 用户ID
        current_balance: 用户当前余额（提现申请完成后的值）
        record_id: 本次提现结算记录ID

    Returns:
        RiskCheckResult
    """
    from common.db.session import async_session_maker

    async with async_session_maker() as session:
        result = RiskCheckResult()
        result.items.append(await _check_balance_consistency(session, user_id, current_balance))
        result.items.append(await _check_recharge_flows(session, user_id))
        result.items.append(await _check_agent_flows(session, user_id))
        result.items.append(await _check_flow_sequence(session, user_id))
        result.items.append(await _check_withdrawal_consistency(session, user_id))
        return result


# ────────────────────────────────────────────────────────────────────────────
# 检验1：余额一致性
# ────────────────────────────────────────────────────────────────────────────
async def _check_balance_consistency(session: AsyncSession, user_id: int, current_balance: str) -> RiskItem:
    """余额一致性：流水总收入 - 总支出 应等于当前余额"""
    title = "余额一致性检验"
    try:
        flows = (await session.execute(
            select(FundFlow).where(FundFlow.user_id == user_id)
        )).scalars().all()

        total_income = sum(_to_dec(f.amount) for f in flows if f.type == 'income')
        total_expense = sum(_to_dec(f.amount) for f in flows if f.type in ('expense', 'fee'))
        computed = total_income - total_expense
        actual = _to_dec(current_balance)

        diff = abs(computed - actual)
        if diff <= TOLERANCE:
            return RiskItem(title=title, passed=True,
                            summary=f"✅ 通过：流水计算余额 ¥{computed:.2f} 与实际余额 ¥{actual:.2f} 一致")
        else:
            return RiskItem(
                title=title, passed=False,
                summary=f"⚠️ 异常：流水计算余额 ¥{computed:.2f} 与实际余额 ¥{actual:.2f} 相差 ¥{diff:.2f}",
                issues=[
                    f"流水收入合计：¥{total_income:.2f}",
                    f"流水支出合计：¥{total_expense:.2f}",
                    f"流水计算余额：¥{computed:.2f}",
                    f"系统记录余额：¥{actual:.2f}",
                    f"差额：¥{diff:.2f}（超过容差 ¥{TOLERANCE}）",
                ]
            )
    except Exception as e:
        logger.warning(f"余额一致性检验异常: {e}")
        return RiskItem(title=title, passed=False, summary=f"⚠️ 检验执行异常: {e}")


# ────────────────────────────────────────────────────────────────────────────
# 检验2：充值订单核验
# ────────────────────────────────────────────────────────────────────────────
_RECHARGE_DESC_RE = re.compile(r'订单号[：:]\s*(\S+)')

async def _check_recharge_flows(session: AsyncSession, user_id: int) -> RiskItem:
    """充值流水核验：每笔充值收入应能找到对应 paid 状态的充值订单"""
    title = "充值订单核验"
    try:
        flows = (await session.execute(
            select(FundFlow).where(
                FundFlow.user_id == user_id,
                FundFlow.type == 'income',
            )
        )).scalars().all()

        recharge_flows = [f for f in flows if f.description and '充值' in f.description]
        if not recharge_flows:
            return RiskItem(title=title, passed=True, summary="✅ 通过：无充值流水，跳过检验")

        issues: List[str] = []
        ok_count = 0
        for f in recharge_flows:
            m = _RECHARGE_DESC_RE.search(f.description or '')
            if not m:
                issues.append(f"流水ID {f.id}（¥{f.amount}）：描述中未找到订单号")
                continue
            order_no = m.group(1)
            order = (await session.execute(
                select(RechargeOrder).where(
                    RechargeOrder.order_no == order_no,
                    RechargeOrder.user_id == user_id,
                )
            )).scalar_one_or_none()

            if not order:
                issues.append(f"流水ID {f.id}（¥{f.amount}）：充值订单 {order_no} 不存在")
            elif order.status != 'paid':
                issues.append(
                    f"流水ID {f.id}（¥{f.amount}）：充值订单 {order_no} 状态为 {order.status}，非 paid"
                )
            else:
                ok_count += 1

        if issues:
            return RiskItem(
                title=title, passed=False,
                summary=f"⚠️ 异常：{len(recharge_flows)} 笔充值流水中 {len(issues)} 笔核验不通过",
                issues=issues,
            )
        return RiskItem(
            title=title, passed=True,
            summary=f"✅ 通过：{ok_count} 笔充值流水均有对应已支付订单",
        )
    except Exception as e:
        logger.warning(f"充值订单核验异常: {e}")
        return RiskItem(title=title, passed=False, summary=f"⚠️ 检验执行异常: {e}")


# ────────────────────────────────────────────────────────────────────────────
# 检验3：代销/分销订单核验
# ────────────────────────────────────────────────────────────────────────────
_AGENT_KEYWORDS = ('收到一级代理', '收到二级代理', '代理卡券', '分销收益', '对接收益')

async def _check_agent_flows(session: AsyncSession, user_id: int) -> RiskItem:
    """代销流水核验：代销/分销收入流水应有对应的 AgentOrder"""
    title = "代销/分销订单核验"
    try:
        flows = (await session.execute(
            select(FundFlow).where(
                FundFlow.user_id == user_id,
                FundFlow.type == 'income',
            )
        )).scalars().all()

        agent_flows = [
            f for f in flows
            if f.description and any(kw in f.description for kw in _AGENT_KEYWORDS)
        ]
        if not agent_flows:
            return RiskItem(title=title, passed=True, summary="✅ 通过：无代销/分销收入流水，跳过检验")

        issues: List[str] = []
        ok_count = 0
        for f in agent_flows:
            if not f.order_id:
                issues.append(f"流水ID {f.id}（¥{f.amount}，{f.description[:30]}）：缺少关联订单ID")
                continue
            order = (await session.execute(
                select(AgentOrder).where(AgentOrder.id == f.order_id)
            )).scalar_one_or_none()

            if not order:
                issues.append(
                    f"流水ID {f.id}（¥{f.amount}）：关联代理订单 {f.order_id} 不存在"
                )
            else:
                ok_count += 1

        if issues:
            return RiskItem(
                title=title, passed=False,
                summary=f"⚠️ 异常：{len(agent_flows)} 笔代销流水中 {len(issues)} 笔核验不通过",
                issues=issues,
            )
        return RiskItem(
            title=title, passed=True,
            summary=f"✅ 通过：{ok_count} 笔代销/分销流水均有对应真实订单",
        )
    except Exception as e:
        logger.warning(f"代销订单核验异常: {e}")
        return RiskItem(title=title, passed=False, summary=f"⚠️ 检验执行异常: {e}")


# ────────────────────────────────────────────────────────────────────────────
# 检验4：流水余额序列完整性
# ────────────────────────────────────────────────────────────────────────────
async def _check_flow_sequence(session: AsyncSession, user_id: int) -> RiskItem:
    """流水序列完整性：每笔流水的 balance_before 应等于上一笔的 balance_after"""
    title = "流水余额序列完整性"
    try:
        flows = (await session.execute(
            select(FundFlow)
            .where(FundFlow.user_id == user_id)
            .order_by(FundFlow.id.asc())
        )).scalars().all()

        if len(flows) < 2:
            return RiskItem(title=title, passed=True, summary="✅ 通过：流水不足两笔，无需检验序列")

        issues: List[str] = []
        for i in range(1, len(flows)):
            prev = flows[i - 1]
            curr = flows[i]
            expected = _to_dec(prev.balance_after)
            actual = _to_dec(curr.balance_before)
            if abs(expected - actual) > TOLERANCE:
                issues.append(
                    f"流水ID {curr.id}：balance_before=¥{curr.balance_before}，"
                    f"上一笔ID {prev.id} balance_after=¥{prev.balance_after}，不连续"
                )
                if len(issues) >= 10:
                    issues.append("...（超过10处异常，已截断）")
                    break

        if issues:
            return RiskItem(
                title=title, passed=False,
                summary=f"⚠️ 异常：流水余额序列存在 {len(issues)} 处断点",
                issues=issues,
            )
        return RiskItem(
            title=title, passed=True,
            summary=f"✅ 通过：全部 {len(flows)} 笔流水余额序列连续一致",
        )
    except Exception as e:
        logger.warning(f"流水序列检验异常: {e}")
        return RiskItem(title=title, passed=False, summary=f"⚠️ 检验执行异常: {e}")


# ────────────────────────────────────────────────────────────────────────────
# 检验5：提现记录与支出流水一致性
# ────────────────────────────────────────────────────────────────────────────
async def _check_withdrawal_consistency(session: AsyncSession, user_id: int) -> RiskItem:
    """提现记录一致性：结算记录中已审核/已打款的提现总额应与支出流水中提现条目匹配"""
    title = "提现记录与流水一致性"
    try:
        # 统计所有结算记录提现总额（任何状态，扣减在申请时即确定）
        records = (await session.execute(
            select(SettlementRecord).where(
                SettlementRecord.user_id == user_id,
            )
        )).scalars().all()
        settlement_total = sum(_to_dec(r.amount) for r in records)

        # 统计流水中的提现支出总额
        flows = (await session.execute(
            select(FundFlow).where(
                FundFlow.user_id == user_id,
                FundFlow.type == 'expense',
            )
        )).scalars().all()
        withdraw_flows = [f for f in flows if f.description and '提现' in f.description]
        flow_withdraw_total = sum(_to_dec(f.amount) for f in withdraw_flows)

        diff = abs(settlement_total - flow_withdraw_total)
        if diff <= TOLERANCE:
            return RiskItem(
                title=title, passed=True,
                summary=f"✅ 通过：结算记录提现合计 ¥{settlement_total:.2f} 与流水支出 ¥{flow_withdraw_total:.2f} 一致",
            )
        issues = [
            f"结算记录（全部状态）提现合计：¥{settlement_total:.2f}（共 {len(records)} 笔）",
            f"流水支出（含提现字样）合计：¥{flow_withdraw_total:.2f}（共 {len(withdraw_flows)} 笔）",
            f"差额：¥{diff:.2f}",
        ]
        return RiskItem(
            title=title, passed=False,
            summary=f"⚠️ 异常：结算记录与流水提现金额相差 ¥{diff:.2f}",
            issues=issues,
        )
    except Exception as e:
        logger.warning(f"提现记录一致性检验异常: {e}")
        return RiskItem(title=title, passed=False, summary=f"⚠️ 检验执行异常: {e}")
