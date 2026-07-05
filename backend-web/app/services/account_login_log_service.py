"""
账号登录日志查询服务

功能：
1. 账号登录日志分页查询（按账号 / 时间范围 / 登录状态筛选）
2. 普通用户仅可查询自己账号的登录日志，管理员可查全部
3. 提供清理 10 天前历史日志能力
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.account_login_log import XYAccountLoginLog
from common.models.xy_account import XYAccount
from common.utils.pagination import execute_paginated_with_filters
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


class AccountLoginLogService:
    """账号登录日志只读访问 + 历史日志清理。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        *,
        owner_id: int | None = None,
        account_identifier: str | None = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        login_status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """分页查询账号登录日志

        Args:
            owner_id: 所有者ID筛选，None 代表管理员查全部
            account_identifier: 业务账号ID（XYAccount.account_id）
            start_date: 开始日期（YYYY-MM-DD，含当天 00:00:00）
            end_date: 结束日期（YYYY-MM-DD，含当天 23:59:59）
            login_status: 登录状态（success / failed / skipped_cooldown / no_credentials）
            limit: 每页数量
            offset: 偏移量

        Returns:
            (日志列表[dict], 总数)
        """
        filters: list = []

        if owner_id is not None:
            filters.append(XYAccountLoginLog.owner_id == owner_id)

        if account_identifier:
            filters.append(XYAccountLoginLog.account_identifier == account_identifier)

        # 时间范围（格式错误时静默跳过，与风控日志服务保持一致）
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                filters.append(XYAccountLoginLog.created_at >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                filters.append(XYAccountLoginLog.created_at <= end_dt)
            except ValueError:
                pass

        if login_status:
            filters.append(XYAccountLoginLog.login_status == login_status)

        logs, total = await execute_paginated_with_filters(
            self.session,
            XYAccountLoginLog,
            filters=filters,
            order_by=[XYAccountLoginLog.created_at.desc()],
            limit=limit,
            offset=offset,
        )

        # 批量查询相关账号的当前状态
        account_ids = list({log.account_identifier for log in logs if log.account_identifier})
        account_status_map: dict[str, str] = {}
        account_disable_reason_map: dict[str, str] = {}
        if account_ids:
            from sqlalchemy import select
            accounts_stmt = select(
                XYAccount.account_id, XYAccount.status, XYAccount.disable_reason
            ).where(XYAccount.account_id.in_(account_ids))
            account_rows = (await self.session.execute(accounts_stmt)).all()
            account_status_map = {row.account_id: row.status or "unknown" for row in account_rows}
            account_disable_reason_map = {row.account_id: row.disable_reason or "" for row in account_rows}

        items = [
            {
                "id": log.id,
                "cookie_id": log.account_identifier,
                "username": log.username,
                "trigger_reason": log.trigger_reason,
                "login_status": log.login_status,
                "failure_reason": log.failure_reason,
                "error_message": log.error_message,
                "updated_cookie_names": log.updated_cookie_names,
                "duration_ms": log.duration_ms,
                "account_status": account_status_map.get(log.account_identifier, "unknown"),
                "disable_reason": account_disable_reason_map.get(log.account_identifier, ""),
                "created_at": safe_isoformat(log.created_at),
            }
            for log in logs
        ]
        return items, total

    async def cleanup_logs_older_than_days(self, days: int = 10) -> int:
        """删除 N 天前的历史登录日志，返回受影响行数。

        默认保留最近 10 天，便于「日志管理」界面一键清理过期数据。
        """
        if days < 1:
            days = 1
        cutoff = get_beijing_now_naive() - timedelta(days=days)
        stmt = delete(XYAccountLoginLog).where(XYAccountLoginLog.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(result.rowcount or 0)

    async def cleanup_all_logs(self) -> int:
        """清空全部登录日志（管理员手动触发），返回受影响行数。"""
        stmt = delete(XYAccountLoginLog)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(result.rowcount or 0)
