"""
用户登录日志服务

功能：
1. 记录系统用户登录本系统的每一次尝试与结果（成功 / 失败都写入），供登录接口调用
2. 用户登录日志分页查询（仅管理员使用，返回全部用户的登录记录）
3. 支持按关键字、登录方式、时间范围筛选

说明：
- 本服务只做追加与查询，不提供 UPDATE / DELETE
- 与「账号登录日志服务（AccountLoginLogService）」相互独立，勿混用
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user_login_log import XYUserLoginLog
from common.utils.pagination import execute_paginated_with_filters
from common.utils.time_utils import safe_isoformat

# 登录方式枚举（前端据此展示中文）
LOGIN_METHOD_USERNAME_PASSWORD = "username_password"  # 账号密码
LOGIN_METHOD_EMAIL_PASSWORD = "email_password"  # 邮箱密码
LOGIN_METHOD_EMAIL_CODE = "email_code"  # 邮箱验证码


class UserLoginLogService:
    """用户登录日志写入与查询服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        login_method: str,
        success: bool,
        owner_id: Optional[int] = None,
        login_account: Optional[str] = None,
        client_ip: Optional[str] = None,
        result_message: Optional[str] = None,
    ) -> None:
        """写入一条用户登录日志（成功 / 失败都写）。

        该方法处于登录主流程中，写日志失败不应阻断登录，因此内部捕获异常、
        回滚本次写入并打印完整错误日志（不做静默失败）。

        Args:
            login_method: 登录方式（username_password/email_password/email_code）
            success: 是否登录成功
            owner_id: 登录用户ID（所属用户），失败时为 None
            login_account: 登录账号（用户名或邮箱）
            client_ip: 客户端 IP
            result_message: 结果说明（成功提示或失败原因）
        Returns:
            None
        """
        log = XYUserLoginLog(
            owner_id=owner_id,
            login_account=login_account,
            login_method=login_method,
            success=bool(success),
            client_ip=(client_ip or None),
            result_message=(result_message or None),
        )
        try:
            self.session.add(log)
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001 - 登录日志写入失败不能影响登录流程
            await self.session.rollback()
            logger.error(
                "写入用户登录日志失败: "
                f"login_method={login_method}, success={success}, owner_id={owner_id}, "
                f"login_account={login_account}, client_ip={client_ip}, "
                f"result_message={result_message}, error={type(exc).__name__}: {exc}"
            )

    async def list_logs(
        self,
        *,
        keyword: Optional[str] = None,
        login_method: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """分页查询用户登录日志（返回全部用户的记录，供管理员查看）。

        Args:
            keyword: 关键字（匹配登录账号，或数字时匹配用户ID）
            login_method: 登录方式筛选
            start_date: 开始日期（YYYY-MM-DD，含当天 00:00:00）
            end_date: 结束日期（YYYY-MM-DD，含当天 23:59:59）
            limit: 每页数量
            offset: 偏移量

        Returns:
            (日志列表[dict], 总数)
        """
        filters: list = []

        # 关键字：匹配登录账号；纯数字时同时匹配用户ID
        if keyword:
            kw = keyword.strip()
            if kw:
                conditions = [XYUserLoginLog.login_account.ilike(f"%{kw}%")]
                if kw.isdigit():
                    conditions.append(XYUserLoginLog.owner_id == int(kw))
                filters.append(or_(*conditions))

        if login_method:
            filters.append(XYUserLoginLog.login_method == login_method)

        # 时间范围（格式错误时静默跳过，与其它日志服务保持一致）
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                filters.append(XYUserLoginLog.created_at >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                filters.append(XYUserLoginLog.created_at <= end_dt)
            except ValueError:
                pass

        logs, total = await execute_paginated_with_filters(
            self.session,
            XYUserLoginLog,
            filters=filters,
            order_by=[XYUserLoginLog.created_at.desc(), XYUserLoginLog.id.desc()],
            limit=limit,
            offset=offset,
        )

        items = [
            {
                "id": log.id,
                "owner_id": log.owner_id,
                "login_account": log.login_account,
                "login_method": log.login_method,
                "success": bool(log.success),
                "client_ip": log.client_ip,
                "result_message": log.result_message,
                "created_at": safe_isoformat(log.created_at),
            }
            for log in logs
        ]
        return items, total