"""
COOKIES续期定时任务

功能：
1. 为启用和禁用账号初始化Cookie续期到期时间
2. 到期后通过浏览器注入Cookie并刷新页面完成续期
3. 将续期结果写入独立的COOKIES刷新日志表
4. 禁用账号连续失败10次后跳过处理
5. 禁用账号续期成功后自动启用并通知WebSocket服务启动任务
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.cookie_refresh_schedule import CookieRefreshSchedule
from common.models.scheduled_cookies_refresh_log import ScheduledCookiesRefreshLog
from common.models.xy_account import XYAccount
from common.utils.cookie_refresh import (
    build_cookie_string_from_browser_cookies,
    get_cookie_refresh_snapshot,
    normalize_browser_cookie_snapshot,
    normalize_cookie_string,
    set_cookie_refresh_snapshot,
)
from common.utils.time_utils import get_beijing_now_naive
from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.cookies_refresh_browser_service import cookies_refresh_browser_service

# 禁用账号连续失败次数阈值，超过则跳过处理
_CONSECUTIVE_FAILURE_THRESHOLD = 10
# 视为禁用的账号状态集合
_DISABLED_STATUSES = {"inactive", "disabled", "suspended"}


@dataclass(slots=True)
class CookiesRefreshProcessResult:
    """单个账号的COOKIES续期处理结果。"""

    status: str | None
    message: str
    updated_cookie_count: int = 0
    updated_cookie_names: list[str] = field(default_factory=list)
    next_expire_at: datetime | None = None


class CookiesRefreshTaskService:
    """COOKIES续期定时任务服务。"""

    def __init__(self):
        self.task_name = "COOKIES续期任务"

    def _build_cookie_record_key(self, cookie: dict[str, object]) -> str:
        return "|".join(
            [
                str(cookie.get("name") or ""),
                str(cookie.get("domain") or ""),
                str(cookie.get("path") or "/"),
            ]
        )

    def _build_cookie_record_label(self, cookie: dict[str, object]) -> str:
        name = str(cookie.get("name") or "").strip()
        domain = str(cookie.get("domain") or "").strip()
        path = str(cookie.get("path") or "/").strip() or "/"
        if not name:
            return ""
        if domain:
            return f"{name}@{domain}{path}"
        return name

    def _get_changed_cookie_labels(
        self,
        old_snapshot: list[dict[str, object]],
        new_snapshot: list[dict[str, object]],
    ) -> list[str]:
        old_map = {self._build_cookie_record_key(cookie): cookie for cookie in old_snapshot}
        new_map = {self._build_cookie_record_key(cookie): cookie for cookie in new_snapshot}
        changed_labels: list[str] = []
        for key in sorted(set(old_map) | set(new_map)):
            if old_map.get(key) == new_map.get(key):
                continue
            cookie = new_map.get(key) or old_map.get(key) or {}
            label = self._build_cookie_record_label(cookie)
            if label:
                changed_labels.append(label)
        return changed_labels

    def _build_initial_expire_at(self, now: datetime) -> datetime:
        """生成首次初始化的随机到期时间（0-30秒后）。"""
        return now + timedelta(seconds=random.randint(0, 30))

    def _build_success_expire_at(self, now: datetime) -> datetime:
        """生成续期成功后的随机到期时间（1-5分钟后）。"""
        return now + timedelta(seconds=random.randint(60, 300))

    async def _get_eligible_accounts(self, session: AsyncSession) -> list[XYAccount]:
        """查询所有未删除的账号（包含启用和禁用状态）。"""
        stmt = (
            select(XYAccount)
            .where(XYAccount.status != "deleted")
            .order_by(XYAccount.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _is_disabled_account(self, account: XYAccount) -> bool:
        """判断账号是否处于禁用状态。"""
        return (account.status or "").strip().lower() in _DISABLED_STATUSES

    async def _check_consecutive_failures(
        self,
        session: AsyncSession,
        account_id: str,
    ) -> bool:
        """检查禁用账号最近N条日志是否全部失败。

        Returns:
            True 表示连续失败已达阈值，应跳过处理。
        """
        stmt = (
            select(ScheduledCookiesRefreshLog.status)
            .where(ScheduledCookiesRefreshLog.account_id == account_id)
            .order_by(desc(ScheduledCookiesRefreshLog.id))
            .limit(_CONSECUTIVE_FAILURE_THRESHOLD)
        )
        result = await session.execute(stmt)
        recent_statuses = list(result.scalars().all())
        # 不足阈值条记录时不跳过
        if len(recent_statuses) < _CONSECUTIVE_FAILURE_THRESHOLD:
            return False
        return all(s == "failed" for s in recent_statuses)

    async def _enable_account_after_refresh(
        self,
        session: AsyncSession,
        account: XYAccount,
    ) -> None:
        """禁用账号续期成功后自动启用，并通知WebSocket服务启动任务。"""
        old_status = account.status
        account.status = "active"
        account.disable_reason = None
        await session.commit()
        logger.info(
            f"【{self.task_name}】禁用账号 {account.account_id} 续期成功，"
            f"状态已从 {old_status} 变更为 active"
        )

        # 通知WebSocket服务启动该账号任务
        try:
            settings = get_settings()
            http_client = get_http_client()
            start_url = (
                f"{settings.websocket_service_url}/internal/accounts/"
                f"{account.account_id}/start"
            )
            resp = await http_client.post(start_url, json={
                "cookie_value": account.cookie or "",
                "user_id": account.owner_id,
            })
            ws_success = resp.get("success", False) if isinstance(resp, dict) else False
            if ws_success:
                logger.info(
                    f"【{self.task_name}】账号 {account.account_id} WebSocket任务启动成功"
                )
            else:
                ws_msg = resp.get("message", "") if isinstance(resp, dict) else str(resp)
                logger.warning(
                    f"【{self.task_name}】账号 {account.account_id} WebSocket任务启动失败: {ws_msg}"
                )
        except Exception as exc:
            logger.error(
                f"【{self.task_name}】账号 {account.account_id} 通知WebSocket服务异常: {exc}"
            )

    async def _get_schedule(self, session: AsyncSession, account_id: str) -> CookieRefreshSchedule | None:
        """查询账号对应的Cookie续期计划。"""
        stmt = select(CookieRefreshSchedule).where(CookieRefreshSchedule.account_id == account_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _initialize_schedule(
        self,
        session: AsyncSession,
        account_id: str,
        now: datetime,
    ) -> CookiesRefreshProcessResult:
        """为首次出现的账号初始化Cookie续期时间。"""
        expire_at = self._build_initial_expire_at(now)
        schedule = CookieRefreshSchedule(
            account_id=account_id,
            expire_at=expire_at,
            last_status="initialized",
            last_error_message=None,
        )
        session.add(schedule)
        await session.commit()
        return CookiesRefreshProcessResult(
            status="initialized",
            message=f"首次初始化续期时间，下次到期时间：{expire_at.strftime('%Y-%m-%d %H:%M:%S')}",
            updated_cookie_count=0,
            next_expire_at=expire_at,
        )

    async def _process_account(
        self,
        session: AsyncSession,
        account: XYAccount,
    ) -> CookiesRefreshProcessResult:
        """处理单个账号的Cookie续期。"""
        now = get_beijing_now_naive()
        schedule = await self._get_schedule(session, account.account_id)
        if not schedule:
            return await self._initialize_schedule(session, account.account_id, now)

        if schedule.expire_at > now:
            remaining_seconds = int((schedule.expire_at - now).total_seconds())
            logger.info(f"【{self.task_name}】账号 {account.account_id} 未到期，剩余 {remaining_seconds} 秒")
            return CookiesRefreshProcessResult(
                status="success",
                message=f"未到期，跳过，剩余 {remaining_seconds} 秒",
                updated_cookie_count=0,
                next_expire_at=schedule.expire_at,
            )

        old_cookie_snapshot = get_cookie_refresh_snapshot(account.metadata_json)
        normalized_cookie_string = normalize_cookie_string(account.cookie or "")
        if not normalized_cookie_string and not old_cookie_snapshot:
            schedule.last_status = "failed"
            schedule.last_error_message = "账号Cookie为空，且无完整Cookie快照，无法执行续期"
            await session.commit()
            return CookiesRefreshProcessResult(status="failed", message="账号Cookie为空，且无完整Cookie快照，无法执行续期")

        browser_result = await cookies_refresh_browser_service.refresh_account_cookies(account)
        if not browser_result.success:
            schedule.last_status = "failed"
            schedule.last_error_message = browser_result.message[:500]
            await session.commit()
            return CookiesRefreshProcessResult(status="failed", message=browser_result.message)

        new_cookie_snapshot = normalize_browser_cookie_snapshot(browser_result.cookies)
        updated_cookie_names = self._get_changed_cookie_labels(old_cookie_snapshot, new_cookie_snapshot)
        updated_cookie_count = len(updated_cookie_names)
        merged_cookie_string = build_cookie_string_from_browser_cookies(new_cookie_snapshot)
        refresh_time = get_beijing_now_naive()
        next_expire_at = self._build_success_expire_at(refresh_time)

        account.cookie = merged_cookie_string
        account.metadata_json = set_cookie_refresh_snapshot(account.metadata_json, new_cookie_snapshot)
        account.last_refresh_at = refresh_time
        schedule.expire_at = next_expire_at
        schedule.last_refresh_at = refresh_time
        schedule.last_status = "success"
        schedule.last_error_message = None
        await session.commit()

        if updated_cookie_count > 0:
            updated_cookie_names_text = "、".join(updated_cookie_names)
            message = f"{browser_result.message}，全量比对更新 {updated_cookie_count} 个Cookie记录：{updated_cookie_names_text}"
        else:
            message = f"{browser_result.message}，未检测到完整Cookie快照变化"
        return CookiesRefreshProcessResult(
            status="success",
            message=message,
            updated_cookie_count=updated_cookie_count,
            updated_cookie_names=updated_cookie_names,
            next_expire_at=next_expire_at,
        )

    async def _log_result(
        self,
        session: AsyncSession,
        batch_id: str,
        account_id: str,
        result: CookiesRefreshProcessResult,
    ) -> None:
        """写入单个账号的COOKIES刷新日志。"""
        log_record = ScheduledCookiesRefreshLog(
            batch_id=batch_id,
            account_id=account_id,
            status=result.status or "failed",
            updated_cookie_count=result.updated_cookie_count,
            next_expire_at=result.next_expire_at,
            error_message=result.message[:500] if result.message else None,
        )
        session.add(log_record)
        await session.commit()

        if result.status == "success":
            logger.info(f"【{self.task_name}】账号 {account_id} 续期成功：{result.message}")
        elif result.status == "initialized":
            logger.info(f"【{self.task_name}】账号 {account_id} 已初始化续期计划")
        else:
            logger.warning(f"【{self.task_name}】账号 {account_id} 续期失败：{result.message}")

    async def execute(self) -> None:
        """执行COOKIES续期定时任务。"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = get_beijing_now_naive()
        batch_id = str(uuid.uuid4())
        initialized_count = 0
        success_count = 0
        failed_count = 0
        skipped_count = 0
        enabled_count = 0
        processed_count = 0

        async with async_session_maker() as session:
            accounts = await self._get_eligible_accounts(session)
            active_count = sum(1 for a in accounts if not self._is_disabled_account(a))
            disabled_count = len(accounts) - active_count
            logger.info(
                f"【{self.task_name}】共获取到 {len(accounts)} 个账号"
                f"（启用 {active_count} 个，禁用 {disabled_count} 个）"
            )

            for account in accounts:
                is_disabled = self._is_disabled_account(account)
                try:
                    # 禁用账号：检查是否连续失败达到阈值
                    if is_disabled:
                        should_skip = await self._check_consecutive_failures(
                            session, account.account_id
                        )
                        if should_skip:
                            skipped_count += 1
                            logger.info(
                                f"【{self.task_name}】禁用账号 {account.account_id} "
                                f"最近 {_CONSECUTIVE_FAILURE_THRESHOLD} 次均失败，跳过"
                            )
                            continue

                    result = await self._process_account(session, account)
                    processed_count += 1
                    if result.status == "initialized":
                        initialized_count += 1
                    elif result.status == "success":
                        success_count += 1
                        # 禁用账号续期成功 -> 自动启用
                        if is_disabled:
                            await self._enable_account_after_refresh(session, account)
                            enabled_count += 1
                    elif result.status == "failed":
                        failed_count += 1

                    await self._log_result(session, batch_id, account.account_id, result)
                except Exception as exc:
                    await session.rollback()
                    failed_count += 1
                    processed_count += 1
                    logger.error(f"【{self.task_name}】账号 {account.account_id} 执行异常: {exc}")
                    await self._log_result(
                        session,
                        batch_id,
                        account.account_id,
                        CookiesRefreshProcessResult(status="failed", message=f"执行异常: {exc}"),
                    )

        duration_seconds = (get_beijing_now_naive() - start_time).total_seconds()
        logger.info(
            f"【{self.task_name}】执行结束，实际处理 {processed_count} 个账号，"
            f"初始化 {initialized_count} 个，成功 {success_count} 个，失败 {failed_count} 个，"
            f"跳过 {skipped_count} 个（连续失败），自动启用 {enabled_count} 个，"
            f"耗时 {duration_seconds:.2f} 秒"
        )


cookies_refresh_task_service = CookiesRefreshTaskService()
