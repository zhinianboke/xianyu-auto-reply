"""
定时补评价任务

功能：
1. 查询符合条件的账号（启用+定时补评价开启）
2. 查询已发货和已完成的订单
3. 调用check_can_rate检查是否可以评价
4. 执行评价操作
5. 记录执行日志到scheduled_rate_log表
6. 对不能评价的订单进行冷却，10分钟内不再重复处理
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.models.xy_order import XYOrder
from common.models.scheduled_rate_log import ScheduledRateLog
from common.utils.time_utils import get_beijing_now_naive


# 全局冷却缓存：订单号 -> 冷却过期时间
_order_cooldown_cache: Dict[str, datetime] = {}

# 冷却时间（秒）
ORDER_COOLDOWN_SECONDS = 600  # 10分钟


def is_order_in_cooldown(order_no: str) -> bool:
    """
    检查订单是否在冷却期内
    
    Args:
        order_no: 订单号
        
    Returns:
        True表示在冷却期内，False表示可以处理
    """
    if order_no not in _order_cooldown_cache:
        return False
    
    expire_time = _order_cooldown_cache[order_no]
    if datetime.now() >= expire_time:
        # 冷却已过期，移除缓存
        del _order_cooldown_cache[order_no]
        return False
    
    return True


def add_order_to_cooldown(order_no: str) -> None:
    """
    将订单加入冷却缓存
    
    Args:
        order_no: 订单号
    """
    expire_time = datetime.now() + timedelta(seconds=ORDER_COOLDOWN_SECONDS)
    _order_cooldown_cache[order_no] = expire_time
    logger.debug(f"[定时补评价] 订单 {order_no} 加入冷却，过期时间: {expire_time}")


def cleanup_expired_cooldowns() -> None:
    """清理已过期的冷却记录"""
    now = datetime.now()
    expired_orders = [
        order_no for order_no, expire_time in _order_cooldown_cache.items()
        if now >= expire_time
    ]
    for order_no in expired_orders:
        del _order_cooldown_cache[order_no]
    
    if expired_orders:
        logger.debug(f"[定时补评价] 清理了 {len(expired_orders)} 个过期的冷却记录")


class RateTask:
    """定时补评价任务"""
    
    # 订单处理间隔（秒）
    ORDER_PROCESS_DELAY = 2.0
    
    # 补评价日志保留天数，超过该天数的日志在每次任务执行时主动清理
    LOG_RETENTION_DAYS = 10
    
    async def execute(self) -> str:
        """
        执行补评价任务
        
        Returns:
            批次ID
        """
        batch_id = str(uuid.uuid4())
        logger.debug(f"[定时补评价] 开始执行，批次ID: {batch_id}")
        
        # 清理过期的冷却记录
        cleanup_expired_cooldowns()
        
        try:
            async with async_session_maker() as session:
                # 主动清理过期的补评价日志（10天前）
                await self._cleanup_expired_logs(session)
                
                # 获取符合条件的账号
                accounts = await self._get_eligible_accounts(session)
                
                if not accounts:
                    logger.debug("[定时补评价] 没有符合条件的账号")
                    return batch_id
                
                logger.debug(f"[定时补评价] 找到 {len(accounts)} 个符合条件的账号")
                
                # 处理每个账号
                for account in accounts:
                    try:
                        await self._process_account(session, batch_id, account)
                    except Exception as e:
                        logger.error(f"[定时补评价] 处理账号 {account.account_id} 异常: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"[定时补评价] 执行异常: {e}")
        
        return batch_id
    
    async def _get_eligible_accounts(self, session: AsyncSession) -> List[XYAccount]:
        """
        获取符合条件的账号列表
        
        条件：
        - status = 'active'（启用）
        - scheduled_rate = True（定时补评价开启）
        - 自动评价配置已启用（AutoRateConfig.enabled = True）
        """
        from common.models.auto_rate_config import AutoRateConfig
        
        # 联表查询：账号表 + 自动评价配置表
        stmt = (
            select(XYAccount)
            .join(AutoRateConfig, XYAccount.account_id == AutoRateConfig.account_id)
            .where(
                XYAccount.status == "active",
                XYAccount.scheduled_rate == True,
                AutoRateConfig.enabled == True,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_pending_rate_orders(
        self,
        session: AsyncSession,
        account_id: str
    ) -> List[XYOrder]:
        """
        获取待评价订单
        
        条件：
        - account_id 匹配
        - 真实下单时间(placed_at)在当天（不是数据库写入时间，
          避免同步历史订单时 created_at 被误判为今日订单）
        - placed_at 不为 NULL（历史空值数据跳过，防误伤）
        - 状态为 'shipped'（已发货）或 'completed'（已完成）
        - 未评价（is_rated = False 或 NULL）
        """
        # 获取今天的开始时间（北京时间）
        now = get_beijing_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        stmt = select(XYOrder).where(
            XYOrder.account_id == account_id,
            XYOrder.placed_at.is_not(None),
            XYOrder.placed_at >= today_start,
            XYOrder.status.in_(["shipped", "completed"]),
            (XYOrder.is_rated == False) | (XYOrder.is_rated == None),
        ).order_by(XYOrder.placed_at)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def _process_account(
        self,
        session: AsyncSession,
        batch_id: str,
        account: XYAccount
    ) -> None:
        """处理单个账号"""
        account_id = account.account_id
        
        # 检查账号是否处于Session过期冷却期内
        from common.utils.cookie_refresh import is_account_session_cooled
        if is_account_session_cooled(account_id):
            logger.info(f"[定时补评价] 账号 {account_id} 处于Session过期冷却期内，跳过")
            return
        
        logger.debug(f"[定时补评价] 开始处理账号: {account_id}")
        
        # 检查账号是否有Cookie
        if not account.cookie:
            logger.debug(f"[定时补评价] 账号 {account_id} 没有Cookie，跳过")
            return
        
        # 获取待评价订单
        orders = await self._get_pending_rate_orders(session, account_id)
        
        if not orders:
            logger.debug(f"[定时补评价] 账号 {account_id} 没有待评价订单")
            return
        
        logger.debug(f"[定时补评价] 账号 {account_id} 找到 {len(orders)} 个待评价订单")
        
        # 使用可变cookie字符串，方便令牌过期刷新后后续订单使用最新cookie
        current_cookie_str = account.cookie
        
        # 处理每个订单
        for order in orders:
            # 检查订单是否在冷却期内
            if is_order_in_cooldown(order.order_no):
                logger.debug(f"[定时补评价] 订单 {order.order_no} 在冷却期内，跳过")
                continue
            
            try:
                success, error_message, updated_cookie = await self._process_order(account, order, current_cookie_str)
                
                # 如果cookie被刷新了，同步更新本地变量供后续订单使用
                if updated_cookie and updated_cookie != current_cookie_str:
                    current_cookie_str = updated_cookie
                    logger.info(f"[定时补评价] 账号 {account_id} Cookie已通过Set-Cookie更新，后续订单使用最新Cookie")
                
                # 如果处理失败且不是已评价的情况，加入冷却
                if not success and error_message and '已评价' not in error_message:
                    add_order_to_cooldown(order.order_no)
                
                # 记录日志到数据库
                await self._save_log(
                    session=session,
                    batch_id=batch_id,
                    account_id=account_id,
                    order_no=order.order_no,
                    success=success,
                    error_message=error_message
                )
                
                # 订单处理间隔
                await asyncio.sleep(self.ORDER_PROCESS_DELAY)
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[定时补评价] 处理订单 {order.order_no} 异常: {error_msg}")
                # 异常情况也加入冷却
                add_order_to_cooldown(order.order_no)
                # 记录异常日志
                await self._save_log(
                    session=session,
                    batch_id=batch_id,
                    account_id=account_id,
                    order_no=order.order_no,
                    success=False,
                    error_message=error_msg
                )
                continue
    
    async def _cleanup_expired_logs(self, session: AsyncSession) -> None:
        """
        主动清理过期的补评价日志

        删除 created_at 早于 (当前北京时间 - LOG_RETENTION_DAYS 天) 的日志记录，
        避免日志表无限增长。使用参数化的 ORM delete 语句，避免 SQL 注入。
        """
        try:
            cutoff_time = get_beijing_now_naive() - timedelta(days=self.LOG_RETENTION_DAYS)
            stmt = sql_delete(ScheduledRateLog).where(
                ScheduledRateLog.created_at < cutoff_time
            )
            result = await session.execute(stmt)
            await session.commit()

            deleted_count = result.rowcount or 0
            if deleted_count > 0:
                logger.info(
                    f"[定时补评价] 已清理 {deleted_count} 条 {self.LOG_RETENTION_DAYS} 天前的补评价日志"
                    f"（清理时间界限: {cutoff_time}）"
                )
        except Exception as e:
            logger.error(f"[定时补评价] 清理过期日志失败: {e}")
            await session.rollback()

    async def _save_log(
        self,
        session: AsyncSession,
        batch_id: str,
        account_id: str,
        order_no: str,
        success: bool,
        error_message: Optional[str]
    ) -> None:
        """保存执行日志到数据库"""
        try:
            log = ScheduledRateLog(
                batch_id=batch_id,
                account_id=account_id,
                order_no=order_no,
                status="success" if success else "failed",
                error_message=error_message[:500] if error_message else None
            )
            session.add(log)
            await session.commit()
            
            # 只有成功时才打印INFO日志，失败时打印DEBUG日志
            if success:
                logger.info(f"[定时补评价] 订单 {order_no} 处理成功")
            else:
                logger.debug(f"[定时补评价] 订单 {order_no} 处理失败: {error_message}")
        except Exception as e:
            logger.error(f"[定时补评价] 保存日志失败: {e}")
            await session.rollback()
    
    async def _process_order(
        self,
        account: XYAccount,
        order: XYOrder,
        cookie_str: str = None,
    ) -> tuple[bool, Optional[str], str]:
        """
        处理单个订单评价
        
        流程：
        1. 检查商品是否属于当前账号
        2. 调用check_can_rate检查订单是否可以评价
        3. 如果可以评价，获取评价内容并执行评价
        
        Returns:
            (是否成功, 错误信息, 最新cookie字符串)
        """
        order_no = order.order_no
        account_id = account.account_id
        cookie_string = cookie_str or account.cookie
        item_id = order.item_id
        
        logger.debug(f"[定时补评价] 开始处理订单: {order_no}，商品ID: {item_id}，当前状态: {order.status}")
        
        # 检查商品是否属于当前账号（只有商品ID存在时才检查）
        if item_id:
            belongs_to_account = await self._check_item_belongs_to_account(account.id, item_id)
            if not belongs_to_account:
                logger.info(f"[定时补评价] 商品 {item_id} 不属于账号 {account_id}，跳过评价")
                return False, f"商品 {item_id} 不属于当前账号", cookie_string
        # 商品ID不存在时继续执行原有逻辑
        
        # 调用check_can_rate检查订单是否可以评价（传入account_id支持令牌过期自动刷新Cookie）
        from common.services.order_service import check_can_rate
        check_result = await check_can_rate(order_no, cookie_string, account_id=account_id)
        
        # 如果Cookie被刷新了，同步更新本地变量
        if check_result.get('cookies_str') and check_result['cookies_str'] != cookie_string:
            cookie_string = check_result['cookies_str']
            logger.info(f"[定时补评价] 账号 {account_id} Cookie已通过令牌刷新更新")
        
        if not check_result.get('success'):
            return False, check_result.get('reason', 'API请求失败'), cookie_string
        
        if not check_result.get('can_rate'):
            reason = check_result.get('reason', '订单状态不满足评价条件')
            order_status = check_result.get('order_status', '未知')
            logger.info(f"[定时补评价] 订单 {order_no} 不可评价: {reason}，闲鱼状态: {order_status}")
            
            # 如果订单已评价，只更新本地数据库状态，不触发实际评价
            if '已评价' in reason:
                from common.services.rate_service import update_order_rated_status
                await update_order_rated_status(order_no, True)
                logger.info(f"[定时补评价] 订单 {order_no} 闲鱼已评价，本地状态已同步")
                return True, f"订单已评价，状态已同步（{reason}）", cookie_string
            
            return False, reason, cookie_string
        
        logger.info(f"[定时补评价] 订单 {order_no} 可以评价: {check_result.get('reason')}")
        
        # 获取评价内容
        from common.services.rate_service import get_rate_feedback_content
        feedback = await get_rate_feedback_content(account_id)
        if not feedback:
            return False, "获取评价内容失败或自动评价未启用", cookie_string
        
        logger.info(f"[定时补评价] 订单 {order_no} 评价内容: {feedback[:30]}...")
        
        # 直接调用RateService执行评价（传入account_id支持令牌过期自动刷新Cookie）
        try:
            from common.services.rate_service import RateService, update_order_rated_status
            
            rate_service = RateService(cookie_string, account_id=account_id)
            result = await rate_service.rate_buyer(order_no, feedback=feedback)
            
            if result.get('success'):
                # 更新订单评价状态
                await update_order_rated_status(order_no, True)
                logger.info(f"[定时补评价] 订单 {order_no} 评价成功")
                return True, None, cookie_string
            else:
                error_msg = result.get('message', '评价失败')
                logger.warning(f"[定时补评价] 订单 {order_no} 评价失败: {error_msg}")
                
                # 超出30天不允许评价等永久性错误，标记为已评价，避免反复重试
                if '不允许评价' in error_msg or '超出' in error_msg:
                    await update_order_rated_status(order_no, True)
                    logger.info(f"[定时补评价] 订单 {order_no} 已超期不可评价，标记为已评价")
                
                return False, error_msg, cookie_string
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[定时补评价] 订单 {order_no} 评价异常: {error_msg}")
            return False, error_msg, cookie_string
    
    async def _check_item_belongs_to_account(self, account_pk: int, item_id: str) -> bool:
        """检查商品是否属于指定账号
        
        Args:
            account_pk: 账号主键ID
            item_id: 商品ID
            
        Returns:
            True表示商品属于该账号，False表示不属于
        """
        try:
            from common.models.xy_catalog_item import XYCatalogItem
            
            async with async_session_maker() as session:
                stmt = select(XYCatalogItem).where(
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == item_id
                )
                result = await session.execute(stmt)
                item = result.scalars().first()
                return item is not None
                
        except Exception as e:
            logger.error(f"[定时补评价] 检查商品归属失败: account_pk={account_pk}, item_id={item_id}, error={e}")
            return False
