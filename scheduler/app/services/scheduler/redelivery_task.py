"""
定时补发货任务

功能：
1. 查询符合条件的账号（启用+自动确认发货开启+定时补发货开启）
2. 查询当天未发货的订单
3. 检查订单是否可以发货（卡券配置、必要字段等）
4. 通过WebSocket服务发送发货消息
5. 记录执行日志
6. 对临时性错误的订单进行冷却，避免频繁重试
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import delete as sql_delete, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.scheduled_redelivery_log import ScheduledRedeliveryLog
from common.models.xy_account import XYAccount
from common.models.xy_order import XYOrder
from common.utils.time_utils import get_beijing_now_naive
from common.models.card import Card
from app.core.config import get_settings
from app.core.http_client import get_http_client


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


def add_order_to_cooldown(order_no: str, cooldown_seconds: int = ORDER_COOLDOWN_SECONDS) -> None:
    """
    将订单加入冷却缓存
    
    Args:
        order_no: 订单号
        cooldown_seconds: 冷却时间（秒），默认为 ORDER_COOLDOWN_SECONDS
    """
    expire_time = datetime.now() + timedelta(seconds=cooldown_seconds)
    _order_cooldown_cache[order_no] = expire_time
    logger.debug(f"[定时补发货] 订单 {order_no} 加入冷却 {cooldown_seconds}秒，过期时间: {expire_time}")


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
        logger.debug(f"[定时补发货] 清理了 {len(expired_orders)} 个过期冷却记录")


def should_add_to_cooldown(error_message: str) -> bool:
    """
    判断错误是否应该加入冷却队列
    
    临时性错误（应该冷却）：
    - 令牌过期
    - 网络超时
    - 服务繁忙
    
    永久性错误（不需要冷却）：
    - 订单已发货
    - 订单已关闭
    - 订单已完成
    
    Args:
        error_message: 错误信息
        
    Returns:
        True表示应该加入冷却，False表示不需要
    """
    if not error_message:
        return False
    
    error_lower = error_message.lower()
    
    # 临时性错误，应该冷却
    temp_errors = [
        '令牌过期',
        'token',
        'expired',
        '超时',
        'timeout',
        '繁忙',
        'busy',
        '限流',
        'rate limit',
        '网络',
        'network',
        '服务不可用',
        'unavailable',
        '无法获取订单状态',  # check_can_ship返回的错误，通常是令牌过期导致
        'api请求失败',  # API调用失败，可能是临时性问题
    ]
    
    for keyword in temp_errors:
        if keyword in error_lower:
            return True
    
    # 永久性错误，不需要冷却
    permanent_errors = [
        '已发货',
        '已完成',
        '已关闭',
        '交易关闭',
        '交易成功',
        'already',
        'closed',
        'completed',
    ]
    
    for keyword in permanent_errors:
        if keyword in error_lower:
            return False
    
    # 默认不加入冷却
    return False


class RedeliveryTask:
    """定时补发货任务"""
    
    # 订单处理间隔（秒）
    ORDER_PROCESS_DELAY = 1.0
    
    # 补发货日志保留天数，超过该天数的日志在每次任务执行时主动清理
    LOG_RETENTION_DAYS = 10
    
    async def execute(self) -> str:
        """
        执行补发货任务
        
        Returns:
            批次ID
        """
        batch_id = str(uuid.uuid4())
        logger.info(f"[定时补发货] 开始执行，批次ID: {batch_id}")
        
        # 清理过期的冷却记录
        cleanup_expired_cooldowns()
        
        try:
            async with async_session_maker() as session:
                # 主动清理过期的补发货日志（10天前）
                await self._cleanup_expired_logs(session)
                
                # 获取符合条件的账号
                accounts = await self._get_eligible_accounts(session)
                
                if not accounts:
                    logger.info("[定时补发货] 没有符合条件的账号")
                    return batch_id
                
                logger.info(f"[定时补发货] 找到 {len(accounts)} 个符合条件的账号")
                
                # 处理每个账号
                for account in accounts:
                    try:
                        await self._process_account(session, batch_id, account)
                    except Exception as e:
                        logger.error(f"[定时补发货] 处理账号 {account.account_id} 异常: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"[定时补发货] 执行异常: {e}")
        
        return batch_id
    
    async def _get_eligible_accounts(self, session: AsyncSession) -> List[XYAccount]:
        """
        获取符合条件的账号列表
        
        条件：
        - status = 'active'（启用）
        - auto_confirm = True（自动确认发货开启）
        - scheduled_redelivery = True（定时补发货开启）
        """
        stmt = select(XYAccount).where(
            XYAccount.status == "active",
            XYAccount.auto_confirm == True,
            XYAccount.scheduled_redelivery == True,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_pending_orders(
        self,
        session: AsyncSession,
        account_id: str
    ) -> List[XYOrder]:
        """
        获取待发货订单
        
        条件：
        - account_id 匹配
        - 真实下单时间(placed_at)在当天（不是数据库写入时间，
          避免同步历史订单时 created_at 被误判为今日订单）
        - placed_at 不为 NULL（历史空值数据跳过，防误伤）
        - 状态为 'pending_payment'（待付款）、'processing'（处理中）、'pending_ship'（待发货）
        """
        # 获取今天的开始时间（北京时间）
        now = get_beijing_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        stmt = select(XYOrder).where(
            XYOrder.account_id == account_id,
            XYOrder.placed_at.is_not(None),
            XYOrder.placed_at >= today_start,
            XYOrder.status.in_(["pending_payment", "processing", "pending_ship"]),
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
            logger.info(f"[定时补发货] 账号 {account_id} 处于Session过期冷却期内，跳过")
            return
        
        logger.info(f"[定时补发货] 开始处理账号: {account_id}")
        
        # 获取待发货订单
        orders = await self._get_pending_orders(session, account_id)
        
        if not orders:
            logger.info(f"[定时补发货] 账号 {account_id} 没有待发货订单")
            return
        
        logger.info(f"[定时补发货] 账号 {account_id} 找到 {len(orders)} 个待发货订单")
        
        # 使用可变cookie字符串，方便令牌过期刷新后后续订单使用最新cookie
        current_cookie_str = account.cookie
        
        # 处理每个订单
        for order in orders:
            # 检查订单是否在冷却期内
            if is_order_in_cooldown(order.order_no):
                logger.debug(f"[定时补发货] 订单 {order.order_no} 在冷却期内，跳过")
                continue
            
            try:
                success, error_message, updated_cookie = await self._process_order(session, account, order, current_cookie_str)
                
                # 如果cookie被刷新了，同步更新本地变量供后续订单使用
                if updated_cookie and updated_cookie != current_cookie_str:
                    current_cookie_str = updated_cookie
                    logger.info(f"[定时补发货] 账号 {account_id} Cookie已通过Set-Cookie更新，后续订单使用最新Cookie")
                
                # 如果处理失败，记录失败原因到订单表并判断是否需要加入冷却
                if not success and error_message:
                    # 并发占用提示不算发货失败，不记录失败原因
                    if "订单正在被其他进程处理" in error_message:
                        logger.info(f"[定时补发货] 订单 {order.order_no} 被其他进程处理，跳过记录失败原因")
                        await self._log_result(
                            session, batch_id, account_id, order.order_no, success, error_message
                        )
                        # 订单处理间隔
                        await asyncio.sleep(self.ORDER_PROCESS_DELAY)
                        continue

                    # 登录态异常时，标记账号冷却并触发后台异步密码登录
                    if (
                        "FAIL_SYS_TOKEN_EMPTY" in error_message
                        or "令牌为空" in error_message
                        or "已掉线" in error_message
                        or "请重新登录" in error_message
                        or "SESSION_EXPIRED" in error_message
                    ):
                        from common.utils.cookie_refresh import (
                            mark_account_session_expired, trigger_password_login_async
                        )
                        mark_account_session_expired(account_id)
                        trigger_password_login_async(account_id)
                        logger.warning(
                            f"[定时补发货] 账号 {account_id} 订单 {order.order_no} 登录态异常，"
                            f"已标记冷却并触发后台密码登录: {error_message}"
                        )
                    try:
                        from common.services.order_service import OrderService
                        order_svc = OrderService(session)
                        await order_svc.update_order_delivery_fail_reason(
                            order.order_no, error_message
                        )
                    except Exception as rec_err:
                        logger.warning(f"[定时补发货] 记录失败原因到订单表失败: {rec_err}")
                    
                    if should_add_to_cooldown(error_message):
                        add_order_to_cooldown(order.order_no)
                        logger.info(
                            f"[定时补发货] 订单 {order.order_no} 遇到临时错误，"
                            f"已加入冷却队列: {error_message}"
                        )
                
                await self._log_result(
                    session, batch_id, account_id, order.order_no, success, error_message
                )
                
                # 订单处理间隔
                await asyncio.sleep(self.ORDER_PROCESS_DELAY)
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[定时补发货] 处理订单 {order.order_no} 异常: {error_msg}")
                
                # 异常情况也判断是否需要加入冷却
                if should_add_to_cooldown(error_msg):
                    add_order_to_cooldown(order.order_no)
                
                await self._log_result(
                    session, batch_id, account_id, order.order_no, False, error_msg
                )
                continue
    
    async def _process_order(
        self,
        session: AsyncSession,
        account: XYAccount,
        order: XYOrder,
        cookie_str: str = None,
    ) -> tuple[bool, Optional[str], str]:
        """
        处理单个订单发货
        
        流程：
        1. 获取Redis分布式锁（防止与自动发货并发）
        2. 调用check_can_ship检查订单是否可以发货
        3. 检查是否有匹配的卡券
        4. 通过WebSocket服务发送发货消息
        
        Returns:
            (是否成功, 错误信息, 最新cookie字符串)
        """
        order_no = order.order_no
        account_id = order.account_id
        cookie_string = cookie_str or account.cookie
        
        logger.info(f"[定时补发货] 开始处理订单: {order_no}，当前状态: {order.status}")
        
        # 获取Redis分布式锁（防止与自动发货并发，Redis失败时降级继续执行）
        from common.db.redis_client import try_acquire_delivery_lock
        
        lock_result = None
        redis_lock_acquired = False
        try:
            lock_result = await try_acquire_delivery_lock(order_no, expire=120, holder_info="scheduler", wait_timeout=5)
            if lock_result.success:
                redis_lock_acquired = True
                logger.debug(f"[定时补发货] 获取Redis分布式锁成功: {order_no}")
            elif lock_result.is_locked_by_other:
                # 锁被其他进程持有，跳过本次处理
                logger.info(f"[定时补发货] 订单 {order_no} Redis分布式锁被其他进程持有（可能被自动发货处理中），跳过")
                return False, "订单正在被其他进程处理", cookie_string
            elif lock_result.has_error:
                # Redis连接异常，降级继续执行
                logger.warning(f"[定时补发货] Redis连接异常，降级继续执行: {order_no}")
        except Exception as e:
            logger.warning(f"[定时补发货] Redis分布式锁异常: {order_no}, error={e}，继续执行")
        
        try:
            # 获取锁后检查数据库订单状态，如果已发货则跳过
            if redis_lock_acquired:
                stmt = select(XYOrder).where(XYOrder.order_no == order_no)
                result = await session.execute(stmt)
                current_order = result.scalars().first()
                if current_order and current_order.status == 'shipped':
                    logger.info(f"[定时补发货] 获取锁后检查发现订单 {order_no} 已发货，跳过处理")
                    return True, "订单已发货，无需处理", cookie_string
            
            # 调用check_can_ship检查订单是否可以发货（传入account_id支持令牌过期自动刷新Cookie）
            from common.services.order_service import check_can_ship
            check_result = await check_can_ship(order_no, cookie_string, account_id=account_id)
            
            # 如果Cookie被刷新了，同步更新本地变量
            if check_result.get('cookies_str') and check_result['cookies_str'] != cookie_string:
                cookie_string = check_result['cookies_str']
                logger.info(f"[定时补发货] 账号 {account_id} Cookie已通过令牌刷新更新")
            
            if not check_result.get('success'):
                return False, check_result.get('reason', 'API请求失败'), cookie_string
            
            if not check_result.get('can_ship'):
                reason = check_result.get('reason', '订单状态不满足发货条件')
                order_status = check_result.get('order_status', '未知')
                logger.info(f"[定时补发货] 订单 {order_no} 不可发货: {reason}，闲鱼状态: {order_status}")

                # 如果订单已发货或已交易成功，只更新本地数据库状态，不触发实际发货
                if '已发货' in reason or '已交易成功' in reason:
                    stmt = sql_update(XYOrder).where(XYOrder.order_no == order_no).values(status="shipped")
                    await session.execute(stmt)
                    await session.commit()
                    logger.info(f"[定时补发货] 订单 {order_no} 闲鱼已发货，本地状态已同步为shipped")
                    return True, f"订单已发货，状态已同步（{reason}）", cookie_string

                # 订单已被关闭/取消：闲鱼侧已结束，本地状态由 check_can_ship 内部
                # _update_order_status_to_cancelled 同步为 'cancelled'。
                # 此处必须返回 success=True，否则外层 _process_account 会调
                # update_order_delivery_fail_reason 把订单的 delivery_fail_reason
                # 覆盖为"订单已关闭"，导致：
                #   - 卖家通过 pre_check 写入的"禁止发货原因"丢失
                #   - 卖家在闲鱼后台主动关闭订单时，原有的 fail_reason（如发货失败原因）丢失
                # 这是一个通用问题，不局限于 card_only 流程。
                if '已关闭' in reason or '已取消' in reason:
                    logger.info(
                        f"[定时补发货] 订单 {order_no} 已在闲鱼平台被关闭/取消（{reason}），"
                        f"本地状态已同步为 cancelled，不再处理，保留原有 delivery_fail_reason"
                    )
                    return True, f"订单已结束，状态已同步（{reason}）", cookie_string

                # 不满足发货条件的订单加入冷却2分钟，避免频繁检查
                add_order_to_cooldown(order_no, cooldown_seconds=120)
                return False, reason, cookie_string
            
            logger.info(f"[定时补发货] 订单 {order_no} 可以发货: {check_result.get('reason')}")
            
            # 检查订单金额和规格信息，缺失时从API重新获取
            need_api_fetch = False
            fetch_reasons = []
            
            if order.amount is not None:
                from decimal import Decimal
                if Decimal(str(order.amount)) <= 0:
                    need_api_fetch = True
                    fetch_reasons.append(f"金额为{order.amount}")
            
            if not order.spec_name or not order.spec_value:
                need_api_fetch = True
                fetch_reasons.append("缺少规格信息")
            
            if need_api_fetch:
                logger.info(f"[定时补发货] 订单 {order_no} {', '.join(fetch_reasons)}，尝试从API重新获取...")
                try:
                    from common.services.order_service import OrderStatusChecker
                    from decimal import Decimal
                    checker = OrderStatusChecker(cookie_string, account_id=order.account_id if hasattr(order, 'account_id') else None)
                    raw_detail = await checker._fetch_raw_order_detail(order_no)
                    if raw_detail:
                        # 使用完整的解析方法提取金额和规格
                        parsed = checker._parse_order_detail_response(order_no, raw_detail)
                        if parsed:
                            updated_fields = []
                            # 更新金额
                            real_amount = parsed.get('amount', '')
                            if real_amount and Decimal(str(real_amount)) > 0:
                                order.amount = Decimal(str(real_amount))
                                updated_fields.append(f"金额={real_amount}")
                            # 更新规格信息
                            api_spec_name = parsed.get('spec_name', '')
                            api_spec_value = parsed.get('spec_value', '')
                            if api_spec_name and api_spec_value:
                                order.spec_name = api_spec_name
                                order.spec_value = api_spec_value
                                updated_fields.append(f"规格={api_spec_name}:{api_spec_value}")
                            
                            if updated_fields:
                                await session.commit()
                                logger.info(f"[定时补发货] 订单 {order_no} 已从API更新: {', '.join(updated_fields)}，继续发货")
                            
                            # 如果Cookie被刷新了，同步更新
                            if checker.cookies_str != cookie_string:
                                cookie_string = checker.cookies_str
                            
                            # 更新后再次检查金额
                            if order.amount is not None and Decimal(str(order.amount)) <= 0:
                                logger.warning(f"[定时补发货] ❌ 订单 {order_no} API确认金额为0，禁止发货")
                                return False, f"订单金额为0，禁止发货（API确认）", cookie_string
                        else:
                            # 解析失败，如果是金额问题则禁止发货
                            if order.amount is not None and Decimal(str(order.amount)) <= 0:
                                logger.warning(f"[定时补发货] ❌ 订单 {order_no} API响应解析失败，金额为0禁止发货")
                                return False, f"订单金额为0，禁止发货（API响应解析失败）", cookie_string
                    else:
                        # API查询失败，如果是金额问题则禁止发货
                        if order.amount is not None and Decimal(str(order.amount)) <= 0:
                            logger.warning(f"[定时补发货] ❌ 订单 {order_no} 金额为 {order.amount} 且无法从API获取，禁止发货")
                            return False, f"订单金额为0，禁止发货（API查询失败）", cookie_string
                except Exception as fetch_exc:
                    logger.warning(f"[定时补发货] 订单 {order_no} 从API重新获取异常: {fetch_exc}")
                    # 如果是金额问题则禁止发货
                    if order.amount is not None:
                        from decimal import Decimal
                        if Decimal(str(order.amount)) <= 0:
                            return False, f"订单金额为0，禁止发货（{fetch_exc}）", cookie_string

            # 检查订单必要字段
            if not order.item_id:
                return False, "订单缺少商品ID", cookie_string
            if not order.buyer_id:
                return False, "订单缺少买家ID", cookie_string
            # 订单缺少会话ID时，先调用 WebSocket 服务自动创建会话并回写，再继续发货
            if not order.chat_id:
                chat_ok, chat_error = await self._ensure_chat_id(session, order)
                if not chat_ok:
                    return False, chat_error or "订单缺少会话ID", cookie_string
            
            # 占位chat_id（创建会话失败时写入的）不能用于发货
            if order.chat_id and order.chat_id.startswith("FAILED_"):
                return False, "会话创建失败（占位ID），跳过发货", cookie_string
            
            # 检查是否有匹配的卡券
            card = await self._get_matching_card(session, order)
            if not card:
                return False, "未找到匹配的卡券", cookie_string
            
            # 调用WebSocket服务进行发货
            try:
                settings = get_settings()
                http_client = get_http_client()

                # 重新从数据库读取 quantity，避免 ORM 缓存竞态：
                # scheduler 在 _get_pending_orders 阶段就把订单读入 SQLAlchemy identity map，
                # 期间 websocket 服务的 fetch_and_update_order_detail（独立进程）可能已把 DB 中的
                # quantity 从默认值 1 更新为真实值（如买家下了 2 件），但 ORM 缓存里的
                # order.quantity 仍是 1，会导致多数量订单只发 1 张卡密。
                # 单独 SELECT 读取，不依赖 ORM 缓存状态。
                order_quantity = int(order.quantity) if order.quantity and order.quantity > 0 else 1
                try:
                    fresh_qty_stmt = select(XYOrder.quantity).where(XYOrder.order_no == order_no)
                    fresh_qty_result = await session.execute(fresh_qty_stmt)
                    fresh_qty = fresh_qty_result.scalar_one_or_none()
                    if fresh_qty is not None and int(fresh_qty) > 0:
                        fresh_qty_int = int(fresh_qty)
                        if fresh_qty_int != order_quantity:
                            logger.info(
                                f"[定时补发货] 订单 {order_no} quantity 已从 DB 刷新: "
                                f"ORM 缓存={order_quantity} → DB 最新={fresh_qty_int}"
                            )
                            order.quantity = fresh_qty_int  # 同步内存对象
                            order_quantity = fresh_qty_int
                except Exception as qty_err:
                    logger.warning(
                        f"[定时补发货] 订单 {order_no} 刷新 quantity 失败，"
                        f"使用 ORM 缓存值 {order_quantity}: {qty_err}"
                    )

                # 构建发货请求
                # quantity 用于多数量订单的循环补发，与自动发货 multi_quantity_delivery 行为对齐：
                # 买家下 N 件时一次性补发 N 张卡密
                deliver_url = f"{settings.websocket_service_url}/internal/orders/deliver"
                deliver_data = {
                    "order_no": order_no,
                    "item_id": order.item_id,
                    "buyer_id": order.buyer_id,
                    "chat_id": order.chat_id,
                    "card_id": card.id,
                    "is_bargain": order.is_bargain or False,
                    "delivery_method": "scheduled",
                    "quantity": order_quantity,
                }
                
                logger.info(f"[定时补发货] 调用WebSocket服务发货: {order_no}")
                result = await http_client.post(deliver_url, json=deliver_data)
                logger.info(f"[定时补发货] 订单 {order_no} 接口返回: {result}")
                
                if result.get('success'):
                    result_data = result.get('data') or {}
                    # is_card_only=True 表示 internal API 走了「禁止发货 + 主动关闭订单 + 仅发卡券」流程：
                    # 订单已被卖家在闲鱼平台主动关闭，本地状态由 internal API 内部的
                    # record_delivery_for_closed_order 维持为 'closed'，并保留 delivery_fail_reason，
                    # 这里若再覆盖为 'shipped' 会让本地状态与平台不一致，且丢失禁止发货原因。
                    if result_data.get('is_card_only'):
                        logger.info(
                            f"[定时补发货] 订单 {order_no} card_only 模式：卡券已补发，"
                            f"订单已被关闭，本地状态保持不变，不覆盖为 shipped"
                        )
                        # 仍返回 True，避免任务重复触发；视为本次处理完成
                        return True, None, cookie_string

                    # 更新订单状态为已发货
                    order.status = "shipped"
                    order.delivery_method = "scheduled"
                    order.delivery_content = result_data.get('content', '')
                    await session.commit()

                    # 多数量退化提示：订单 quantity>1 但因卡券类型限制只发了 1 张，
                    # 把提示写入 delivery_fail_reason 让商家在订单列表看到原因
                    degraded_warn_msg: Optional[str] = None
                    if result_data.get('quantity_degraded_for_dock_card'):
                        # 对接卡券退化：建议手动补发或改用自有卡券
                        requested = result_data.get('quantity_requested') or order.quantity or 1
                        sent = result_data.get('quantity_sent') or 1
                        degraded_warn_msg = (
                            f"⚠️ 对接卡券暂不支持多数量发货：订单数量 {requested} 张，"
                            f"已自动发送 {sent} 张，剩余 {max(requested - sent, 0)} 张请手动补发或改用自有卡券"
                        )
                    elif result_data.get('quantity_degraded_for_fixed_content'):
                        # text/image 固定内容卡券退化：建议改用 data/api 类型
                        requested = result_data.get('quantity_requested') or order.quantity or 1
                        sent = result_data.get('quantity_sent') or 1
                        degraded_warn_msg = (
                            f"⚠️ 固定内容卡券（{result_data.get('delivery_type')} 类型）不支持多数量发货："
                            f"订单数量 {requested} 张，仅发送 1 张固定内容（剩余 {max(requested - sent, 0)} 张未发）。"
                            f"如需多数量发送不同卡密，请改用 data 或 api 类型卡券"
                        )

                    if degraded_warn_msg:
                        try:
                            from common.services.order_service import OrderService
                            order_svc = OrderService(session)
                            await order_svc.update_order_delivery_fail_reason(order_no, degraded_warn_msg)
                            logger.warning(f"[定时补发货] 订单 {order_no} {degraded_warn_msg}")
                        except Exception as warn_err:
                            logger.warning(
                                f"[定时补发货] 订单 {order_no} 写入多数量退化提示失败: {warn_err}"
                            )

                    # 卡券疑似被平台风控拦截未送达：internal API 已等待闲鱼服务端回执判定，
                    # 并把拦截原因写入订单 delivery_fail_reason。订单已标记 shipped（库存已扣，
                    # 不自动重发以免资损/再次被同一风控拦截，下轮也不会再捞取），
                    # 这里把补发货批次日志记为失败（返回 success=False），提示人工核实买家是否收到。
                    if result_data.get('send_intercepted'):
                        intercept_reason = (
                            result_data.get('send_intercept_reason')
                            or "卡券疑似被平台风控拦截未送达，请人工核实买家是否收到"
                        )
                        # 若同时存在多数量退化提示，合并写入，避免外层覆盖 delivery_fail_reason 时丢失
                        final_reason = (
                            f"{degraded_warn_msg}；{intercept_reason}" if degraded_warn_msg else intercept_reason
                        )
                        logger.warning(
                            f"[定时补发货] 订单 {order_no} 卡券疑似被平台拦截，"
                            f"已标记发货但批次日志记为失败: {final_reason}"
                        )
                        return False, final_reason, cookie_string

                    logger.info(f"[定时补发货] 订单 {order_no} 发货成功")
                    return True, None, cookie_string
                else:
                    error_msg = result.get('message', '发货失败')
                    logger.warning(f"[定时补发货] 订单 {order_no} 发货失败: {error_msg}")
                    return False, error_msg, cookie_string
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[定时补发货] 调用WebSocket服务异常: {error_msg}")
                return False, f"调用发货服务异常: {error_msg}", cookie_string
        
        finally:
            # 主动释放Redis分布式锁
            if redis_lock_acquired and lock_result:
                try:
                    from common.db.redis_client import release_delivery_lock
                    released = await release_delivery_lock(lock_result)
                    if released:
                        logger.debug(f"[定时补发货] Redis分布式锁已释放: {order_no}")
                    else:
                        logger.warning(f"[定时补发货] Redis分布式锁释放失败: {order_no}")
                except Exception as e:
                    logger.warning(f"[定时补发货] Redis分布式锁释放异常: {order_no}, error={e}")
    
    async def _ensure_chat_id(
        self,
        session: AsyncSession,
        order: XYOrder,
    ) -> tuple[bool, Optional[str]]:
        """
        订单缺少 chat_id 时，通过 WebSocket 服务创建单聊会话并回写订单。
        
        流程：
        1. 调用 websocket 服务 /internal/accounts/{account_id}/create-chat 接口
        2. 服务端通过 LWP 协议 /r/SingleChatConversation/create 创建或获取会话（幂等）
        3. 返回的 chat_id 通过 OrderService 回写到 xy_orders 表
        4. 同步内存对象 order.chat_id，供后续发货逻辑使用
        
        与 backend-web 手动发货保持一致的处理方式，确保补发货也能自动补齐 chat_id。
        
        Args:
            session: 数据库会话（用于回写订单）
            order: 订单对象
        
        Returns:
            (是否成功, 错误信息)
        """
        try:
            settings = get_settings()
            http_client = get_http_client()
            
            create_url = (
                f"{settings.websocket_service_url}"
                f"/internal/accounts/{order.account_id}/create-chat"
            )
            create_payload = {
                "buyer_id": order.buyer_id,
                "item_id": order.item_id,
            }
            
            logger.info(
                f"[定时补发货] 订单 {order.order_no} 缺少会话ID，"
                f"调用 WebSocket 服务创建会话: buyer_id={order.buyer_id}, item_id={order.item_id}"
            )
            result = await http_client.post(create_url, json=create_payload)
            
            if not result.get("success"):
                error_msg = result.get("message", "创建会话失败")
                logger.warning(
                    f"[定时补发货] 订单 {order.order_no} 创建会话失败: {error_msg}，"
                    f"写入占位chat_id避免重复尝试"
                )
                # 写入占位chat_id，避免下次定时任务再次尝试创建
                placeholder_chat_id = f"FAILED_{order.buyer_id}"
                from common.services.order_service import OrderService
                order_svc = OrderService(session)
                await order_svc.update_order_chat_id(order.order_no, placeholder_chat_id)
                order.chat_id = placeholder_chat_id
                return False, f"创建会话失败: {error_msg}"
            
            new_chat_id = (result.get("data") or {}).get("chat_id")
            if not new_chat_id:
                logger.warning(
                    f"[定时补发货] 订单 {order.order_no} 创建会话响应缺少 chat_id: {result}，"
                    f"写入占位chat_id避免重复尝试"
                )
                # 写入占位chat_id，避免下次定时任务再次尝试创建
                placeholder_chat_id = f"FAILED_{order.buyer_id}"
                from common.services.order_service import OrderService
                order_svc = OrderService(session)
                await order_svc.update_order_chat_id(order.order_no, placeholder_chat_id)
                order.chat_id = placeholder_chat_id
                return False, "创建会话响应缺少 chat_id"
            
            # 回写订单 chat_id
            from common.services.order_service import OrderService
            order_svc = OrderService(session)
            updated = await order_svc.update_order_chat_id(
                order.order_no, new_chat_id
            )
            if not updated:
                logger.warning(
                    f"[定时补发货] 订单 {order.order_no} 会话ID回写数据库失败: "
                    f"chat_id={new_chat_id}"
                )
                return False, "会话ID回写数据库失败"
            
            # 同步内存对象（ORM identity map 不会自动感知上面的 UPDATE 语句）
            order.chat_id = new_chat_id
            logger.info(
                f"[定时补发货] 订单 {order.order_no} 会话ID创建并回写成功: "
                f"chat_id={new_chat_id}"
            )
            return True, None
        
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"[定时补发货] 订单 {order.order_no} 创建会话异常: {error_msg}"
            )
            return False, f"创建会话异常: {error_msg}"
    
    async def _get_matching_card(
        self,
        session: AsyncSession,
        order: XYOrder
    ) -> Optional[Card]:
        """
        获取订单匹配的卡券（委托给 CardMatcher 统一逻辑）
        
        匹配规则：
        1. 通过关联表查询，含向后兼容回退
        2. 卡券已启用
        3. 如果是多规格卡券，规格需要匹配
        4. 必须唯一匹配（只有一个卡券匹配）
        
        Returns:
            匹配的卡券或None
        """
        from common.services.card_matcher import CardMatcher
        
        item_id = order.item_id
        spec_name = order.spec_name
        spec_value = order.spec_value
        
        matcher = CardMatcher(session)
        matched_cards = await matcher.get_cards_by_item_id(item_id, spec_name, spec_value)
        
        if not matched_cards:
            logger.info(f"[定时补发货] 商品 {item_id} 没有匹配的卡券")
            return None
        
        # 必须唯一匹配
        if len(matched_cards) > 1:
            card_names = [c.get('name') for c in matched_cards]
            logger.info(f"[定时补发货] 商品 {item_id} 匹配到多个卡券: {card_names}，需要唯一匹配")
            return None
        
        # 从字典中获取卡券ID，再查询完整的Card对象
        card_id = matched_cards[0].get('id')
        stmt = select(Card).where(Card.id == card_id)
        result = await session.execute(stmt)
        return result.scalars().first()
    
    async def _cleanup_expired_logs(self, session: AsyncSession) -> None:
        """
        主动清理过期的补发货日志

        删除 created_at 早于 (当前北京时间 - LOG_RETENTION_DAYS 天) 的日志记录，
        避免日志表无限增长。使用参数化的 ORM delete 语句，避免 SQL 注入。
        """
        try:
            cutoff_time = get_beijing_now_naive() - timedelta(days=self.LOG_RETENTION_DAYS)
            stmt = sql_delete(ScheduledRedeliveryLog).where(
                ScheduledRedeliveryLog.created_at < cutoff_time
            )
            result = await session.execute(stmt)
            await session.commit()

            deleted_count = result.rowcount or 0
            if deleted_count > 0:
                logger.info(
                    f"[定时补发货] 已清理 {deleted_count} 条 {self.LOG_RETENTION_DAYS} 天前的补发货日志"
                    f"（清理时间界限: {cutoff_time}）"
                )
        except Exception as e:
            logger.error(f"[定时补发货] 清理过期日志失败: {e}")
            await session.rollback()

    async def _log_result(
        self,
        session: AsyncSession,
        batch_id: str,
        account_id: str,
        order_no: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """记录执行日志"""
        try:
            log = ScheduledRedeliveryLog(
                batch_id=batch_id,
                account_id=account_id,
                order_no=order_no,
                status="success" if success else "failed",
                error_message=error_message[:500] if error_message else None,
            )
            session.add(log)
            await session.commit()
            
            # 只有成功时才打印INFO日志，失败时打印DEBUG日志
            if success:
                logger.info(f"[定时补发货] 订单 {order_no} 处理成功")
            else:
                logger.debug(f"[定时补发货] 订单 {order_no} 处理失败: {error_message}")
            
        except Exception as e:
            logger.error(f"[定时补发货] 记录日志失败: {e}")
            await session.rollback()
