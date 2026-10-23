"""
在线聊天 IM 令牌管理。

功能：查询令牌缓存、获取新令牌、合并 Cookie，并委托 WebSocket 服务处理验证码。
由 GoofishImClient 继承，复用客户端账号状态和项目统一数据库、服务客户端。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import text

from app.services.websocket_client import websocket_client
from common.db.session import async_session_maker
from common.services.captcha.token_response import is_token_expired_response
from common.services.im_token_api import extract_im_access_token, request_im_token_with_fallback
from common.services.token_renewal_cache_service import mark_token_cache_expired, upsert_token_cache
from common.services.token_api_mode import get_token_api_mode_label, load_token_api_mode
from common.services.token_request_lock import TokenRequestLockError, token_request_lock
from common.utils.cookie_refresh import merge_cookies, update_account_cookies_in_db
from common.utils.time_utils import get_beijing_now_naive
from common.utils.xianyu_utils import trans_cookies
from .im_transport import REQUEST_TIMEOUT

# 风控滑块验证关键词：Token响应中出现任一关键词即表示被风控拦截（如"哎哟喂,被挤爆啦"），需过滑块
# 与 websocket 进程 cookie_token_manager.need_captcha_verification 保持一致
CAPTCHA_KEYWORDS = (
    "FAIL_SYS_USER_VALIDATE",  # 用户验证失败
    "RGV587_ERROR",            # 风控错误
    "哎哟喂,被挤爆啦",          # 被挤爆了（英文逗号）
    "哎哟喂，被挤爆啦",         # 被挤爆了（中文逗号）
    "挤爆了",                  # 被挤爆了
    "请稍后重试",              # 请稍后重试
    "punish?x5secdata",        # 惩罚页面
    "captcha",                 # 验证码
)
# 过滑块重试上限（防止无限递归）
CAPTCHA_MAX_RETRY = 1


class ImTokenMixin:
    """供在线聊天客户端复用的令牌缓存和刷新流程。"""

    # ==================== Token缓存（数据库） ====================
    # 缓存键使用 chat_{myid} 前缀，与自动回复WebSocket的缓存隔离，
    # 避免共用同一token/device_id导致IM服务器踢掉自动回复连接

    @property
    def _cache_user_id(self) -> str:
        """Token缓存键，加chat_前缀与自动回复隔离"""
        return f"chat_{self.myid}"

    async def _get_cached_token(self) -> Optional[Dict[str, str]]:
        """从数据库xy_token_cache获取缓存的token和device_id

        Returns:
            包含token和device_id的字典，不存在或已过期则返回None
        """
        self._last_token_cache_lookup_succeeded = False
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    text("""
                        SELECT token, device_id, expire_at
                        FROM xy_token_cache
                        WHERE user_id = :user_id
                        LIMIT 1
                    """),
                    {"user_id": self._cache_user_id},
                )
                row = result.fetchone()
                self._last_token_cache_lookup_succeeded = True

                if row:
                    token_val, device_id_val, expire_at = row
                    now = get_beijing_now_naive()
                    if expire_at and expire_at > now:
                        remaining = expire_at - now
                        hours = int(remaining.total_seconds() // 3600)
                        minutes = int((remaining.total_seconds() % 3600) // 60)
                        logger.info(
                            f"【{self.account_id}】Token缓存命中: "
                            f"user_id={self.myid}, "
                            f"剩余有效时间={hours}小时{minutes}分钟"
                        )
                        return {"token": token_val, "device_id": device_id_val}
                    else:
                        logger.info(
                            f"【{self.account_id}】Token缓存已过期: "
                            f"user_id={self.myid}, 过期时间={expire_at}"
                        )
                        await self._mark_cached_token_expired()
                else:
                    logger.info(
                        f"【{self.account_id}】Token缓存未命中: "
                        f"cache_key={self._cache_user_id}"
                    )
        except Exception as e:
            logger.warning(f"【{self.account_id}】获取Token缓存失败: {e}")
        return None

    async def _set_cached_token(self, token_val: str, device_id_val: str):
        """将token和device_id缓存到数据库

        使用 INSERT ... ON DUPLICATE KEY UPDATE 实现插入或更新
        基础过期时间由环境变量 TOKEN_CACHE_TTL_MIN_HOURS / TOKEN_CACHE_TTL_MAX_HOURS 控制，
        再追加 1~5 小时的秒级随机偏移；未配置时最终 TTL 为 6~15 小时

        Args:
            token_val: IM Token
            device_id_val: 设备ID
        """
        cache_write = await upsert_token_cache(
            token_user_id=self._cache_user_id,
            token=token_val,
            device_id=device_id_val,
        )
        if not cache_write.success:
            logger.warning(f"【{self.account_id}】{cache_write.message}")
            return
        logger.info(
            f"【{self.account_id}】Token已缓存到数据库 "
            f"(过期时间={cache_write.expire_at:%Y-%m-%d %H:%M:%S}, "
            f"TTL={cache_write.ttl_hours:.1f}小时)"
        )

    async def _mark_cached_token_expired(self):
        """标记已失效的聊天 Token 缓存，保留历史数据并避免覆盖并发更新。"""
        invalidation = await mark_token_cache_expired(
            token_user_id=self._cache_user_id,
        )
        if invalidation.success:
            logger.info(
                f"【{self.account_id}】{invalidation.message}: "
                f"cache_key={self._cache_user_id}"
            )
        else:
            logger.warning(f"【{self.account_id}】{invalidation.message}")

    # ==================== 内部方法 ====================

    async def _get_im_token(self) -> str:
        """在账号级 Redis 锁内获取 IM Token。

        Returns:
            数据库缓存或 Token 接口返回的 Token；失败时返回空值。
        """
        account_identifier = self.myid or self.account_id
        try:
            async with token_request_lock(account_identifier):
                return await self._get_im_token_with_lock()
        except TokenRequestLockError as exc:
            logger.error(f"【{self.account_id}】{exc}")
            return ""

    async def _get_im_token_with_lock(self) -> str:
        """持锁后复查数据库缓存，未命中时调用 Token 接口并写回。"""
        # 1. 先从数据库缓存获取
        cached = await self._get_cached_token()
        if cached:
            # 恢复缓存中的device_id，保持一致
            self.device_id = cached["device_id"]
            logger.info(
                f"【{self.account_id}】使用数据库缓存的Token和Device ID"
            )
            return cached["token"]
        if not self._last_token_cache_lookup_succeeded:
            logger.error(
                f"【{self.account_id}】Token缓存复查失败，本次未调用Token接口"
            )
            return ""

        # 2. 缓存未命中，调API获取
        token = await self._fetch_im_token_from_api()
        if token:
            if self._captcha_token_cache_saved:
                # 滑块服务端已写入同一聊天缓存，避免重复刷新到期时间。
                self._captcha_token_cache_saved = False
            else:
                await self._set_cached_token(token, self.device_id)
        return token

    async def _fetch_im_token_from_api(
        self, _retry: int = 0, _captcha_retry: int = 0
    ) -> str:
        """
        通过mtop API获取IM登录Token

        令牌过期时会从响应Set-Cookie中提取新Cookie，增量合并后更新到数据库和内存，
        然后使用新Cookie重试一次（最多重试1次，防止无限递归）。

        触发风控滑块（如"哎哟喂,被挤爆啦" / FAIL_SYS_USER_VALIDATE）时，委托 WebSocket
        进程过滑块获取最新Cookie，成功后清缓存并用新Cookie重试（最多重试 CAPTCHA_MAX_RETRY 次）。

        Args:
            _retry: 令牌过期内部重试计数，外部不需要传
            _captcha_retry: 过滑块内部重试计数，外部不需要传
        """
        try:
            # Token 接口方式实时查库，确保系统设置修改后无需重启即可生效。
            api_mode = await load_token_api_mode(self.account_id)
            logger.info(
                f"【{self.account_id}】获取IM Token，使用{get_token_api_mode_label(api_mode)}"
            )
            api_result = await request_im_token_with_fallback(
                self.cookies_str,
                self.device_id,
                api_mode=api_mode,
                timeout_seconds=REQUEST_TIMEOUT,
                log_tag=self.account_id,
            )
            if api_result.device_id and api_result.device_id != self.device_id:
                self.device_id = api_result.device_id
                logger.info(f"【{self.account_id}】已更新远程接口返回的Device ID")
            result = api_result.response_json

            # Token 接口下发的 Cookie 统一写回账号。
            new_cookies = api_result.response_cookies
            if new_cookies:
                merged_str = merge_cookies(self.cookies_str, new_cookies)
                self.cookies_str = merged_str
                self.cookies = trans_cookies(merged_str)
                cookie_saved = await update_account_cookies_in_db(
                    self.account_id,
                    merged_str,
                )
                if cookie_saved:
                    logger.info(
                        f"【{self.account_id}】已合并Token接口下发的 "
                        f"{len(new_cookies)} 个Cookie字段并更新到数据库"
                    )
                else:
                    logger.error(
                        f"【{self.account_id}】Token接口下发的Cookie写回数据库失败"
                    )

            # 检查令牌过期，使用新Cookie重试（最多1次）
            ret = result.get("ret", [])
            ret_str = str(ret)
            if is_token_expired_response(result):
                if _retry < 1:
                    logger.warning(
                        f"【{self.account_id}】令牌过期，已更新Cookie，准备重试获取Token（第{_retry + 1}次）"
                    )
                    return await self._fetch_im_token_from_api(_retry=_retry + 1)
                else:
                    logger.error(f"【{self.account_id}】令牌过期重试已达上限，放弃获取Token")
                    return ""

            # 检查是否触发风控滑块验证（如"哎哟喂,被挤爆啦"），委托过滑块后用新Cookie重试
            if self._is_captcha_required(ret_str, result):
                if _captcha_retry >= CAPTCHA_MAX_RETRY:
                    logger.error(f"【{self.account_id}】过滑块重试已达上限，放弃获取Token")
                    return ""
                if not await self._solve_captcha_via_websocket(result):
                    logger.error(f"【{self.account_id}】过滑块失败，放弃获取Token")
                    return ""
                logger.warning(
                    f"【{self.account_id}】过滑块成功，准备用新Cookie重试获取Token"
                    f"（第{_captcha_retry + 1}次）"
                )
                if self._captcha_token_cache_saved:
                    cached = await self._get_cached_token()
                    if cached:
                        self.device_id = cached["device_id"]
                        logger.info(
                            f"【{self.account_id}】使用WebSocket端已写入的聊天Token缓存"
                        )
                        return cached["token"]
                    logger.warning(
                        f"【{self.account_id}】WebSocket端报告Token缓存写入成功，"
                        "但本地未读取到有效缓存，继续重试Token接口"
                    )
                    self._captcha_token_cache_saved = False
                # 仅确认旧缓存已失效；条件更新不会覆盖其他流程刚写入的新 Token。
                await self._mark_cached_token_expired()
                return await self._fetch_im_token_from_api(
                    _retry=_retry, _captcha_retry=_captcha_retry + 1
                )

            access_token = extract_im_access_token(result) or ""
            if not access_token:
                logger.error(
                    f"【{self.account_id}】Token响应异常: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
            return access_token

        except Exception as e:
            logger.error(f"【{self.account_id}】获取IM Token异常: {e}")
            return ""

    def _is_captcha_required(self, ret_str: str, result: Dict[str, Any]) -> bool:
        """判断Token响应是否触发风控滑块验证（被挤爆 / 风控拦截）

        Args:
            ret_str: 响应 ret 字段的字符串形式
            result: 完整响应字典

        Returns:
            是否需要过滑块
        """
        for keyword in CAPTCHA_KEYWORDS:
            if keyword in ret_str:
                logger.info(f"【{self.account_id}】检测到风控滑块关键词: {keyword}")
                return True
        data = result.get("data", {})
        if isinstance(data, dict):
            url = data.get("url", "") or ""
            if any(flag in url for flag in ("punish", "captcha", "validate")):
                logger.info(f"【{self.account_id}】检测到风控验证URL")
                return True
        return False

    async def _solve_captcha_via_websocket(self, result: Dict[str, Any]) -> bool:
        """委托 WebSocket 进程过滑块，成功后合并新Cookie并写回数据库与内存

        backend-web 进程不具备本地浏览器过滑块能力（浏览器持久化目录与账号级互斥锁
        统一收敛在 WebSocket 进程），因此通过 HTTP 委托 /internal/captcha/solve 完成。
        过滑块成功返回的 x5sec 等风控Cookie会合并进当前实例并更新数据库，供本次重试使用。

        Args:
            result: Token接口返回的完整响应字典（含 data.url 验证链接）

        Returns:
            是否过滑块成功（成功时已更新 self.cookies / self.cookies_str / 数据库）
        """
        # 提取 punish 验证链接
        verification_url = ""
        data = result.get("data", {})
        if isinstance(data, dict):
            verification_url = data.get("url", "") or ""
        if not verification_url:
            logger.error(f"【{self.account_id}】未找到验证URL，无法过滑块")
            return False

        logger.info(
            f"【{self.account_id}】检测到风控，委托WebSocket过滑块: {verification_url[:80]}..."
        )
        self._captcha_token_cache_saved = False
        # 携带当前Cookie与设备ID：验证链接过期时 WebSocket 端可凭此重取新鲜链接
        resp = await websocket_client.solve_captcha(
            account_id=self.account_id,
            url=verification_url,
            call_type="local",
            cookies=self.cookies_str,
            device_id=self.device_id,
            account_row_id=self.account_row_id,
            token_user_id=self._cache_user_id,
            persist_token_cache=True,
            token_cache_write_mode="upsert",
        )

        if not (isinstance(resp, dict) and resp.get("success")):
            msg = resp.get("message", "") if isinstance(resp, dict) else ""
            logger.error(f"【{self.account_id}】过滑块失败: {msg}")
            return False

        response_data = resp.get("data")
        if not isinstance(response_data, dict):
            response_data = {}
        raw_cookies = response_data.get("cookies")
        new_cookies = raw_cookies if isinstance(raw_cookies, dict) else {}
        token_already_available = bool(response_data.get("token_already_available"))
        cookie_saved_by_websocket = bool(response_data.get("cookie_saved"))
        self._captcha_token_cache_saved = bool(response_data.get("token_cache_saved"))
        if not new_cookies and not token_already_available:
            logger.error(f"【{self.account_id}】过滑块返回成功但未获取到Cookie，判定为失败")
            return False

        if new_cookies:
            # 合并过滑块返回的Cookie（主要为 x5sec 等风控字段）并写回内存与数据库
            merged_cookies = {**self.cookies, **new_cookies}
            merged_cookies_str = "; ".join(
                f"{key}={value}" for key, value in merged_cookies.items()
            )
            if not cookie_saved_by_websocket:
                saved = await update_account_cookies_in_db(
                    self.account_id,
                    merged_cookies_str,
                )
                if not saved:
                    logger.error(f"【{self.account_id}】过滑块Cookie合并写回数据库失败")
                    return False
            self.cookies = merged_cookies
            self.cookies_str = merged_cookies_str
            logger.info(
                f"【{self.account_id}】过滑块成功，已合并 {len(new_cookies)} 个Cookie，"
                f"数据库写入方={'WebSocket端' if cookie_saved_by_websocket else '聊天端'}"
            )
        if token_already_available:
            logger.info(f"【{self.account_id}】重取验证链接时Token已可用，准备重试Token接口")
        return True
