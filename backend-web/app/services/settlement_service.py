"""
结算服务

功能：
1. 创建提现结算记录
2. 查询当前用户结算记录列表
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fund_flow import FundFlow
from common.models.settlement_record import SettlementRecord
from common.models.user_setting import UserSetting
from common.models.user import User
from common.models.system_setting import SystemSetting
from common.utils.pagination import (
    build_pagination_response,
    execute_paginated_with_filters,
)
from common.utils.time_utils import safe_isoformat

logger = logging.getLogger(__name__)

BALANCE_KEY = 'balance'
ALIPAY_ID_KEY = 'alipay_id'
PAYMENT_QRCODE_KEY = 'payment_qrcode'
PAYMENT_TYPE_KEY = 'payment_type'
WITHDRAW_NOTIFY_EMAIL_KEY = 'withdraw.notify_email'
WITHDRAW_MIN_AMOUNT_KEY = 'withdraw.min_amount'
WITHDRAW_REVIEW_SECRET_KEY = 'withdraw.review_secret'
# Fallback secret for backward compatibility (used when DB setting is not configured)
_DEFAULT_REVIEW_SECRET = "xianyu_withdraw_review_2024"


class SettlementService:
    """结算服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_withdraw_record(self, user_id: int, amount: str) -> Dict[str, Any]:
        """创建提现记录，状态默认为待审核，并同步扣减余额与写入流水"""
        # 校验系统是否配置了提现通知邮箱
        notify_email = await self._get_withdraw_notify_email()
        if not notify_email:
            return {'success': False, 'message': '系统未配置提现通知邮箱，暂时无法提现，请联系管理员'}
        
        try:
            withdraw_amount = Decimal((amount or '').strip())
        except Exception:
            return {'success': False, 'message': '提现金额格式不正确'}

        if withdraw_amount <= Decimal('0'):
            return {'success': False, 'message': '提现金额必须大于0'}

        lock_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        balance_result = await self.session.execute(lock_stmt)
        balance_setting = balance_result.scalar_one_or_none()

        # 查询收款码和收款方式
        qrcode_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == PAYMENT_QRCODE_KEY,
        )
        qrcode_result = await self.session.execute(qrcode_stmt)
        qrcode_setting = qrcode_result.scalar_one_or_none()
        payment_qrcode = (qrcode_setting.value if qrcode_setting else '').strip()

        if not payment_qrcode:
            return {'success': False, 'message': '请先上传收款码'}

        type_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == PAYMENT_TYPE_KEY,
        )
        type_result = await self.session.execute(type_stmt)
        type_setting = type_result.scalar_one_or_none()
        payment_type = (type_setting.value if type_setting else 'alipay').strip()

        # 兼容旧数据：也查一下 alipay_id
        alipay_stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == ALIPAY_ID_KEY,
        )
        alipay_result = await self.session.execute(alipay_stmt)
        alipay_setting = alipay_result.scalar_one_or_none()
        alipay_id = (alipay_setting.value if alipay_setting else '').strip()

        try:
            balance_before = Decimal((balance_setting.value if balance_setting else '0').strip() or '0')
        except Exception:
            return {'success': False, 'message': '当前余额数据异常，请联系管理员处理'}

        if withdraw_amount > Decimal('10000'):
            return {'success': False, 'message': '单次提现金额不能超过10000元'}

        # 校验最低提现金额
        min_amount_stmt = select(SystemSetting).where(SystemSetting.key == WITHDRAW_MIN_AMOUNT_KEY)
        min_amount_result = await self.session.execute(min_amount_stmt)
        min_amount_setting = min_amount_result.scalar_one_or_none()
        min_amount_str = (min_amount_setting.value if min_amount_setting else '').strip()
        if min_amount_str:
            try:
                min_amount = Decimal(min_amount_str)
                if min_amount > Decimal('0') and withdraw_amount < min_amount:
                    return {'success': False, 'message': f'提现金额不能低于最低提现金额 ¥{min_amount}'}
            except Exception:
                pass

        if withdraw_amount > balance_before:
            return {'success': False, 'message': '提现金额不能大于当前余额'}

        balance_after = balance_before - withdraw_amount

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

        record = SettlementRecord(
            user_id=user_id,
            alipay_id=alipay_id or '',
            payment_type=payment_type,
            payment_qrcode=payment_qrcode,
            amount=str(withdraw_amount),
            status='pending_review',
            remark='用户发起提现申请',
        )
        self.session.add(record)
        await self.session.flush()

        flow = FundFlow(
            user_id=user_id,
            type='expense',
            amount=str(withdraw_amount),
            balance_before=str(balance_before),
            balance_after=str(balance_after),
            description=f'余额提现申请，结算记录ID: {record.id}',
        )
        self.session.add(flow)

        await self.session.commit()
        await self.session.refresh(record)

        logger.info(
            f"提现申请创建成功: 用户={user_id}, 金额={withdraw_amount}, "
            f"余额: {balance_before} -> {balance_after}, 结算记录ID={record.id}"
        )

        # 异步发送提现通知邮件（不阻塞主流程）
        try:
            import asyncio
            from app.services.email_service import send_withdraw_notification_email
            
            # 获取用户名
            user_result = await self.session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            username = user.username if user else f"用户{user_id}"
            
            # 创建后台任务发送邮件
            asyncio.create_task(
                send_withdraw_notification_email(
                    user_id=user_id,
                    username=username,
                    amount=str(withdraw_amount),
                    alipay_id=alipay_id or '',
                    payment_type=payment_type,
                    payment_qrcode=payment_qrcode,
                    record_id=record.id,
                    balance_after=str(balance_after),
                )
            )
            logger.info(f"提现通知邮件任务已创建: 用户={username}, 金额={withdraw_amount}")
        except Exception as e:
            # 邮件发送失败不影响提现主流程
            logger.warning(f"创建提现通知邮件任务失败: {e}")

        return {
            'success': True,
            'message': '提现申请已提交，等待审核',
            'data': {
                'id': record.id,
                'amount': record.amount,
                'status': record.status,
                'alipay_id': record.alipay_id,
                'balance': str(balance_after),
                'created_at': safe_isoformat(record.created_at),
            },
        }

    async def get_settlement_records(self, user_id: int, page: int, page_size: int) -> Dict[str, Any]:
        """分页查询结算记录，按创建时间倒序"""
        page = max(page, 1)
        page_size = page_size if page_size in (10, 20, 50, 100) else 20

        records, total = await execute_paginated_with_filters(
            self.session,
            SettlementRecord,
            filters=[SettlementRecord.user_id == user_id],
            order_by=[desc(SettlementRecord.created_at), desc(SettlementRecord.id)],
            page=page,
            page_size=page_size,
        )

        items = [
            {
                'id': item.id,
                'alipay_id': item.alipay_id,
                'payment_type': item.payment_type,
                'payment_qrcode': item.payment_qrcode,
                'amount': item.amount,
                'status': item.status,
                'remark': item.remark,
                'reject_reason': item.reject_reason,
                'created_at': safe_isoformat(item.created_at),
                'updated_at': safe_isoformat(item.updated_at),
            }
            for item in records
        ]

        return {
            'success': True,
            'data': build_pagination_response(items, total, page, page_size),
        }

    async def _get_withdraw_notify_email(self) -> str:
        """获取提现通知邮箱配置"""
        stmt = select(SystemSetting).where(SystemSetting.key == WITHDRAW_NOTIFY_EMAIL_KEY)
        result = await self.session.execute(stmt)
        setting = result.scalar_one_or_none()
        return (setting.value if setting else '').strip()


async def get_withdraw_notify_email() -> str:
    """获取提现通知邮箱配置（独立函数，供邮件服务调用）"""
    from common.db.session import async_session_maker
    
    async with async_session_maker() as session:
        stmt = select(SystemSetting).where(SystemSetting.key == WITHDRAW_NOTIFY_EMAIL_KEY)
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        return (setting.value if setting else '').strip()


def generate_review_token(record_id: int, action: str, secret: str = _DEFAULT_REVIEW_SECRET) -> str:
    """生成审核令牌，用于验证邮件中的审核链接
    
    Args:
        record_id: 结算记录ID
        action: 审核动作（approve/reject）
        secret: 签名密钥（默认使用内置值，建议通过 async_get_review_secret 从数据库读取后传入）
    
    Returns:
        令牌字符串
    """
    import hashlib
    # 使用简单的哈希作为签名，包含记录ID和动作
    data = f"{record_id}:{action}:{secret}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]
def verify_review_token(record_id: int, action: str, token: str, secret: str = _DEFAULT_REVIEW_SECRET) -> bool:
    """验证审核令牌
    
    Args:
        record_id: 结算记录ID
        action: 审核动作
        token: 待验证的字符串
        secret: 签名密钥
    
    Returns:
        是否验证通过
    """
    expected = generate_review_token(record_id, action, secret)
    return token == expected


async def async_get_review_secret() -> str:
    """从数据库读取审核令牌密钥，未配置时回退到内置默认值

    优先级：system_settings 表 > 内置默认值
    """
    try:
        from common.db.session import async_session_maker
        async with async_session_maker() as session:
            stmt = select(SystemSetting).where(SystemSetting.key == WITHDRAW_REVIEW_SECRET_KEY)
            result = await session.execute(stmt)
            setting = result.scalar_one_or_none()
            if setting and setting.value and setting.value.strip():
                return setting.value.strip()
    except Exception:
        pass
    return _DEFAULT_REVIEW_SECRET


async def review_withdraw_record(record_id: int, action: str, token: str, reject_reason: str = '') -> Dict[str, Any]:
    """审核提现记录（通过或拒绝）
    
    Args:
        record_id: 结算记录ID
        action: 审核动作（approve/reject）
        token: 审核令牌
    
    Returns:
        审核结果
    """
    from common.db.session import async_session_maker

    # 验证令牌（优先从数据库读取密钥）
    secret = await async_get_review_secret()
    if not verify_review_token(record_id, action, token, secret=secret):
        return {'success': False, 'message': '无效的审核令牌'}
    
    # 验证动作
    if action not in ('approve', 'reject'):
        return {'success': False, 'message': '无效的审核动作'}
    
    async with async_session_maker() as session:
        # 查询记录
        stmt = select(SettlementRecord).where(SettlementRecord.id == record_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            return {'success': False, 'message': '结算记录不存在'}
        
        if record.status != 'pending_review':
            status_map = {
                'approved': '已通过',
                'rejected': '已拒绝',
                'paid': '已打款',
            }
            current_status = status_map.get(record.status, record.status)
            return {'success': False, 'message': f'该记录已处理，当前状态：{current_status}'}
        
        # 更新状态
        if action == 'approve':
            record.status = 'approved'
            record.remark = (record.remark or '') + '\n管理员已通过审核'
            message = '提现申请已通过审核'
        else:
            record.status = 'rejected'
            record.remark = (record.remark or '') + '\n管理员已拒绝审核'
            if reject_reason:
                record.reject_reason = reject_reason.strip()
            # 扣减流水在用户点击提现时已确定，拒绝不退还余额
            message = '提现申请已拒绝'
        
        await session.commit()
        logger.info(f"提现审核完成: 记录ID={record_id}, 动作={action}")
        
        return {
            'success': True,
            'message': message,
            'data': {
                'id': record.id,
                'status': record.status,
                'amount': record.amount,
            }
        }
