"""
接口续期Cookies定时任务

功能：
1. 每 10 分钟执行一次（具体间隔由数据库 xy_scheduled_tasks 配置控制）
2. 查询数据库中所有启用状态的闲鱼账号
3. 调用 common/services/cookie_renew_api_service 共通服务执行接口续期
4. 如有差异，覆盖更新数据库中的 cookies 字符串
5. 详细记录每次执行的批次日志
6. 失败时不重试当次（按定时间隔下次重试）
7. 续期成功后若账号已被并发改为禁用状态，则自动重新启用并通知 WebSocket 服务
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.db.session import async_session_maker
from common.models.scheduled_api_cookie_renew_log import ScheduledApiCookieRenewLog
from common.models.xy_account import XYAccount
from common.services.cookie_renew_api_service import cookie_renew_api_service
from common.utils.cookie_refresh import clear_cookie_refresh_snapshot
from common.utils.time_utils import get_beijing_now_naive


# 账号之间的请求间隔（秒），避免短时间内集中请求
ACCOUNT_REQUEST_INTERVAL_SECONDS = 1
# 接口返回内容最大保存长度（避免 TEXT 列过大）
MAX_RESPONSE_CONTENT_LENGTH = 2000
# 视为"禁用"的账号状态集合
_DISABLED_STATUSES = {"inactive", "disabled", "suspended"}


@dataclass(slots=True)
class ApiCookieRenewResult:
    """单个账号的接口续期处理结果。"""

    status: str  # success / cookie_updated / browser_renewed / failed / need_password_login
    updated_cookie_names: list[str] = field(default_factory=list)
    response_content: str | None = None
    error_message: str | None = None
    renew_method: str = "none"  # api / browser / none
    step_details: str = ""  # 各步骤执行详情


class ApiCookieRenewTaskService:
    """接口续期Cookies定时任务服务。"""

    def __init__(self):
        self.task_name = "接口续期Cookies"

    async def execute(self) -> None:
        """执行接口续期Cookies任务。"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = get_beijing_now_naive()
        batch_id = str(uuid.uuid4())
        success_count = 0
        cookie_updated_count = 0
        browser_renewed_count = 0
        need_password_login_count = 0
        failed_count = 0
        processed_count = 0

        try:
            async with async_session_maker() as session:
                accounts = await self._get_eligible_accounts(session)
                if not accounts:
                    logger.info(f"【{self.task_name}】未找到可处理的账号")
                    return

                logger.info(
                    f"【{self.task_name}】共找到 {len(accounts)} 个启用账号"
                )

                for index, account in enumerate(accounts):
                    try:
                        result = await self._renew_account(session, account)
                        processed_count += 1
                        if result.status == "success":
                            success_count += 1
                        elif result.status == "cookie_updated":
                            cookie_updated_count += 1
                        elif result.status == "browser_renewed":
                            browser_renewed_count += 1
                        elif result.status == "need_password_login":
                            need_password_login_count += 1
                        else:
                            failed_count += 1

                        await self._log_result(session, batch_id, account.account_id, result)

                        # 续期成功后重新读取账号最新状态，若期间被并发改为禁用则自动启用
                        if result.status in ("success", "cookie_updated", "browser_renewed"):
                            await session.refresh(account)
                            if self._is_disabled_account(account):
                                await self._enable_account_after_renew(session, account)
                    except Exception as exc:
                        await session.rollback()
                        failed_count += 1
                        processed_count += 1
                        logger.error(
                            f"【{self.task_name}】账号 {account.account_id} 执行异常: {exc}"
                        )
                        await self._log_result(
                            session,
                            batch_id,
                            account.account_id,
                            ApiCookieRenewResult(
                                status="failed",
                                error_message=f"执行异常: {exc}"[:500],
                            ),
                        )

                    # 账号之间间隔，避免请求过于密集
                    if index < len(accounts) - 1:
                        await asyncio.sleep(ACCOUNT_REQUEST_INTERVAL_SECONDS)

            duration_seconds = (get_beijing_now_naive() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行结束，批次ID: {batch_id}，"
                f"处理 {processed_count} 个账号，"
                f"接口续期成功 {success_count} 个，Cookie更新 {cookie_updated_count} 个，"
                f"浏览器续期成功 {browser_renewed_count} 个，"
                f"需要密码登录 {need_password_login_count} 个，"
                f"失败 {failed_count} 个，"
                f"耗时 {duration_seconds:.2f} 秒"
            )

        except Exception as exc:
            logger.error(f"【{self.task_name}】执行失败: {exc}")
            raise

    async def _get_eligible_accounts(self, session: AsyncSession) -> list[XYAccount]:
        """获取所有启用状态的账号（仅处理 active 账号）。"""
        stmt = (
            select(XYAccount)
            .where(XYAccount.status == "active")
            .order_by(XYAccount.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _is_disabled_account(self, account: XYAccount) -> bool:
        """判断账号是否处于禁用状态。"""
        return (account.status or "").strip().lower() in _DISABLED_STATUSES

    async def _enable_account_after_renew(
        self,
        session: AsyncSession,
        account: XYAccount,
    ) -> None:
        """禁用账号接口续期成功后自动启用，并通知WebSocket服务启动任务。"""
        old_status = account.status
        account.status = "active"
        account.disable_reason = None
        await session.commit()
        logger.info(
            f"【{self.task_name}】禁用账号 {account.account_id} 接口续期成功，"
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
            resp = await http_client.post(
                start_url,
                json={
                    "cookie_value": account.cookie or "",
                    "user_id": account.owner_id,
                },
            )
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

    async def _renew_account(
        self,
        session: AsyncSession,
        account: XYAccount,
    ) -> ApiCookieRenewResult:
        """对单个账号执行接口续期。"""
        account_id = account.account_id
        cookies_str = account.cookie or ""

        if not cookies_str.strip():
            return ApiCookieRenewResult(
                status="failed",
                error_message="账号Cookie为空，无法执行接口续期",
            )

        logger.info(f"【{self.task_name}】开始处理账号: {account_id}")

        # 调用共通服务执行续期（接口续期 → 浏览器续期）
        renew_result = await cookie_renew_api_service.renew(cookies_str, account_id, source="scheduled_task")

        # 仅在 cookies 真正发生变化时更新数据库
        if (
            renew_result.updated_cookie_names
            and renew_result.new_cookies_str
            and renew_result.new_cookies_str != cookies_str
        ):
            account.cookie = renew_result.new_cookies_str
            # 清理浏览器 cookie 快照，避免 cookies_refresh_task 下次基于过期快照做差异检测
            account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
            account.last_refresh_at = get_beijing_now_naive()
            session.add(account)
            await session.commit()
            logger.info(
                f"【{self.task_name}】账号 {account_id} Cookie已更新（{renew_result.renew_method}），"
                f"共更新 {len(renew_result.updated_cookie_names)} 个字段："
                f"{'、'.join(renew_result.updated_cookie_names)}"
            )

        # 计算最终状态
        if renew_result.success:
            if renew_result.renew_method == "browser":
                # 浏览器续期成功（接口续期失败，浏览器续期成功）
                return ApiCookieRenewResult(
                    status="browser_renewed",
                    updated_cookie_names=renew_result.updated_cookie_names,
                    response_content=None,
                    error_message=None,
                    renew_method="browser",
                    step_details=renew_result.step_details,
                )
            elif renew_result.updated_cookie_names:
                # 接口续期成功且有Cookie更新
                return ApiCookieRenewResult(
                    status="cookie_updated",
                    updated_cookie_names=renew_result.updated_cookie_names,
                    response_content=None,
                    error_message=None,
                    renew_method="api",
                    step_details=renew_result.step_details,
                )
            # 接口续期成功但无Cookie变化
            return ApiCookieRenewResult(
                status="success",
                updated_cookie_names=[],
                response_content=None,
                error_message=None,
                renew_method="api",
                step_details=renew_result.step_details,
            )

        # 续期失败：判断是否需要密码登录
        truncated_response = self._truncate_response(renew_result.response_text)
        if renew_result.need_password_login:
            # 接口续期和浏览器续期都失败，触发后台密码登录
            logger.warning(
                f"【{self.task_name}】账号 {account_id} 接口续期和浏览器续期均失败，"
                f"触发后台密码登录。详情: {renew_result.step_details}"
            )
            try:
                from common.utils.cookie_refresh import (
                    mark_account_session_expired,
                    trigger_password_login_async,
                )
                mark_account_session_expired(account_id)
                trigger_password_login_async(account_id)
            except Exception as pwd_exc:
                logger.error(
                    f"【{self.task_name}】账号 {account_id} 触发密码登录异常: {pwd_exc}"
                )

            return ApiCookieRenewResult(
                status="need_password_login",
                updated_cookie_names=renew_result.updated_cookie_names,
                response_content=truncated_response,
                error_message=renew_result.api_message[:500] if renew_result.api_message else "接口续期和浏览器续期均失败，需要账号密码登录",
                renew_method="none",
                step_details=renew_result.step_details,
            )

        # 普通失败
        return ApiCookieRenewResult(
            status="failed",
            updated_cookie_names=renew_result.updated_cookie_names,
            response_content=truncated_response,
            error_message=renew_result.api_message[:500] if renew_result.api_message else "续期失败",
            renew_method="none",
            step_details=renew_result.step_details,
        )

    @staticmethod
    def _truncate_response(response_text: str | None) -> str | None:
        """裁剪响应文本到最大长度以保存到日志表中。"""
        if not response_text:
            return None
        text = response_text.strip()
        if not text:
            return None
        if len(text) > MAX_RESPONSE_CONTENT_LENGTH:
            return text[:MAX_RESPONSE_CONTENT_LENGTH] + "...(已截断)"
        return text

    async def _log_result(
        self,
        session: AsyncSession,
        batch_id: str,
        account_id: str,
        result: ApiCookieRenewResult,
    ) -> None:
        """写入单个账号的接口续期日志。"""
        try:
            updated_names_str = (
                ",".join(result.updated_cookie_names)
                if result.updated_cookie_names
                else None
            )
            # 错误信息中包含步骤详情，方便排查
            error_message = result.error_message or ""
            if result.step_details:
                error_message = f"{error_message}\n【执行详情】{result.step_details}" if error_message else f"【执行详情】{result.step_details}"
            error_message = error_message[:500] if error_message else None

            log_record = ScheduledApiCookieRenewLog(
                batch_id=batch_id,
                account_id=account_id,
                status=result.status,
                updated_cookie_count=len(result.updated_cookie_names),
                updated_cookie_names=updated_names_str,
                response_content=result.response_content,
                error_message=error_message,
            )
            session.add(log_record)
            await session.commit()

            if result.status == "cookie_updated":
                logger.info(
                    f"【{self.task_name}】账号 {account_id} Cookie 已同步更新"
                    f"（接口续期，{len(result.updated_cookie_names)}个字段）"
                )
            elif result.status == "browser_renewed":
                logger.info(
                    f"【{self.task_name}】账号 {account_id} Cookie 已同步更新"
                    f"（接口续期失败，浏览器续期成功，{len(result.updated_cookie_names)}个字段）"
                )
            elif result.status == "success":
                logger.info(f"【{self.task_name}】账号 {account_id} 接口正常，Cookie无变化")
            elif result.status == "need_password_login":
                logger.warning(
                    f"【{self.task_name}】账号 {account_id} 接口续期和浏览器续期均失败，"
                    f"需要账号密码登录。详情: {result.step_details}"
                )
            else:
                logger.warning(
                    f"【{self.task_name}】账号 {account_id} 续期失败："
                    f"{result.error_message or '未知错误'}"
                )
        except Exception as exc:
            logger.error(f"【{self.task_name}】账号 {account_id} 记录日志失败: {exc}")
            await session.rollback()


# 全局实例
api_cookie_renew_task_service = ApiCookieRenewTaskService()
