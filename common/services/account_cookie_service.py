"""
账号 Cookie 增量更新服务。

功能：
1. 按账号数据库行锁定当前 Cookie，避免并发续期互相覆盖
2. 将接口返回的新 Cookie 字段合并到数据库现有 Cookie
3. 保留原有 Cookie 字段，仅覆盖同名字段
"""
from __future__ import annotations

import asyncio
from typing import Mapping

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.utils.cookie_refresh import clear_cookie_refresh_snapshot
from common.utils.xianyu_utils import trans_cookies


async def merge_account_cookie_fields(
    account_row_id: int,
    account_id: str,
    cookie_updates: Mapping[str, object],
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> str | None:
    """将新 Cookie 字段合并写回指定账号。

    Args:
        account_row_id: ``xy_accounts.id``，用于精确定位账号并加行锁。
        account_id: 账号业务 ID，仅用于二次校验和日志。
        cookie_updates: 新增或更新的 Cookie 字段映射。
        max_attempts: 数据库写入最大尝试次数。
        retry_delay_seconds: 相邻重试之间的等待秒数。

    Returns:
        成功返回合并后的 Cookie 字符串；账号不存在或写入失败返回 ``None``。
    """
    updates = {
        str(name).strip(): "" if value is None else str(value)
        for name, value in (cookie_updates or {}).items()
        if str(name).strip()
    }
    if not updates:
        return None

    attempts = max(1, int(max_attempts))
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(XYAccount)
                    .where(
                        XYAccount.id == account_row_id,
                        XYAccount.account_id == account_id,
                    )
                    .with_for_update()
                )
                account = result.scalars().first()
                if not account:
                    logger.warning(
                        f"【{account_id}】未找到账号数据库行，无法合并 "
                        f"{len(updates)} 个Cookie字段"
                    )
                    return None

                merged_cookies = trans_cookies(account.cookie or "")
                merged_cookies.update(updates)
                merged_cookies_str = "; ".join(
                    f"{name}={value}" for name, value in merged_cookies.items()
                )
                account.cookie = merged_cookies_str
                account.metadata_json = clear_cookie_refresh_snapshot(
                    account.metadata_json
                )
                session.add(account)
                await session.commit()
                return merged_cookies_str
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_delay_seconds))

    logger.error(
        f"【{account_id}】合并Cookie字段失败，已重试{attempts}次: {last_error}"
    )
    return None
