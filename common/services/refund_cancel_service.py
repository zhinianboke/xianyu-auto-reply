"""
退款订单注销服务

功能：
1. 统一处理「退款订单注销」逻辑，供「消息接收（websocket）」与「退款订单获取定时任务（scheduler）」共用
2. 按账号配置调用外部注销接口，推送发货内容和链接
3. 记录注销结果到订单（is_unregistered / unregister_error_reason）

规则：
- 账号未开启注销 / 未配置URL → 不处理
- 订单不存在 / 已注销过(is_unregistered=True) → 跳过（幂等）
- 发货内容为空 → 直接标记已请求 + 错误原因「发货内容为空」
- 有发货内容 → 按 \n---\n 拆块，每块取首个链接，逐块 POST 表单（form-data，每个发货内容调一次），
  全部返回200才标记已请求；任一失败记录错误原因，不标记
"""
from __future__ import annotations

import re
import asyncio

import aiohttp
from loguru import logger
from sqlalchemy import select

from common.models.xy_order import XYOrder


async def process_order_unregister(account_id: str, order_no: str) -> None:
    """处理单个退款订单的注销接口调用（消息接收与定时任务共用）

    Args:
        account_id: 账号标识（xy_accounts.account_id）
        order_no: 订单号
    """
    from common.db.session import async_session_maker
    from common.models.xy_account import XYAccount

    pf = f"【{account_id}】"

    # 1. 读取账号配置 + 订单状态（短事务）
    async with async_session_maker() as session:
        account = (await session.execute(
            select(XYAccount).where(XYAccount.account_id == account_id)
        )).scalars().first()
        if not account or not account.refund_cancel_enabled:
            return  # 未开启退款订单注销
        cancel_url = (account.refund_cancel_url or '').strip()
        if not cancel_url:
            return  # 未配置URL
        timeout_seconds = account.refund_cancel_timeout or 60

        order = (await session.execute(
            select(XYOrder).where(
                XYOrder.order_no == order_no,
                XYOrder.account_id == account_id,
            )
        )).scalars().first()
        if not order or order.is_unregistered:
            return  # 订单不存在或已注销过

        delivery_content = order.delivery_content or ''

        # 按 \n---\n 拆块（每个发货内容一块），在会话内计算以便空内容直接标记
        blocks = [b.strip() for b in delivery_content.split('\n---\n') if b.strip()]

        # 无有效发货内容（为空或拆块后无内容）→ 直接标记已请求 + 错误原因
        if not blocks:
            order.is_unregistered = True
            order.unregister_error_reason = "发货内容为空"
            await session.commit()
            logger.info(f"{pf}退款注销：订单 {order_no} 发货内容为空，标记已请求")
            return

    # 2. 逐块调用注销接口（每个发货内容调一次，HTTP 期间不持有数据库会话）
    timeout_obj = aiohttp.ClientTimeout(total=timeout_seconds)
    all_success = True
    fail_detail = ''
    async with aiohttp.ClientSession() as http_session:
        for idx, block in enumerate(blocks, 1):
            link_match = re.search(r'https?://\S+', block)
            link_url = link_match.group(0) if link_match else ''
            payload = {'delivery_content': block, 'link_url': link_url}
            try:
                # 以 form-data（application/x-www-form-urlencoded）提交：data=dict
                async with http_session.post(cancel_url, data=payload, timeout=timeout_obj) as resp:
                    status_code = resp.status
                    resp_text = await resp.text()
                if status_code == 200:
                    logger.info(
                        f"{pf}退款注销接口成功 order={order_no} 第{idx}/{len(blocks)}块 link={link_url}"
                    )
                else:
                    all_success = False
                    fail_detail = f"第{idx}块返回HTTP {status_code}: {resp_text[:100]}"
                    logger.warning(f"{pf}退款注销接口非200 order={order_no} {fail_detail}")
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                all_success = False
                fail_detail = f"第{idx}块网络异常: {e}"
                logger.warning(f"{pf}退款注销接口异常 order={order_no} {fail_detail}")

    # 3. 写回结果（短事务）
    async with async_session_maker() as session:
        order = (await session.execute(
            select(XYOrder).where(
                XYOrder.order_no == order_no,
                XYOrder.account_id == account_id,
            )
        )).scalars().first()
        if not order:
            return
        if all_success:
            order.is_unregistered = True
            order.unregister_error_reason = None
            logger.info(f"{pf}✅ 订单 {order_no} 退款注销全部成功，标记 is_unregistered=True")
        else:
            order.unregister_error_reason = f"注销失败: {fail_detail}"[:500]
            logger.warning(f"{pf}订单 {order_no} 退款注销存在失败，记录错误原因，不标记已注销")
        await session.commit()
