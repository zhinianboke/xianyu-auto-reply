"""
IM Token 续期定时任务。

功能：
1. 查询启用账号中两个到期日均失效且当日无处理中风控日志的 Token 缓存
2. 使用缓存表已有 Device ID 请求最新 Token
3. 接口下发的 Set-Cookie（如新 _m_h5_tk）合并写回账号，令牌过期时重试一次
4. 仅更新 Token 和续期到期日，不修改原到期日
5. 支持调度循环和管理界面手动执行
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import aiohttp
from loguru import logger
from sqlalchemy import exists, or_, select, update

from common.db.session import async_session_maker
from common.models.risk_control_log import XYRiskControlLog
from common.models.token_cache import TokenCache
from common.models.xy_account import XYAccount
from common.services.im_token_api import extract_im_access_token, request_im_token
from common.utils.cookie_refresh import update_account_cookies_in_db
from common.utils.time_utils import get_beijing_now_naive, random_token_cache_expiry
from common.utils.xianyu_utils import trans_cookies


TOKEN_RENEWAL_MAX_CONCURRENCY = 5


@dataclass(frozen=True, slots=True)
class TokenRenewalCandidate:
    """一次 Token 续期请求所需的数据库快照。"""

    cache_id: int
    user_id: str
    account_id: str
    cookies_str: str
    device_id: str


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

            results = await asyncio.gather(
                *(self._renew_candidate(candidate) for candidate in candidates),
                return_exceptions=False,
            )
            renewed_count = sum(1 for renewed in results if renewed)
            logger.info(
                f"【{self.task_name}】执行完成: 候选={len(candidates)}, "
                f"成功={renewed_count}, 失败或已被其他流程更新={len(candidates) - renewed_count}"
            )
            return renewed_count

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

    async def _merge_response_cookies(
        self,
        candidate: TokenRenewalCandidate,
        cookies_str: str,
        response_cookies: dict[str, str],
    ) -> str:
        """将接口下发的 Set-Cookie 合并进账号 Cookie 并写回数据库。

        Args:
            candidate: 当前续期候选账号。
            cookies_str: 本次请求使用的 Cookie 字符串。
            response_cookies: 接口响应下发的 Cookie 键值对。
        Returns:
            合并后的 Cookie 字符串；未下发新 Cookie 时原样返回。
        """
        if not response_cookies:
            return cookies_str

        cookies = trans_cookies(cookies_str)
        cookies.update(response_cookies)
        merged_cookies_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        try:
            saved = await update_account_cookies_in_db(candidate.account_id, merged_cookies_str)
            if saved:
                logger.info(f"【{self.task_name}】【{candidate.account_id}】已合并接口下发Cookie并写回数据库")
            else:
                logger.warning(f"【{self.task_name}】【{candidate.account_id}】接口下发Cookie写回数据库失败")
        except Exception as exc:
            logger.warning(
                f"【{self.task_name}】【{candidate.account_id}】接口下发Cookie写回异常: "
                f"{type(exc).__name__}: {exc}"
            )
        return merged_cookies_str

    async def _renew_candidate(self, candidate: TokenRenewalCandidate) -> bool:
        """请求并条件写入单个账号的续期 Token。

        接口可能先返回令牌过期并下发新 _m_h5_tk（Set-Cookie），此时合并
        Cookie 后重试一次，与 WebSocket 侧 Token 刷新的处理口径一致。
        """
        async with self._semaphore:
            cookies_str = candidate.cookies_str
            result = None
            for attempt in range(2):
                try:
                    result = await request_im_token(cookies_str, candidate.device_id)
                except asyncio.TimeoutError:
                    logger.error(f"【{self.task_name}】【{candidate.account_id}】请求超时")
                    return False
                except aiohttp.ClientError as exc:
                    logger.error(
                        f"【{self.task_name}】【{candidate.account_id}】网络错误: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return False
                except Exception as exc:
                    logger.error(
                        f"【{self.task_name}】【{candidate.account_id}】请求异常: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return False

                # 无论成功失败，接口下发的 Cookie（如新 _m_h5_tk）都要合并写回
                cookies_str = await self._merge_response_cookies(
                    candidate, cookies_str, result.response_cookies
                )

                if attempt == 0 and self._is_token_expired_response(result.response_json):
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
                return False

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
                        return False
                    await session.commit()
            except Exception as exc:
                logger.error(
                    f"【{self.task_name}】【{candidate.account_id}】写入失败: "
                    f"{type(exc).__name__}: {exc}"
                )
                return False

            logger.info(
                f"【{self.task_name}】【{candidate.account_id}】续期成功: "
                f"续期到期日={renew_expire_at:%Y-%m-%d %H:%M:%S}, TTL={ttl_hours:.1f}小时"
            )
            return True


token_renewal_task_service = TokenRenewalTask()
