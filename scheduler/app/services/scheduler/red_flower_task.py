"""
定时求小红花任务

功能：
1. 查询所有开启自动求小红花的账号
2. 获取每个账号近10天内未求小红花的订单
3. 调用闲鱼求小红花API
4. 处理响应Set-Cookie，合并更新到数据库
5. 令牌过期时从Set-Cookie提取新Cookie，更新数据库后自动重试一次
6. Session过期时标记冷却并触发后台密码登录
7. 更新订单 is_red_flower 字段
8. 记录执行日志
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
from loguru import logger
from sqlalchemy import delete as sql_delete, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.scheduled_red_flower_log import ScheduledRedFlowerLog
from common.models.xy_account import XYAccount
from common.models.xy_order import XYOrder
from common.utils.time_utils import get_beijing_now_naive
from common.utils.xianyu_utils import trans_cookies, generate_sign
from common.utils.cookie_refresh import (
    is_token_expired_error, handle_token_expired_response,
    update_account_cookies_in_db,
    is_session_expired_error, trigger_password_login_async,
    mark_account_session_expired, extract_cookies_from_response,
    merge_cookies, is_account_session_cooled,
)


# 全局冷却缓存：订单号 -> 冷却过期时间
_order_cooldown_cache: Dict[str, datetime] = {}

# 冷却时间（秒）
ORDER_COOLDOWN_SECONDS = 600  # 10分钟


def is_order_in_cooldown(order_no: str) -> bool:
    """检查订单是否在冷却期内"""
    if order_no not in _order_cooldown_cache:
        return False
    expire_time = _order_cooldown_cache[order_no]
    if datetime.now() >= expire_time:
        del _order_cooldown_cache[order_no]
        return False
    return True


def add_order_to_cooldown(order_no: str, cooldown_seconds: int = ORDER_COOLDOWN_SECONDS) -> None:
    """将订单加入冷却缓存"""
    expire_time = datetime.now() + timedelta(seconds=cooldown_seconds)
    _order_cooldown_cache[order_no] = expire_time
    logger.info(f"[求小红花] 订单 {order_no} 加入冷却 {cooldown_seconds}秒")


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
        logger.info(f"[求小红花] 清理了 {len(expired_orders)} 个过期冷却记录")


class RedFlowerTask:
    """定时求小红花任务"""

    # 订单处理间隔（秒），避免请求过快被限流
    ORDER_PROCESS_DELAY = 0.5
    # HTTP请求超时（秒）
    REQUEST_TIMEOUT = 30
    # 求小红花日志保留天数，超过该天数的日志在每次任务执行时主动清理
    LOG_RETENTION_DAYS = 10

    async def execute(self) -> str:
        """
        执行求小红花任务

        Returns:
            批次ID
        """
        batch_id = str(uuid.uuid4())
        logger.info(f"[求小红花] 开始执行，批次ID: {batch_id}")

        # 清理过期冷却记录
        cleanup_expired_cooldowns()

        try:
            async with async_session_maker() as session:
                # 主动清理过期的求小红花日志（10天前）
                await self._cleanup_expired_logs(session)

                # 获取符合条件的账号
                accounts = await self._get_eligible_accounts(session)

                if not accounts:
                    logger.info("[求小红花] 没有符合条件的账号")
                    return batch_id

                logger.info(f"[求小红花] 找到 {len(accounts)} 个符合条件的账号")

                # 处理每个账号
                for account in accounts:
                    try:
                        await self._process_account(session, batch_id, account)
                    except Exception as e:
                        logger.error(f"[求小红花] 处理账号 {account.account_id} 异常: {e}")
                        continue

        except Exception as e:
            logger.error(f"[求小红花] 执行异常: {e}")

        return batch_id

    async def _cleanup_expired_logs(self, session: AsyncSession) -> None:
        """
        主动清理过期的求小红花日志

        删除 created_at 早于 (当前北京时间 - LOG_RETENTION_DAYS 天) 的日志记录，
        避免日志表无限增长。使用参数化的 ORM delete 语句，避免 SQL 注入。
        """
        try:
            cutoff_time = get_beijing_now_naive() - timedelta(days=self.LOG_RETENTION_DAYS)
            stmt = sql_delete(ScheduledRedFlowerLog).where(
                ScheduledRedFlowerLog.created_at < cutoff_time
            )
            result = await session.execute(stmt)
            await session.commit()

            deleted_count = result.rowcount or 0
            if deleted_count > 0:
                logger.info(
                    f"[求小红花] 已清理 {deleted_count} 条 {self.LOG_RETENTION_DAYS} 天前的求小红花日志"
                    f"（清理时间界限: {cutoff_time}）"
                )
        except Exception as e:
            logger.error(f"[求小红花] 清理过期日志失败: {e}")
            await session.rollback()

    async def _get_eligible_accounts(self, session: AsyncSession) -> List[XYAccount]:
        """
        获取符合条件的账号列表

        条件：
        - status = 'active'（启用）
        - auto_red_flower = True（自动求小红花开启）
        """
        stmt = select(XYAccount).where(
            XYAccount.status == "active",
            XYAccount.auto_red_flower == True,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # 不需要求小红花的订单状态（已取消、处理中、退款中/已退款）
    EXCLUDED_ORDER_STATUSES = ("cancelled", "processing", "refunding", "refunded")

    async def _get_pending_orders(
        self,
        session: AsyncSession,
        account_id: str,
    ) -> List[XYOrder]:
        """
        获取近10天内未求小红花的订单

        条件：
        - account_id 匹配
        - 真实下单时间(placed_at)在近10天内（不是数据库写入时间，
          避免同步历史订单时 created_at 都是最近导致"全量处理"问题）
        - placed_at 不为 NULL（历史空值数据跳过，防误伤）
        - is_red_flower = False
        - 排除已取消(cancelled)和待付款(processing)的订单
        - 按下单时间升序排列
        """
        now = get_beijing_now_naive()
        ten_days_ago = now - timedelta(days=10)

        stmt = select(XYOrder).where(
            XYOrder.account_id == account_id,
            XYOrder.is_red_flower == False,
            XYOrder.status.notin_(self.EXCLUDED_ORDER_STATUSES),
            XYOrder.placed_at.is_not(None),
            XYOrder.placed_at >= ten_days_ago,
        ).order_by(XYOrder.placed_at)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _process_account(
        self,
        session: AsyncSession,
        batch_id: str,
        account: XYAccount,
    ) -> None:
        """处理单个账号"""
        account_id = account.account_id

        # 检查账号是否处于Session过期冷却期内
        if is_account_session_cooled(account_id):
            logger.info(f"[求小红花] 账号 {account_id} 处于Session过期冷却期内，跳过")
            return

        logger.info(f"[求小红花] 开始处理账号: {account_id}")

        # 获取待处理订单
        orders = await self._get_pending_orders(session, account_id)

        if not orders:
            logger.info(f"[求小红花] 账号 {account_id} 没有待求小红花的订单")
            return

        logger.info(f"[求小红花] 账号 {account_id} 找到 {len(orders)} 个待求小红花订单")

        # 使用可变的cookie字符串，方便set-cookie刷新后后续订单使用最新cookie
        current_cookie_str = account.cookie

        # 处理每个订单
        for order in orders:
            if is_order_in_cooldown(order.order_no):
                logger.info(f"[求小红花] 订单 {order.order_no} 在冷却期内，跳过")
                continue

            try:
                success, error_message, updated_cookie = await self._request_red_flower(
                    session, account_id, current_cookie_str, order,
                )

                # 如果cookie被刷新了，同步更新本地变量供后续订单使用
                if updated_cookie and updated_cookie != current_cookie_str:
                    current_cookie_str = updated_cookie
                    logger.info(f"[求小红花] 账号 {account_id} Cookie已通过Set-Cookie更新")

                if success:
                    # 更新订单 is_red_flower 字段
                    await session.execute(
                        sql_update(XYOrder)
                        .where(XYOrder.order_no == order.order_no)
                        .values(is_red_flower=True)
                    )
                    await session.commit()
                else:
                    # Session过期时，标记冷却并触发密码登录，该账号后续订单都跳过
                    if error_message and "SESSION_EXPIRED" in error_message:
                        await self._log_result(
                            session, batch_id, account_id,
                            order.order_no, False, error_message,
                        )
                        break

                    # 令牌过期且重试仍失败，标记冷却并触发密码登录，该账号后续订单都跳过
                    if error_message and "TOKEN_RETRY_FAILED" in error_message:
                        await self._log_result(
                            session, batch_id, account_id,
                            order.order_no, False, error_message,
                        )
                        break

                    # 临时性错误加入冷却
                    if error_message and self._should_cooldown(error_message):
                        add_order_to_cooldown(order.order_no)

                # 记录日志
                await self._log_result(
                    session, batch_id, account_id,
                    order.order_no, success, error_message,
                )

                # 订单处理间隔
                await asyncio.sleep(self.ORDER_PROCESS_DELAY)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"[求小红花] 处理订单 {order.order_no} 异常: {error_msg}")
                if self._should_cooldown(error_msg):
                    add_order_to_cooldown(order.order_no)
                await self._log_result(
                    session, batch_id, account_id,
                    order.order_no, False, error_msg,
                )
                continue

    async def _request_red_flower(
        self,
        session: AsyncSession,
        account_id: str,
        cookie_str: str,
        order: XYOrder,
        is_retry: bool = False,
    ) -> tuple[bool, Optional[str], str]:
        """
        调用闲鱼求小红花API

        支持：
        - 处理响应中的Set-Cookie，合并更新到数据库
        - 令牌过期时从Set-Cookie提取新Cookie，更新数据库后自动重试一次
        - Session过期时标记冷却并触发后台密码登录

        Args:
            session: 数据库会话
            account_id: 账号ID
            cookie_str: 当前Cookie字符串
            order: 订单对象
            is_retry: 是否为令牌过期后的重试请求

        Returns:
            (是否成功, 错误信息, 最新cookie字符串)
        """
        order_no = order.order_no

        if not cookie_str:
            return False, "账号Cookie为空", cookie_str

        try:
            # 解析Cookie
            cookies = trans_cookies(cookie_str)

            # 获取token
            m_h5_tk = cookies.get("_m_h5_tk", "")
            token = m_h5_tk.split("_")[0] if m_h5_tk else ""

            if not token:
                return False, "Cookie中没有找到_m_h5_tk令牌", cookie_str

            # 生成时间戳
            t = str(int(time.time() * 1000))

            # 构造请求数据
            data = {
                "orderId": order_no,
                "channel": "list",
            }
            data_val = json.dumps(data, separators=(",", ":"))

            # 生成签名
            sign = generate_sign(t, token, data_val)

            # 构造请求参数
            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": t,
                "sign": sign,
                "v": "4.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": "mtop.taobao.idlemessage.red.flower",
                "sessionOption": "AutoLoginOnly",
            }

            # 构造请求头
            headers = {
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "cookie": cookie_str,
                "Referer": "https://www.goofish.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }

            retry_tag = "[令牌过期重试] " if is_retry else ""

            # 发送请求
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.red.flower/1.0/",
                    params=params,
                    data={"data": data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                ) as response:
                    result = await response.json()
                    ret_list = result.get("ret", [])
                    ret_msg = ret_list[0] if ret_list else "未知错误"

                    # ---- 处理响应中的 Set-Cookie，更新到数据库 ----
                    new_resp_cookies = extract_cookies_from_response(response)
                    if new_resp_cookies:
                        cookie_str = merge_cookies(cookie_str, new_resp_cookies)
                        await update_account_cookies_in_db(account_id, cookie_str)
                        logger.info(
                            f"[求小红花] {retry_tag}账号 {account_id} "
                            f"从Set-Cookie合并了 {len(new_resp_cookies)} 个字段并更新数据库"
                        )

                    # ---- 成功 ----
                    if ret_msg == "SUCCESS::调用成功":
                        logger.info(f"[求小红花] {retry_tag}订单 {order_no} 求小红花成功")
                        return True, None, cookie_str

                    # ---- 令牌过期处理 ----
                    if is_token_expired_error(ret_list):
                        if is_retry:
                            # 重试后仍令牌过期，放弃并标记冷却
                            logger.warning(
                                f"[求小红花] 账号 {account_id} 订单 {order_no} "
                                f"令牌过期重试仍失败: {ret_msg}，标记冷却并触发密码登录"
                            )
                            mark_account_session_expired(account_id)
                            trigger_password_login_async(account_id)
                            return False, f"TOKEN_RETRY_FAILED: {ret_msg}", cookie_str
                        else:
                            # 首次令牌过期，尝试用Set-Cookie刷新后重试
                            logger.warning(
                                f"[求小红花] 账号 {account_id} 订单 {order_no} "
                                f"令牌过期: {ret_msg}，准备用Set-Cookie刷新后重试"
                            )
                            has_new, refreshed_cookie = handle_token_expired_response(
                                response, cookie_str
                            )
                            if has_new:
                                # 更新数据库
                                await update_account_cookies_in_db(account_id, refreshed_cookie)
                                # 使用新Cookie重试一次
                                return await self._request_red_flower(
                                    session, account_id, refreshed_cookie, order, is_retry=True,
                                )
                            else:
                                # 响应中没有Set-Cookie，标记冷却并触发密码登录
                                logger.warning(
                                    f"[求小红花] 账号 {account_id} 令牌过期但Set-Cookie为空，"
                                    f"标记冷却并触发密码登录"
                                )
                                mark_account_session_expired(account_id)
                                trigger_password_login_async(account_id)
                                return False, f"TOKEN_RETRY_FAILED: {ret_msg}", cookie_str

                    # ---- Session过期 → 标记冷却 + 触发密码登录 ----
                    if is_session_expired_error(ret_list):
                        logger.warning(
                            f"[求小红花] 账号 {account_id} 订单 {order_no} "
                            f"Session过期: {ret_msg}，标记冷却并触发密码登录"
                        )
                        mark_account_session_expired(account_id)
                        trigger_password_login_async(account_id)
                        return False, f"SESSION_EXPIRED: {ret_msg}", cookie_str

                    logger.warning(
                        f"[求小红花] {retry_tag}订单 {order_no} 求小红花失败: {ret_msg}"
                    )
                    return False, ret_msg, cookie_str

        except aiohttp.ClientError as e:
            error_msg = f"网络请求失败: {e}"
            logger.error(f"[求小红花] 订单 {order_no} {error_msg}")
            return False, error_msg, cookie_str
        except Exception as e:
            error_msg = f"请求异常: {e}"
            logger.error(f"[求小红花] 订单 {order_no} {error_msg}")
            return False, error_msg, cookie_str

    async def _log_result(
        self,
        session: AsyncSession,
        batch_id: str,
        account_id: str,
        order_no: str,
        success: bool,
        error_message: Optional[str],
    ) -> None:
        """记录执行日志"""
        try:
            log = ScheduledRedFlowerLog(
                batch_id=batch_id,
                account_id=account_id,
                order_no=order_no,
                status="success" if success else "failed",
                error_message=error_message[:500] if error_message else None,
            )
            session.add(log)
            await session.commit()
        except Exception as e:
            logger.error(f"[求小红花] 记录日志失败: {e}")
            try:
                await session.rollback()
            except Exception:
                pass

    @staticmethod
    def _should_cooldown(error_message: str) -> bool:
        """判断错误是否应该加入冷却队列"""
        if not error_message:
            return False
        error_lower = error_message.lower()
        # 临时性错误需要冷却
        temp_keywords = [
            "token", "令牌", "expired", "超时", "timeout",
            "繁忙", "busy", "限流", "rate limit",
            "网络", "network", "unavailable", "频繁", "frequent",
        ]
        for kw in temp_keywords:
            if kw in error_lower:
                return True
        return False
