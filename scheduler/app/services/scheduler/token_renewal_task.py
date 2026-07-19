"""
IM Token 续期定时任务。

功能：
1. 查询启用账号中两个到期日均失效且当日无处理中风控日志的 Token 缓存
2. 使用缓存表已有 Device ID 请求最新 Token
3. 接口下发的 Set-Cookie（如新 _m_h5_tk）合并写回账号，令牌过期时重试一次
4. 命中“挤爆了”等风控响应时调用 WebSocket 滑块，合并新 Cookie 后重试获取 Token
5. 仅更新 Token 和续期到期日，不修改原到期日
6. 支持调度循环和管理界面手动执行
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from loguru import logger
from sqlalchemy import exists, or_, select, update

from common.db.session import async_session_maker
from common.models.risk_control_log import XYRiskControlLog
from common.models.scheduled_token_renewal_log import ScheduledTokenRenewalLog
from common.models.token_cache import TokenCache
from common.models.xy_account import XYAccount
from common.services.account_cookie_service import merge_account_cookie_fields
from common.services.captcha.token_response import (
    extract_token_captcha_url,
    is_token_captcha_required,
)
from common.services.captcha.websocket_solver import solve_captcha_via_websocket
from common.services.im_token_api import extract_im_access_token, request_im_token
from common.utils.time_utils import get_beijing_now_naive, random_token_cache_expiry

from app.core.config import get_settings


TOKEN_RENEWAL_MAX_CONCURRENCY = 5

@dataclass(frozen=True, slots=True)
class TokenRenewalCandidate:
    """一次 Token 续期请求所需的数据库快照。"""

    cache_id: int
    account_row_id: int
    user_id: str
    account_id: str
    cookies_str: str
    device_id: str


@dataclass(frozen=True, slots=True)
class TokenRenewalResult:
    """单个账号的 Token 续期结果。"""

    candidate: TokenRenewalCandidate
    success: bool
    message: str
    renew_expire_at: datetime | None = None


class TokenRenewalTask:
    """为已到期 Token 缓存预取下一枚 Token。"""

    def __init__(self, max_concurrency: int = TOKEN_RENEWAL_MAX_CONCURRENCY):
        """初始化 Token 续期任务。

        Args:
            max_concurrency: 单轮请求闲鱼 Token API 的最大并发数。
        """
        self.task_name = "Token续期任务"
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._execution_lock = asyncio.Lock()

    async def execute(self) -> int:
        """执行一轮 Token 续期。

        Returns:
            本轮成功写入续期 Token 的缓存条数。
        """
        async with self._execution_lock:
            candidates = await self._load_candidates()
            if not candidates:
                return 0

            batch_id = str(uuid.uuid4())
            raw_results = await asyncio.gather(
                *(self._renew_candidate(candidate) for candidate in candidates),
                return_exceptions=True,
            )
            results: list[TokenRenewalResult] = []
            for candidate, result in zip(candidates, raw_results):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                if isinstance(result, BaseException):
                    message = f"未预期异常：{type(result).__name__}: {result}"
                    logger.error(
                        f"【{self.task_name}】【{candidate.account_id}】{message}"
                    )
                    results.append(self._failed_result(candidate, message))
                else:
                    results.append(result)

            await self._save_results(batch_id, results)
            renewed_count = sum(1 for result in results if result.success)
            logger.info(
                f"【{self.task_name}】执行完成: 批次={batch_id}, 候选={len(candidates)}, "
                f"成功={renewed_count}, 失败或已被其他流程更新={len(candidates) - renewed_count}"
            )
            return renewed_count

    @staticmethod
    def _failed_result(
        candidate: TokenRenewalCandidate,
        message: str,
    ) -> TokenRenewalResult:
        """构造失败结果，统一限制入库说明长度。"""
        return TokenRenewalResult(
            candidate=candidate,
            success=False,
            message=message[:500],
        )

    async def _save_results(
        self,
        batch_id: str,
        results: list[TokenRenewalResult],
    ) -> None:
        """将一轮 Token 续期结果按批次写入数据库。"""
        async with async_session_maker() as session:
            try:
                session.add_all(
                    [
                        ScheduledTokenRenewalLog(
                            batch_id=batch_id,
                            account_id=result.candidate.account_id,
                            token_user_id=result.candidate.user_id,
                            status="success" if result.success else "failed",
                            renew_expire_at=result.renew_expire_at,
                            error_message=result.message[:500],
                        )
                        for result in results
                    ]
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error(
                    f"【{self.task_name}】批次日志写入失败: batch_id={batch_id}, "
                    f"error={type(exc).__name__}: {exc}"
                )

    async def _load_candidates(self) -> list[TokenRenewalCandidate]:
        """查询可续期且当日没有处理中风控日志的启用账号。"""
        now = get_beijing_now_naive()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day_start = day_start + timedelta(days=1)
        processing_risk_exists = exists(
            select(XYRiskControlLog.id).where(
                XYRiskControlLog.account_identifier == XYAccount.account_id,
                XYRiskControlLog.processing_status == "processing",
                XYRiskControlLog.created_at >= day_start,
                XYRiskControlLog.created_at < next_day_start,
            )
        ).correlate(XYAccount)

        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(
                        TokenCache.id.label("cache_id"),
                        TokenCache.user_id,
                        TokenCache.device_id,
                        XYAccount.id.label("account_row_id"),
                        XYAccount.account_id,
                        XYAccount.cookie.label("cookies_str"),
                    )
                    .join(XYAccount, XYAccount.unb == TokenCache.user_id)
                    .where(
                        XYAccount.status == "active",
                        TokenCache.expire_at <= now,
                        or_(
                            TokenCache.renew_expire_at.is_(None),
                            TokenCache.renew_expire_at <= now,
                        ),
                        ~processing_risk_exists,
                    )
                    .order_by(XYAccount.id.asc())
                )
            ).all()

        # 历史数据可能存在多个账号行使用同一 unb；每个缓存键一轮只请求一次。
        candidates_by_user: dict[str, TokenRenewalCandidate] = {}
        for row in rows:
            if not row.user_id or not row.device_id or not row.cookies_str:
                logger.warning(
                    f"【{self.task_name}】跳过缺少必要数据的账号: "
                    f"account_id={row.account_id}, user_id={row.user_id or '空'}"
                )
                continue
            candidates_by_user.setdefault(
                row.user_id,
                TokenRenewalCandidate(
                    cache_id=row.cache_id,
                    account_row_id=row.account_row_id,
                    user_id=row.user_id,
                    account_id=row.account_id,
                    cookies_str=row.cookies_str,
                    device_id=row.device_id,
                ),
            )
        return list(candidates_by_user.values())

    @staticmethod
    def _is_token_expired_response(response_json: Any) -> bool:
        """判断接口响应是否为 mtop 令牌过期（_m_h5_tk 失效）。

        Args:
            response_json: IM Token API 返回的 JSON 数据。
        Returns:
            令牌过期返回 True，否则返回 False。
        """
        if not isinstance(response_json, dict):
            return False
        ret_str = json.dumps(response_json.get("ret", []) or [], ensure_ascii=False)
        return "FAIL_SYS_TOKEN_EXOIRED" in ret_str or "FAIL_SYS_TOKEN_EXPIRED" in ret_str

    @staticmethod
    def _is_captcha_required_response(response_json: Any) -> bool:
        """判断 Token 响应是否触发风控滑块。"""
        return is_token_captcha_required(response_json)

    @staticmethod
    def _captcha_url(response_json: Any) -> str:
        """提取 Token 响应中的滑块验证链接。"""
        return extract_token_captcha_url(response_json)

    async def _merge_response_cookies(
        self,
        candidate: TokenRenewalCandidate,
        cookies_str: str,
        response_cookies: dict[str, str],
    ) -> str | None:
        """将接口下发的 Set-Cookie 合并进账号 Cookie 并写回数据库。

        Args:
            candidate: 当前续期候选账号。
            cookies_str: 本次请求使用的 Cookie 字符串。
            response_cookies: 接口响应下发的 Cookie 键值对。
        Returns:
            合并后的 Cookie 字符串；未下发新 Cookie 时原样返回；写入失败返回 ``None``。
        """
        if not response_cookies:
            return cookies_str

        merged_cookies_str = await merge_account_cookie_fields(
            candidate.account_row_id,
            candidate.account_id,
            response_cookies,
        )
        if merged_cookies_str:
            logger.info(
                f"【{self.task_name}】【{candidate.account_id}】已合并接口下发Cookie并写回数据库"
            )
        else:
            logger.error(
                f"【{self.task_name}】【{candidate.account_id}】接口下发Cookie合并写回失败，"
                "停止本次Token续期"
            )
        return merged_cookies_str

    async def _solve_captcha_and_merge_cookies(
        self,
        candidate: TokenRenewalCandidate,
        cookies_str: str,
        response_json: Any,
    ) -> str | None:
        """调用 WebSocket 过滑块，并将成功返回的 Cookie 增量合并入库。"""
        verification_url = self._captcha_url(response_json)
        if not verification_url:
            logger.error(
                f"【{self.task_name}】【{candidate.account_id}】Token触发风控但未返回滑块链接"
            )
            return None

        settings = get_settings()
        result = await solve_captcha_via_websocket(
            settings.websocket_service_url,
            account_id=candidate.account_id,
            url=verification_url,
            cookies=cookies_str,
            device_id=candidate.device_id,
        )
        if not result.get("success"):
            logger.error(
                f"【{self.task_name}】【{candidate.account_id}】滑块处理失败: "
                f"{result.get('message') or '未知错误'}"
            )
            return None

        result_data = result.get("data")
        new_cookies = result_data.get("cookies") if isinstance(result_data, dict) else None
        token_already_available = bool(
            isinstance(result_data, dict) and result_data.get("token_already_available")
        )
        if token_already_available:
            if isinstance(new_cookies, dict) and new_cookies:
                merged_cookies_str = await merge_account_cookie_fields(
                    candidate.account_row_id,
                    candidate.account_id,
                    new_cookies,
                )
                if not merged_cookies_str:
                    logger.error(
                        f"【{self.task_name}】【{candidate.account_id}】风控解除后的Cookie合并写回失败"
                    )
                    return None
            else:
                merged_cookies_str = cookies_str
            logger.info(
                f"【{self.task_name}】【{candidate.account_id}】重取验证链接时Token已可用，"
                "准备直接重试Token接口"
            )
            return merged_cookies_str

        if not isinstance(new_cookies, dict) or not new_cookies:
            logger.error(
                f"【{self.task_name}】【{candidate.account_id}】滑块成功但未返回新Cookie"
            )
            return None

        merged_cookies_str = await merge_account_cookie_fields(
            candidate.account_row_id,
            candidate.account_id,
            new_cookies,
        )
        if not merged_cookies_str:
            logger.error(
                f"【{self.task_name}】【{candidate.account_id}】滑块Cookie合并写回失败"
            )
            return None
        logger.info(
            f"【{self.task_name}】【{candidate.account_id}】滑块成功，已合并 "
            f"{len(new_cookies)} 个Cookie，准备使用新Cookie重试Token"
        )
        return merged_cookies_str

    async def _renew_candidate(
        self,
        candidate: TokenRenewalCandidate,
    ) -> TokenRenewalResult:
        """请求并条件写入单个账号的续期 Token。

        接口可能先返回令牌过期并下发新 _m_h5_tk（Set-Cookie），此时合并
        Cookie 后重试一次，与 WebSocket 侧 Token 刷新的处理口径一致。
        """
        async with self._semaphore:
            cookies_str = candidate.cookies_str
            result = None
            token_expired_retries = 0
            captcha_retries = 0
            failure_message: str | None = None
            while True:
                try:
                    result = await request_im_token(cookies_str, candidate.device_id)
                except asyncio.TimeoutError:
                    logger.error(f"【{self.task_name}】【{candidate.account_id}】请求超时")
                    return self._failed_result(candidate, "Token接口请求超时")
                except aiohttp.ClientError as exc:
                    message = f"Token接口网络错误：{type(exc).__name__}: {exc}"
                    logger.error(
                        f"【{self.task_name}】【{candidate.account_id}】网络错误: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return self._failed_result(candidate, message)
                except Exception as exc:
                    message = f"Token接口请求异常：{type(exc).__name__}: {exc}"
                    logger.error(
                        f"【{self.task_name}】【{candidate.account_id}】请求异常: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return self._failed_result(candidate, message)

                # 无论成功失败，接口下发的 Cookie（如新 _m_h5_tk）都要合并写回
                merged_response_cookies = await self._merge_response_cookies(
                    candidate, cookies_str, result.response_cookies
                )
                if merged_response_cookies is None:
                    return self._failed_result(candidate, "接口下发Cookie合并写回失败")
                cookies_str = merged_response_cookies

                # 与 WebSocket refresh_token 保持一致：成功 Token 优先，其次滑块，
                # 最后才处理单纯的 _m_h5_tk 令牌过期。
                if extract_im_access_token(result.response_json):
                    break

                if self._is_captcha_required_response(result.response_json):
                    if captcha_retries >= 1:
                        failure_message = "滑块验证重试已达上限"
                        logger.error(
                            f"【{self.task_name}】【{candidate.account_id}】滑块重试已达上限"
                        )
                        break
                    captcha_retries += 1
                    merged_cookies_str = await self._solve_captcha_and_merge_cookies(
                        candidate,
                        cookies_str,
                        result.response_json,
                    )
                    if not merged_cookies_str:
                        return self._failed_result(candidate, "滑块验证或Cookie合并写回失败")
                    cookies_str = merged_cookies_str
                    continue

                if self._is_token_expired_response(result.response_json):
                    if token_expired_retries >= 1:
                        failure_message = "令牌过期重试已达上限"
                        logger.error(
                            f"【{self.task_name}】【{candidate.account_id}】令牌过期重试已达上限"
                        )
                        break
                    token_expired_retries += 1
                    logger.warning(
                        f"【{self.task_name}】【{candidate.account_id}】检测到令牌过期，"
                        "使用新Cookie重试一次"
                    )
                    await asyncio.sleep(0.5)
                    continue
                break

            new_token = extract_im_access_token(result.response_json)
            if not new_token:
                response_text = json.dumps(result.response_json, ensure_ascii=False)[:500]
                logger.warning(
                    f"【{self.task_name}】【{candidate.account_id}】续期未成功: "
                    f"status={result.status_code}, response={response_text}"
                )
                if not failure_message:
                    response_ret = result.response_json.get("ret") if isinstance(result.response_json, dict) else None
                    ret_text = json.dumps(response_ret, ensure_ascii=False)[:300]
                    failure_message = (
                        f"Token接口返回失败（HTTP {result.status_code}）"
                        f"：{ret_text or '未返回错误说明'}"
                    )
                return self._failed_result(candidate, failure_message)

            renew_expire_at, ttl_hours = random_token_cache_expiry()
            checked_at = get_beijing_now_naive()
            try:
                async with async_session_maker() as session:
                    update_result = await session.execute(
                        update(TokenCache)
                        .where(
                            TokenCache.id == candidate.cache_id,
                            TokenCache.user_id == candidate.user_id,
                            TokenCache.device_id == candidate.device_id,
                            TokenCache.expire_at <= checked_at,
                            or_(
                                TokenCache.renew_expire_at.is_(None),
                                TokenCache.renew_expire_at <= checked_at,
                            ),
                        )
                        .values(token=new_token, renew_expire_at=renew_expire_at)
                    )
                    if update_result.rowcount != 1:
                        await session.rollback()
                        logger.info(
                            f"【{self.task_name}】【{candidate.account_id}】缓存已被其他流程更新，"
                            "放弃写入本次结果"
                        )
                        return self._failed_result(
                            candidate,
                            "Token缓存已被其他流程更新，本次未写入",
                        )
                    await session.commit()
            except Exception as exc:
                message = f"Token缓存写入失败：{type(exc).__name__}: {exc}"
                logger.error(
                    f"【{self.task_name}】【{candidate.account_id}】写入失败: "
                    f"{type(exc).__name__}: {exc}"
                )
                return self._failed_result(candidate, message)

            logger.info(
                f"【{self.task_name}】【{candidate.account_id}】续期成功: "
                f"续期到期日={renew_expire_at:%Y-%m-%d %H:%M:%S}, TTL={ttl_hours:.1f}小时"
            )
            return TokenRenewalResult(
                candidate=candidate,
                success=True,
                message=f"续期成功，TTL={ttl_hours:.1f}小时",
                renew_expire_at=renew_expire_at,
            )

token_renewal_task_service = TokenRenewalTask()
