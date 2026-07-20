"""
Cookie/Token管理模块
负责处理Cookie和Token相关的所有逻辑，包括：
- Token刷新
- 滑块验证检测和处理
- Cookie更新和重启
- 密码登录刷新
- Cookie有效性验证
- 浏览器刷新Cookie
- 扫码登录Cookie刷新
"""

import asyncio
import json
import random
import time
import aiohttp
from typing import Optional
from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting
from common.models.token_cache import TokenCache
from common.services.im_token_api import extract_im_access_token, request_im_token
from common.services.risk_control_log_query_service import (
    check_account_processing_risk_control_log,
    get_account_risk_control_lock,
)
from common.services.token_renewal_cache_service import mark_token_cache_expired
from common.services.captcha.concurrency import run_browser_task
from common.services.captcha.slider_mode import (
    SLIDER_MODE_REAL_MOUSE,
    refresh_slider_mode_from_database,
)
from common.services.captcha.token_refetch import request_fresh_captcha_url
from common.services.captcha.token_response import get_token_captcha_reason
from common.services.captcha.weighted_runner import real_mouse_weighted_runner
from common.utils.cookie_refresh import get_account_by_identity, update_account_cookies_in_db
from common.utils.xianyu_utils import trans_cookies
from common.utils.time_utils import get_beijing_now_naive, random_token_cache_expiry
from common.utils.token_cache import TokenCacheValidity, classify_token_cache_validity


STARTUP_EXPIRED_CACHE_REFRESH_JITTER_SECONDS = 120

class CookieTokenManager:
    """Cookie/Token管理器"""
    
    def __init__(self, parent):
        """
        初始化Cookie/Token管理器
        
        Args:
            parent: XianyuLive实例，用于访问共享资源
        """
        self.parent = parent
        self._startup_expired_cache_available = True
        self._last_cache_lookup_succeeded = True
        self._cached_token_in_use: str | None = None
    
    # ==================== 属性代理 ====================
    
    @property
    def cookie_id(self):
        return self.parent.cookie_id
    
    @property
    def cookies_str(self):
        return self.parent.cookies_str
    
    @cookies_str.setter
    def cookies_str(self, value):
        self.parent.cookies_str = value
    
    @property
    def cookies(self):
        return self.parent.cookies
    
    @cookies.setter
    def cookies(self, value):
        self.parent.cookies = value
    
    @property
    def session(self):
        return self.parent.session
    
    @property
    def current_token(self):
        return self.parent.current_token
    
    @current_token.setter
    def current_token(self, value):
        self.parent.current_token = value
    
    @property
    def last_token_refresh_time(self):
        return self.parent.last_token_refresh_time
    
    @last_token_refresh_time.setter
    def last_token_refresh_time(self, value):
        self.parent.last_token_refresh_time = value
    
    @property
    def last_token_refresh_status(self):
        return self.parent.last_token_refresh_status
    
    @last_token_refresh_status.setter
    def last_token_refresh_status(self, value):
        self.parent.last_token_refresh_status = value
    
    @property
    def device_id(self):
        return self.parent.device_id
    
    @property
    def myid(self):
        return self.parent.myid
    
    @property
    def max_captcha_verification_count(self):
        return self.parent.max_captcha_verification_count
    
    @property
    def last_message_received_time(self):
        return self.parent.last_message_received_time
    
    @property
    def message_cookie_refresh_cooldown(self):
        return self.parent.message_cookie_refresh_cooldown
    
    @property
    def restarted_in_browser_refresh(self):
        return self.parent.restarted_in_browser_refresh
    
    @restarted_in_browser_refresh.setter
    def restarted_in_browser_refresh(self, value):
        self.parent.restarted_in_browser_refresh = value
    
    # ==================== 辅助方法代理 ====================
    
    def _safe_str(self, obj):
        return self.parent._safe_str(obj)
    
    async def create_session(self):
        return await self.parent.create_session()
    
    async def send_token_refresh_notification(self, error_message: str, notification_type: str = "token_refresh",
                                             chat_id: str = None, attachment_path: str = None,
                                             verification_url: str = None):
        return await self.parent.send_token_refresh_notification(
            error_message=error_message,
            notification_type=notification_type,
            chat_id=chat_id,
            attachment_path=attachment_path,
            verification_url=verification_url
        )
    
    async def restart_instance(self, reason=None):
        return await self.parent.restart_instance(reason)

    async def _load_account_record(self):
        async with async_session_maker() as session:
            return await get_account_by_identity(
                self.cookie_id,
                owner_id=getattr(self.parent, 'user_id', None),
                session=session,
            )

    async def _load_account_info(self):
        account = await self._load_account_record()
        if not account:
            return None
        return {
            'cookie_value': account.cookie,
            'username': account.username,
            'password': account.login_password,
            'show_browser': account.show_browser,
        }


    # ==================== Token缓存（数据库） ====================

    async def _is_local_slider_disabled(self) -> bool:
        """实时读取“本机滑块不处理”开关，读取失败时禁止调用 Token API。"""
        try:
            async with async_session_maker() as session:
                value = (
                    await session.execute(
                        select(SystemSetting.value)
                        .where(SystemSetting.key == "captcha.local_slider_disabled")
                        .limit(1)
                    )
                ).scalar_one_or_none()
            return str(value or "false").strip().lower() == "true"
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】读取本机滑块处理开关失败，本次禁止调用Token API: {e}")
            return True

    async def _get_processing_risk_control_skip_result(
        self,
        action_name: str,
    ) -> tuple[bool, str | None]:
        """检查同账号风控占用，并返回是否跳过及可继续使用的当前 Token。

        Args:
            action_name: 当前准备执行的动作名称，用于日志说明。
        Returns:
            ``(是否跳过, 当前Token)``；没有现有 Token 时第二项为 ``None``。
        """
        processing_check = await check_account_processing_risk_control_log(
            self.cookie_id
        )
        if not processing_check.has_processing:
            return False, None

        if processing_check.success:
            self.last_token_refresh_status = "skipped_risk_control_processing"
        else:
            self.last_token_refresh_status = "skipped_risk_control_check_failed"

        current_token = self.current_token
        if current_token:
            logger.warning(
                f"【{self.cookie_id}】{processing_check.message}，"
                f"本次跳过{action_name}，继续沿用现有WebSocket连接"
            )
        else:
            logger.warning(
                f"【{self.cookie_id}】{processing_check.message}，"
                f"本次跳过{action_name}，等待下一轮Token刷新"
            )
        return True, current_token

    async def _get_cached_token(
        self,
        allow_expired: bool = False,
        *,
        expired_cache_reason: str = "local_slider_disabled",
    ) -> dict | None:
        """从数据库获取缓存的token和device_id
        
        原到期日有效时直接返回；原到期日失效但续期到期日有效时，
        将原到期日提升为续期到期日并返回续期 Token。启用本机滑块
        不处理时，可通过 allow_expired 继续返回已过期缓存。

        Args:
            allow_expired: 是否允许返回原到期日和续期到期日均已失效的缓存。
            expired_cache_reason: 允许使用过期缓存的原因，用于状态和日志区分。
        
        Returns:
            包含 token、device_id 和是否使用续期 Token 的字典；
            不存在或两个到期日都无效时返回 None。
        """
        self._last_cache_lookup_succeeded = False
        try:
            async with async_session_maker() as session:
                cache = (
                    await session.execute(
                        select(TokenCache)
                        .where(TokenCache.user_id == self.myid)
                        .limit(1)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                self._last_cache_lookup_succeeded = True

                if cache is None:
                    logger.info(f"【{self.cookie_id}】Token缓存未命中: user_id={self.myid}")
                    return None

                if not str(cache.token or "").strip() or not str(cache.device_id or "").strip():
                    logger.warning(f"【{self.cookie_id}】Token缓存内容不完整，按未命中处理: user_id={self.myid}")
                    return None

                now = get_beijing_now_naive()
                validity = classify_token_cache_validity(
                    cache.expire_at,
                    cache.renew_expire_at,
                    now,
                )
                if validity == TokenCacheValidity.CURRENT:
                    remaining = cache.expire_at - now
                    remaining_hours = int(remaining.total_seconds() // 3600)
                    remaining_minutes = int((remaining.total_seconds() % 3600) // 60)
                    logger.info(
                        f"【{self.cookie_id}】Token缓存命中: user_id={self.myid}, "
                        f"剩余有效时间={remaining_hours}小时{remaining_minutes}分钟"
                    )
                    return {
                        "token": cache.token,
                        "device_id": cache.device_id,
                        "renewal_promoted": False,
                        "expired_fallback": False,
                    }

                if validity == TokenCacheValidity.RENEWED:
                    cache.expire_at = cache.renew_expire_at
                    await session.commit()
                    logger.info(
                        f"【{self.cookie_id}】续期Token缓存命中: user_id={self.myid}, "
                        f"原到期日已更新为 {cache.expire_at:%Y-%m-%d %H:%M:%S}"
                    )
                    return {
                        "token": cache.token,
                        "device_id": cache.device_id,
                        "renewal_promoted": True,
                        "expired_fallback": False,
                    }

                logger.info(
                    f"【{self.cookie_id}】Token缓存原到期日和续期到期日均已失效: "
                    f"user_id={self.myid}, 原到期日={cache.expire_at}, "
                    f"续期到期日={cache.renew_expire_at}"
                )
                if allow_expired:
                    reason_text = (
                        "WebSocket启动首次连接"
                        if expired_cache_reason == "websocket_startup"
                        else "本机滑块不处理已开启"
                    )
                    logger.warning(
                        f"【{self.cookie_id}】{reason_text}，暂时使用已过期Token缓存尝试连接"
                    )
                    return {
                        "token": cache.token,
                        "device_id": cache.device_id,
                        "renewal_promoted": False,
                        "expired_fallback": True,
                        "expired_fallback_reason": expired_cache_reason,
                    }
        except Exception as e:
            self._last_cache_lookup_succeeded = False
            logger.warning(f"【{self.cookie_id}】获取Token缓存失败: {e}")
        return None

    async def _use_cached_token(self, cached: dict) -> str:
        """将数据库缓存写入当前实例，并在续期 Token 生效时触发重连。

        Args:
            cached: 包含 Token、Device ID 和续期提升标记的缓存数据。

        Returns:
            已写入当前实例的 Token。
        """
        cached_token = cached["token"]
        cached_device_id = cached["device_id"]
        self.parent.device_id = cached_device_id
        self.current_token = cached_token
        self._cached_token_in_use = cached_token
        self.last_token_refresh_time = time.time()
        self.last_token_refresh_status = "success_from_cache"
        self.parent._using_expired_startup_token = False
        logger.info(f"【{self.cookie_id}】使用数据库缓存的Token和Device ID")
        logger.info(f"【{self.cookie_id}】缓存Token: {cached_token}")
        logger.info(f"【{self.cookie_id}】缓存Device ID: {cached_device_id}")
        if cached.get("expired_fallback"):
            reason = cached.get("expired_fallback_reason")
            if reason == "websocket_startup":
                self.last_token_refresh_status = "success_from_expired_startup_cache"
                self.parent._using_expired_startup_token = True
                token_manager = getattr(self.parent, "token_manager", None)
                if token_manager is not None:
                    refresh_jitter = random.uniform(
                        0,
                        STARTUP_EXPIRED_CACHE_REFRESH_JITTER_SECONDS,
                    )
                    token_manager.last_cookie_refresh_time = time.time() + refresh_jitter
                    refresh_delay = token_manager.cookie_refresh_interval + refresh_jitter
                    logger.warning(
                        f"【{self.cookie_id}】启动阶段使用过期Token缓存连接，"
                        f"将在约{refresh_delay:.0f}秒后自动刷新Token"
                    )
            else:
                self.last_token_refresh_status = "success_from_expired_cache"
        elif cached.get("renewal_promoted"):
            self.last_token_refresh_status = "success_from_renewal"
            await self._reconnect_websocket_for_renewed_token()
        return cached_token

    async def _reconnect_websocket_for_renewed_token(self) -> None:
        """续期 Token 生效后关闭现有连接，由主循环携带新 Token 重连。"""
        connection_manager = getattr(self.parent, "connection_manager", None)
        websocket = getattr(connection_manager, "ws", None)
        if websocket is None or getattr(websocket, "closed", True):
            return

        logger.info(f"【{self.cookie_id}】续期Token已生效，准备重连WebSocket")
        await websocket.close(code=1000, reason="Token续期生效")

    async def _set_cached_token(self, token: str, device_id: str):
        """将token和device_id缓存到数据库
        
        使用 INSERT ... ON DUPLICATE KEY UPDATE 实现插入或更新
        基础过期时间由环境变量 TOKEN_CACHE_TTL_MIN_HOURS / TOKEN_CACHE_TTL_MAX_HOURS 控制，
        再追加 1~5 小时的秒级随机偏移；未配置时最终 TTL 为 6~15 小时

        Args:
            token: IM Token
            device_id: 设备ID
        """
        try:
            from sqlalchemy import text

            # 基础 TTL 默认 5~10 小时，再追加 1~5 小时秒级随机偏移
            expire_at, ttl_hours = random_token_cache_expiry()
            
            async with async_session_maker() as session:
                await session.execute(
                    text("""
                        INSERT INTO xy_token_cache
                            (user_id, token, device_id, expire_at, renew_expire_at, created_at, updated_at)
                        VALUES (:user_id, :token, :device_id, :expire_at, NULL, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE 
                            token = VALUES(token),
                            device_id = VALUES(device_id),
                            expire_at = VALUES(expire_at),
                            renew_expire_at = NULL,
                            updated_at = NOW()
                    """),
                    {
                        "user_id": self.myid,
                        "token": token,
                        "device_id": device_id,
                        "expire_at": expire_at
                    }
                )
                await session.commit()
                self._cached_token_in_use = token
                logger.info(f"【{self.cookie_id}】Token已缓存到数据库 (过期时间={expire_at.strftime('%Y-%m-%d %H:%M:%S')}, TTL={ttl_hours:.1f}小时)")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】缓存Token到数据库失败: {e}")

    async def _delete_cached_token(self):
        """将当前失效 Token 缓存标记为失效，不物理删除历史数据。"""
        invalidation = await mark_token_cache_expired(
            token_user_id=self.myid,
            expected_token=self._cached_token_in_use,
            expected_device_id=self.device_id,
        )
        if invalidation.success:
            logger.info(f"【{self.cookie_id}】{invalidation.message}: user_id={self.myid}")
        else:
            logger.warning(f"【{self.cookie_id}】{invalidation.message}")

    # ==================== Cookie更新 ====================

    async def update_config_cookies(self):
        """更新数据库中的cookies（不会覆盖账号密码等其他字段）"""
        try:
            # 更新数据库中的Cookie
            if hasattr(self.parent, 'cookie_id') and self.cookie_id:
                try:
                    # 获取当前Cookie的用户ID，避免在刷新时改变所有者
                    current_user_id = None
                    if hasattr(self.parent, 'user_id') and self.parent.user_id:
                        current_user_id = self.parent.user_id

                    # 打印要保存的x5sec值
                    cookies_dict = trans_cookies(self.cookies_str)
                    logger.warning(f"【{self.cookie_id}】update_config_cookies保存的x5sec: {cookies_dict.get('x5sec', '无')[:80]}...")
                    
                    # 使用 update_cookie_account_info 避免覆盖其他字段
                    success = await update_account_cookies_in_db(
                        self.cookie_id, 
                        self.cookies_str,
                        owner_id=current_user_id,
                    )
                    if not success:
                        logger.warning(f"更新Cookie到数据库失败: {self.cookie_id}")
                    else:
                        logger.warning(f"已更新Cookie到数据库: {self.cookie_id}")
                except Exception as e:
                    logger.error(f"更新数据库Cookie失败: {self._safe_str(e)}")
                    await self.send_token_refresh_notification(f"数据库Cookie更新失败: {str(e)}", "db_update_failed")
            else:
                logger.warning("Cookie ID不存在，无法更新数据库")
                await self.send_token_refresh_notification("Cookie ID不存在，无法更新数据库", "cookie_id_missing")

        except Exception as e:
            logger.error(f"更新Cookie失败: {self._safe_str(e)}")
            await self.send_token_refresh_notification(f"Cookie更新失败: {str(e)}", "cookie_update_failed")

    # ==================== 滑块验证检测 ====================

    def need_captcha_verification(self, res_json: dict) -> bool:
        """检查响应是否需要滑块验证"""
        try:
            reason = get_token_captcha_reason(res_json)
            if reason:
                logger.info(f"【{self.cookie_id}】检测到需要滑块验证: {reason}")
                return True
            return False

        except Exception as e:
            logger.error(f"【{self.cookie_id}】检查是否需要滑块验证时出错: {self._safe_str(e)}")
            return False


    # ==================== 滑块验证处理 ====================

    def _request_captcha_url_sync(self) -> Optional[str]:
        """同步重新请求 token 接口，提取一个新鲜的滑块验证链接。

        说明：滑块验证在独立线程中执行（asyncio.to_thread），而浏览器需要等待并发槽位/
        账号锁并完成启动，期间最初拿到的 punish?x5secdata 链接极易过期，导致页面显示
        "抱歉，页面访问出现了问题"。本方法在浏览器就绪后被回调，使用同步 requests 重新
        触发一次 token 接口，拿到最新的验证链接再交给浏览器导航，从源头规避链接过期。

        Returns:
            新的验证 URL；若接口已不再要求验证或解析失败则返回 None（此时沿用原链接）。
        """
        try:
            from app.services.captcha.slider_stealth import CAPTCHA_NOT_REQUIRED

            # 幂等缓存：本轮若已确认 token 可用，直接返回哨兵，绝不重复请求 token 接口。
            # 这样即便 run()/兜底编排层多次回调本方法，也只会真正请求一次，避免频繁调用。
            if getattr(self, '_refetch_token_ok', False):
                return CAPTCHA_NOT_REQUIRED

            logger.info(f"【{self.cookie_id}】浏览器就绪，重新请求新鲜的滑块验证链接...")
            # 与远程过滑块接口共用同一份"凭 Cookie 重取链接"逻辑（common.token_refetch）
            res = request_fresh_captcha_url(
                self.cookie_id, self.cookies, self.cookies_str, self.device_id
            )

            # 风控已解除、token 直接可用：缓存结果并返回哨兵，让上层提前结束滑块流程、直接采用新 token
            if res.get("token_ok"):
                try:
                    self._refetch_token_ok = True
                    self._refetch_new_token = res.get("new_token")
                    # 捕获接口可能下发的刷新后 cookie
                    self._refetch_new_cookies = res.get("new_cookies") or {}
                except Exception:
                    pass
                return CAPTCHA_NOT_REQUIRED

            fresh_url = res.get("fresh_url")
            if fresh_url:
                return fresh_url

            # 未返回新链接：沿用原链接
            return None
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】重新获取滑块验证链接失败，沿用原链接: {self._safe_str(e)}")
            return None

    async def _load_remote_captcha_config(self) -> dict | None:
        """读取全局"远程过滑块"配置（system_settings，仅管理员可配）。

        Returns:
            dict {url, secret, pass_cookies, device_id}；未配置或读取失败返回 None（此时走本机逻辑）。
            - pass_cookies 为 True 时表示"调用远程接口时传递账号 Cookie"（默认关闭）；
            - device_id 仅在 pass_cookies 开启时一并下发，供远程端在链接过期时重取新链接。
        """
        try:
            from common.db.session import async_session_maker
            from common.models.system_setting import SystemSetting
            from sqlalchemy import select

            async with async_session_maker() as session:
                rows = (await session.execute(
                    select(SystemSetting).where(
                        SystemSetting.key.in_(
                            [
                                "captcha.remote_service_url",
                                "captcha.remote_secret_key",
                                "captcha.remote_pass_cookies",
                            ]
                        )
                    )
                )).scalars().all()
            m = {r.key: (r.value or "") for r in rows}
            url = (m.get("captcha.remote_service_url") or "").strip()
            secret = (m.get("captcha.remote_secret_key") or "").strip()
            pass_cookies = (m.get("captcha.remote_pass_cookies") or "").strip().lower() == "true"
            if url and secret:
                return {
                    "url": url,
                    "secret": secret,
                    "pass_cookies": pass_cookies,
                    # 仅开启开关时下发 device_id，未开启则不携带任何账号信息
                    "device_id": (self.device_id or "") if pass_cookies else "",
                }
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】读取远程过滑块配置失败（走本机逻辑）: {self._safe_str(e)}")
        return None

    async def handle_captcha_verification(self, res_json: dict) -> str:
        """处理滑块验证，返回新的cookies字符串"""
        try:
            import os
            
            # 检查消息接收冷却时间 - 收到消息后5分钟内不执行滑块验证
            current_time = time.time()
            time_since_last_message = current_time - self.last_message_received_time
            if self.last_message_received_time > 0 and time_since_last_message < self.message_cookie_refresh_cooldown:
                remaining_time = self.message_cookie_refresh_cooldown - time_since_last_message
                remaining_minutes = int(remaining_time // 60)
                remaining_seconds = int(remaining_time % 60)
                logger.info(f"【{self.cookie_id}】收到消息后冷却中，暂停滑块验证，还需等待 {remaining_minutes}分{remaining_seconds}秒")
                return None
            
            logger.info(f"【{self.cookie_id}】开始处理滑块验证...")

            # 获取验证URL
            verification_url = None
            data = res_json.get('data', {})
            if isinstance(data, dict) and 'url' in data:
                verification_url = data.get('url')

            if not verification_url:
                logger.info(f"【{self.cookie_id}】未找到验证URL，认为不需要滑块验证")
                return None

            logger.info(f"【{self.cookie_id}】验证URL: {verification_url}")
            
            # 同账号的“检查处理中状态 + 创建日志”使用同一临界区，避免并发重复滑块。
            log_id = None
            captcha_start_time = time.time()
            async with get_account_risk_control_lock(self.cookie_id):
                should_skip_captcha, existing_token = (
                    await self._get_processing_risk_control_skip_result("滑块处理")
                )
                if should_skip_captcha:
                    return None
                try:
                    from common.db.compat import db_manager
                    log_id = db_manager.add_risk_control_log(
                        cookie_id=self.cookie_id,
                        event_type='slider_captcha',
                        event_description=f'触发场景: Token刷新, URL: {verification_url}',
                        processing_status='processing'
                    )
                    if log_id:
                        logger.info(f"【{self.cookie_id}】风控日志记录成功，ID: {log_id}")
                except Exception as log_e:
                    logger.error(f"【{self.cookie_id}】记录风控日志失败: {log_e}")
            if not log_id:
                self.last_token_refresh_status = "failed_risk_log_create"
                logger.error(
                    f"【{self.cookie_id}】创建风控处理日志失败，本次不启动滑块任务"
                )
                return None

            try:
                from app.services.captcha.slider_stealth import run_slider_verification_with_fallback

                # 重置"重取链接时 token 已可用"标志，避免读到上一次的残留值
                self._refetch_token_ok = False
                self._refetch_new_token = None
                self._refetch_new_cookies = {}

                # 读取全局"远程过滑块"配置（system_settings，仅管理员可配）。
                # 配置了则优先走远程接口；远程超时/不可用时回退本机逻辑。
                remote_config = await self._load_remote_captcha_config()

                # 真实鼠标任务先按权重排队，其他模式保持使用原浏览器任务专用线程池；
                # 两条路径都不占用 asyncio 默认线程池，避免饿死 aiohttp 的 DNS 解析。
                # run_slider_verification_with_fallback: 远程(可选)→真人/主引擎(Playwright)→DrissionPage 兜底
                # 返回 (是否成功, cookies, 通过引擎: remote/real_mouse/playwright/drissionpage/None)
                slider_args = (
                    f"{self.cookie_id}", verification_url, True, False, 20,
                    self.cookies_str, self._request_captcha_url_sync, remote_config,
                )
                selected_slider_mode = await refresh_slider_mode_from_database()
                if (
                    remote_config is None
                    and selected_slider_mode == SLIDER_MODE_REAL_MOUSE
                ):
                    # 本机真实鼠标任务先进入前置本地队列，再提交给原浏览器执行器。
                    success, cookies, captcha_engine = await real_mouse_weighted_runner.submit(
                        "local",
                        run_slider_verification_with_fallback,
                        *slider_args,
                        weight_class="local",
                        slider_mode=selected_slider_mode,
                    )
                else:
                    success, cookies, captcha_engine = await run_browser_task(
                        run_slider_verification_with_fallback,
                        *slider_args,
                        slider_mode=selected_slider_mode,
                    )

                # 重取链接时发现 token 已可用（风控解除，无需滑块）：直接采用，跳过滑块结果处理。
                # 合并接口可能下发的刷新 cookie，并返回 cookies_str，让上层 refresh_token
                # 清缓存后重试 token 刷新（此时风控已解除，会直接成功）。
                if getattr(self, '_refetch_token_ok', False):
                    logger.info(f"【{self.cookie_id}】滑块流程中检测到 token 已可用，直接采用，跳过滑块验证")
                    try:
                        if getattr(self, '_refetch_new_cookies', None):
                            self.cookies.update(self._refetch_new_cookies)
                            self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                            await self.update_config_cookies()
                            logger.info(f"【{self.cookie_id}】已合并重取 token 时下发的刷新 cookie")
                    except Exception as merge_e:
                        logger.warning(f"【{self.cookie_id}】合并重取 cookie 失败（可忽略）: {self._safe_str(merge_e)}")

                    captcha_duration = time.time() - captcha_start_time
                    if log_id:
                        try:
                            from common.db.compat import db_manager
                            db_manager.update_risk_control_log(
                                log_id=log_id,
                                processing_status='success',
                                processing_result=(
                                    f'重取验证链接时风控已解除，token 直接可用，无需滑块，'
                                    f'耗时: {captcha_duration:.2f}秒'
                                ),
                            )
                        except Exception as update_e:
                            logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")

                    self._refetch_token_ok = False
                    return self.cookies_str

                if success and cookies:
                    logger.info(f"【{self.cookie_id}】滑块验证成功，获取到新的cookies")
                    # 打印滑块验证返回的全部cookies
                    logger.warning(f"【{self.cookie_id}】滑块验证返回的全部cookies: {cookies}")
                    
                    # 更新风控日志为成功状态
                    captcha_duration = time.time() - captcha_start_time
                    if log_id:
                        try:
                            from common.db.compat import db_manager
                            engine_label_map = {
                                'drissionpage': '兜底引擎(DrissionPage)',
                                'real_mouse': '真人鼠标引擎(RealMouse)',
                                'remote': '远程接口(Remote)',
                                'playwright': '主引擎(Playwright)',
                            }
                            engine_label = engine_label_map.get(captcha_engine, '主引擎(Playwright)')
                            db_manager.update_risk_control_log(
                                log_id=log_id,
                                processing_status='success',
                                captcha_engine=captcha_engine,
                                processing_result=f'滑块验证成功（{engine_label}），耗时: {captcha_duration:.2f}秒'
                            )
                        except Exception as update_e:
                            logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")

                    # 只提取x5sec相关的cookie值进行更新
                    updated_cookies = self.cookies.copy()
                    new_cookie_count = 0
                    updated_cookie_count = 0
                    x5sec_cookies = {}

                    for cookie_name, cookie_value in cookies.items():
                        cookie_name_lower = cookie_name.lower()
                        if cookie_name_lower.startswith('x5') or 'x5sec' in cookie_name_lower:
                            x5sec_cookies[cookie_name] = cookie_value

                    logger.info(f"【{self.cookie_id}】找到{len(x5sec_cookies)}个x5相关cookies")

                    # 滑块视觉验证通过但未下发任何 x5* cookie：服务端实际并未放行（典型场景为
                    # 浏览器/HTTP 出口 IP 不一致或风控环境异常）。若仍按"成功"返回 cookies_str，
                    # 上层 refresh_token 会认为滑块成功并立即重试 token 刷新，但 cookies 实际未变，
                    # token 接口必然再次返回 FAIL_SYS_USER_VALIDATE → 又触发滑块，形成死循环。
                    # 这里显式判定失败，让上层走 failed_captcha 分支（不计入禁用计数），
                    # 避免账号被误累加 _token_fetch_failures 直至 10 次自动禁用。
                    if not x5sec_cookies:
                        logger.error(
                            f"【{self.cookie_id}】滑块视觉验证通过但未获取到任何 x5 相关 cookie，"
                            f"判定为失败（浏览器返回的 cookies: {list(cookies.keys())}）"
                        )
                        captcha_duration = time.time() - captcha_start_time
                        if log_id:
                            try:
                                from common.db.compat import db_manager
                                db_manager.update_risk_control_log(
                                    log_id=log_id,
                                    processing_status='failed',
                                    processing_result=(
                                        f'滑块视觉通过但未下发 x5sec cookie（疑似环境/IP 风控），'
                                        f'耗时: {captcha_duration:.2f}秒'
                                    ),
                                )
                            except Exception as update_e:
                                logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")
                        return None

                    for cookie_name, cookie_value in x5sec_cookies.items():
                        if cookie_name in updated_cookies:
                            if updated_cookies[cookie_name] != cookie_value:
                                updated_cookies[cookie_name] = cookie_value
                                updated_cookie_count += 1
                        else:
                            updated_cookies[cookie_name] = cookie_value
                            new_cookie_count += 1

                    cookies_str = "; ".join([f"{k}={v}" for k, v in updated_cookies.items()])

                    # 更新数据库
                    try:
                        old_cookies_str = self.cookies_str
                        old_cookies_dict = self.cookies.copy()

                        self.cookies_str = cookies_str
                        self.cookies = updated_cookies
                        
                        # 打印更新后的x5sec值
                        logger.warning(f"【{self.cookie_id}】准备保存到数据库的x5sec: {updated_cookies.get('x5sec', '无')}")

                        await self.update_config_cookies()
                        logger.info(f"【{self.cookie_id}】滑块验证成功后，数据库cookies已自动更新")
                        logger.info(f"【{self.cookie_id}】滑块验证成功: 新增{new_cookie_count}个x5, 更新{updated_cookie_count}个x5")

                        await self.send_token_refresh_notification(
                            f"滑块验证成功，cookies已自动更新到数据库",
                            "captcha_success_auto_update"
                        )

                    except Exception as update_e:
                        logger.error(f"【{self.cookie_id}】自动更新数据库cookies失败: {self._safe_str(update_e)}")
                        self.cookies_str = old_cookies_str
                        self.cookies = old_cookies_dict

                    return cookies_str
                else:
                    remote_fail_reason = None
                    captcha_engine_for_log = captcha_engine
                    if isinstance(captcha_engine, str) and captcha_engine.startswith("remote:"):
                        remote_fail_reason = captcha_engine.split(":", 1)[1].strip() or "远程过滑块未通过"
                        captcha_engine_for_log = "remote"

                    if remote_fail_reason:
                        logger.error(f"【{self.cookie_id}】滑块验证失败: {remote_fail_reason}")
                    else:
                        logger.error(f"【{self.cookie_id}】滑块验证失败")
                    
                    # 更新风控日志为失败状态
                    captcha_duration = time.time() - captcha_start_time
                    if log_id:
                        try:
                            from common.db.compat import db_manager
                            processing_result = (
                                f'远程过滑块失败：{remote_fail_reason}，耗时: {captcha_duration:.2f}秒'
                                if remote_fail_reason
                                else f'滑块验证失败，耗时: {captcha_duration:.2f}秒'
                            )
                            update_kwargs = {
                                "processing_status": "failed",
                                "processing_result": processing_result,
                            }
                            if captcha_engine_for_log == "remote":
                                update_kwargs["captcha_engine"] = "remote"
                            if remote_fail_reason:
                                update_kwargs["error_message"] = remote_fail_reason
                            db_manager.update_risk_control_log(
                                log_id=log_id,
                                **update_kwargs,
                            )
                        except Exception as update_e:
                            logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")
                    
                    return None

            except ImportError as import_e:
                logger.error(f"【{self.cookie_id}】滑块验证导入失败: {import_e}")
                
                # 更新风控日志为异常状态
                if log_id:
                    try:
                        from common.db.compat import db_manager
                        db_manager.update_risk_control_log(
                            log_id=log_id,
                            processing_status='error',
                            error_message='滑块验证模块未安装'
                        )
                    except Exception:
                        pass
                
                await self.send_token_refresh_notification(
                    f"滑块验证功能不可用，请安装Playwright",
                    "captcha_dependency_missing"
                )
                return None

            except asyncio.CancelledError:
                # 任务被取消，记录日志并重新抛出
                logger.warning(f"【{self.cookie_id}】滑块验证任务被取消")
                captcha_duration = time.time() - captcha_start_time
                if log_id:
                    try:
                        from common.db.compat import db_manager
                        db_manager.update_risk_control_log(
                            log_id=log_id,
                            processing_status='cancelled',
                            processing_result=f'任务被取消，耗时: {captcha_duration:.2f}秒'
                        )
                    except Exception:
                        pass
                raise

            except Exception as stealth_e:
                logger.error(f"【{self.cookie_id}】滑块验证异常: {self._safe_str(stealth_e)}")
                
                # 更新风控日志为异常状态
                captcha_duration = time.time() - captcha_start_time
                if log_id:
                    try:
                        from common.db.compat import db_manager
                        db_manager.update_risk_control_log(
                            log_id=log_id,
                            processing_status='error',
                            processing_result=f'滑块验证异常，耗时: {captcha_duration:.2f}秒',
                            error_message=self._safe_str(stealth_e)
                        )
                    except Exception:
                        pass
                
                return None

        except asyncio.CancelledError:
            logger.warning(f"【{self.cookie_id}】处理滑块验证时任务被取消")
            raise
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理滑块验证时出错: {self._safe_str(e)}")
            return None

    # ==================== Cookie更新并重启 ====================

    async def update_cookies_and_restart(self, new_cookies_str: str):
        """更新cookies并重启任务"""
        try:
            logger.info(f"【{self.cookie_id}】开始更新cookies并重启任务...")

            if not new_cookies_str or not new_cookies_str.strip():
                logger.error(f"【{self.cookie_id}】新cookies为空，无法更新")
                return False

            try:
                new_cookies_dict = trans_cookies(new_cookies_str)
                if not new_cookies_dict:
                    logger.error(f"【{self.cookie_id}】新cookies解析失败")
                    return False
            except Exception as parse_e:
                logger.error(f"【{self.cookie_id}】新cookies解析异常: {self._safe_str(parse_e)}")
                return False

            # 合并cookies
            current_cookies_dict = trans_cookies(self.cookies_str)
            merged_cookies_dict = current_cookies_dict.copy()

            for key, value in new_cookies_dict.items():
                merged_cookies_dict[key] = value

            merged_cookies_str = '; '.join([f"{k}={v}" for k, v in merged_cookies_dict.items()])

            # 更新实例cookies
            self.cookies_str = merged_cookies_str
            self.cookies = merged_cookies_dict

            # 更新数据库
            await self.update_config_cookies()
            logger.info(f"【{self.cookie_id}】cookies已更新到数据库")

            # Cookie已变更，清除旧的Token缓存（新Cookie需要重新获取Token）
            await self._delete_cached_token()

            # 重启实例
            await self.restart_instance("Cookie更新后重启")
            return True

        except Exception as e:
            logger.error(f"【{self.cookie_id}】更新cookies并重启失败: {self._safe_str(e)}")
            return False


    # ==================== Token刷新核心逻辑 ====================

    async def refresh_token(self, captcha_retry_count: int = 0, token_expiry_retry_count: int = 0):
        """刷新token
        
        Args:
            captcha_retry_count: 滑块验证重试次数，用于防止无限递归
            token_expiry_retry_count: 令牌过期重试次数（FAIL_SYS_TOKEN_EXOIRED/EXPIRED），用于防止无限重试
        """
        notification_sent = False
        
        try:
            # 检查账号是否已禁用
            from app.services.captcha.concurrency import should_skip_account
            if should_skip_account(self.cookie_id):
                logger.warning(f"【{self.cookie_id}】账号已禁用，跳过token刷新")
                return None
            
            logger.info(f"【{self.cookie_id}】开始刷新token... (滑块验证重试次数: {captcha_retry_count})")
            self.last_token_refresh_status = "started"

            is_initial_cache_attempt = bool(
                captcha_retry_count == 0
                and token_expiry_retry_count == 0
                and getattr(self, "_startup_expired_cache_available", True)
            )
            
            # 开关每次均实时查库，确保运行中的 WebSocket 无需重启即可生效。
            local_slider_disabled = await self._is_local_slider_disabled()
            if local_slider_disabled:
                cached = await self._get_cached_token(allow_expired=True)
                if cached:
                    return await self._use_cached_token(cached)

                self.current_token = None
                self.last_token_refresh_status = "skipped_local_slider_disabled"
                logger.warning(
                    f"【{self.cookie_id}】本机滑块不处理已开启且Token缓存不存在，"
                    "跳过该账号并等待下次轮询"
                )
                return None

            # 常规模式仅在首次调用时读取有效缓存，重试时保持原有接口处理逻辑。
            if captcha_retry_count == 0 and token_expiry_retry_count == 0:
                cached = await self._get_cached_token(
                    allow_expired=is_initial_cache_attempt,
                    expired_cache_reason="websocket_startup",
                )
                if is_initial_cache_attempt and not getattr(
                    self,
                    "_last_cache_lookup_succeeded",
                    True,
                ):
                    self.last_token_refresh_status = "skipped_startup_cache_lookup_failed"
                    logger.warning(
                        f"【{self.cookie_id}】启动阶段读取Token缓存失败，"
                        "本次不调用Token接口，保留启动缓存兜底机会等待下一轮"
                    )
                    return self.current_token
                if is_initial_cache_attempt:
                    self._startup_expired_cache_available = False
                if cached:
                    return await self._use_cached_token(cached)

            should_skip_refresh, existing_token = (
                await self._get_processing_risk_control_skip_result("Token刷新")
            )
            if should_skip_refresh:
                return existing_token
            self.restarted_in_browser_refresh = False

            # 检查滑块验证重试次数
            if captcha_retry_count >= self.max_captcha_verification_count:
                logger.error(f"【{self.cookie_id}】滑块验证重试次数已达上限 ({self.max_captcha_verification_count})，停止重试")
                await self.send_token_refresh_notification(
                    f"滑块验证重试次数已达上限，请手动处理",
                    "captcha_max_retries_exceeded"
                )
                notification_sent = True
                self.last_token_refresh_status = "failed_captcha_max_retries"
                return None

            # 检查消息接收冷却时间
            current_time = time.time()
            time_since_last_message = current_time - self.last_message_received_time
            if self.last_message_received_time > 0 and time_since_last_message < self.message_cookie_refresh_cooldown:
                remaining_time = self.message_cookie_refresh_cooldown - time_since_last_message
                remaining_minutes = int(remaining_time // 60)
                remaining_seconds = int(remaining_time % 60)
                logger.info(f"【{self.cookie_id}】收到消息后冷却中，放弃本次token刷新，还需等待 {remaining_minutes}分{remaining_seconds}秒")
                self.last_token_refresh_status = "skipped_cooldown"
                return None

            # 从数据库重新加载最新的cookie（滑块验证重试时跳过，使用内存中已更新的Cookie）
            logger.info(f"【{self.cookie_id}】开始执行Cookie刷新任务...")
            if captcha_retry_count > 0:
                logger.warning(f"【{self.cookie_id}】滑块验证重试中，跳过从数据库重新加载Cookie，使用内存中已更新的Cookie")
            else:
                try:
                    account_info = await self._load_account_info()
                    if account_info and account_info.get('cookie_value'):
                        new_cookies_str = account_info.get('cookie_value')
                        if new_cookies_str != self.cookies_str:
                            logger.info(f"【{self.cookie_id}】检测到数据库中的cookie已更新，重新加载cookie")
                            self.cookies_str = new_cookies_str
                            self.cookies = trans_cookies(self.cookies_str)
                            logger.warning(f"【{self.cookie_id}】Cookie已从数据库重新加载")
                except Exception as reload_e:
                    logger.warning(f"【{self.cookie_id}】从数据库重新加载cookie失败，继续使用当前cookie: {self._safe_str(reload_e)}")

            logger.info(f"【{self.cookie_id}】发起Token刷新API请求")
            api_result = await request_im_token(self.cookies_str, self.device_id)
            logger.info(
                f"【{self.cookie_id}】Token刷新API响应: "
                f"状态码={api_result.status_code}, 耗时={api_result.duration_seconds:.2f}秒"
            )
            res_json = api_result.response_json
            logger.info(f"【{self.cookie_id}】Token刷新响应: {json.dumps(res_json, ensure_ascii=False)[:500]}")

            # 检查并更新Cookie
            new_cookies = api_result.response_cookies
            if new_cookies:
                self.cookies.update(new_cookies)
                self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                await self.update_config_cookies()
                logger.warning("已更新Cookie到数据库")

            new_token = extract_im_access_token(res_json)
            if new_token:
                self.current_token = new_token
                self.parent._using_expired_startup_token = False
                self.last_token_refresh_time = time.time()
                self.parent.last_message_received_time = 0
                logger.warning(f"【{self.cookie_id}】Token刷新成功，已重置消息接收时间标识")
                logger.info(f"【{self.cookie_id}】Token刷新成功，新Token: {new_token}")
                self.last_token_refresh_status = "success"
                # 缓存token和device_id到数据库
                await self._set_cached_token(new_token, self.device_id)
                return new_token

            # 检查是否需要滑块验证
            if self.need_captcha_verification(res_json):
                logger.warning(f"【{self.cookie_id}】检测到需要滑块验证，开始处理...")

                try:
                    captcha_start_time = time.time()
                    new_cookies_str = await self.handle_captcha_verification(res_json)
                    captcha_duration = time.time() - captcha_start_time

                    if self.last_token_refresh_status in (
                        "skipped_risk_control_processing",
                        "skipped_risk_control_check_failed",
                    ):
                        return self.current_token
                    if self.last_token_refresh_status == "failed_risk_log_create":
                        notification_sent = True
                        return None

                    if new_cookies_str:
                        logger.info(f"【{self.cookie_id}】滑块验证成功，准备重新刷新token...")
                        # 滑块验证成功后，清除旧缓存并重新获取token
                        await self._delete_cached_token()
                        return await self.refresh_token(captcha_retry_count=captcha_retry_count + 1)
                    logger.error(f"【{self.cookie_id}】滑块验证失败")
                    notification_sent = True
                    self.last_token_refresh_status = "failed_captcha"
                    self.current_token = None
                    await self._delete_cached_token()
                    return None
                except Exception as captcha_e:
                    logger.error(f"【{self.cookie_id}】滑块验证处理异常: {self._safe_str(captcha_e)}")
                    notification_sent = True
                    self.last_token_refresh_status = "failed_captcha_exception"
                    self.current_token = None
                    await self._delete_cached_token()
                    return None

            # 检查是否包含"Session过期"（仅Session过期触发密码登录，令牌过期不触发）
            if isinstance(res_json, dict):
                res_json_str = json.dumps(res_json, ensure_ascii=False, separators=(',', ':'))
                if 'Session过期' in res_json_str:
                    refresh_result = await self.try_password_login_refresh("Session过期")

                    if refresh_result == "no_credentials":
                        # 未配置密码，禁用账号
                        logger.debug(f"【{self.cookie_id}】Session过期且未配置密码，立即禁用账号")

                        # 自动禁用账号
                        try:
                            from common.db.compat import db_manager
                            db_manager.disable_account(self.cookie_id, reason="账号已掉线且未配置账号密码，自动禁用")
                            logger.warning(f"【{self.cookie_id}】账号已自动禁用")
                        except Exception as disable_e:
                            logger.error(f"【{self.cookie_id}】自动禁用账号失败: {self._safe_str(disable_e)}")

                        notification_sent = True
                        return None
                    if refresh_result is True:
                        # 刷新成功，清除旧缓存并重新获取token
                        await self._delete_cached_token()
                        return await self.refresh_token(captcha_retry_count + 1)
                    if refresh_result == "skipped_cooldown":
                        # 密码登录冷却期内跳过：包括「上次登录冷却 300 秒内」与「账密错误
                        # 冷却 5 小时内」两种确定性可恢复状态。账号本身一切正常，只是
                        # 当下不能立即用密码登录刷新 cookie，应等待冷却结束 / 用户修正
                        # 账密。标记为 skipped_cooldown（main 循环 non_counted_statuses
                        # 已包含此状态，不计入 _token_fetch_failures，避免被自动禁用）。
                        self.last_token_refresh_status = "skipped_cooldown"
                        self.current_token = None
                        await self._delete_cached_token()
                        return None

                    # 刷新失败（密码登录真实失败：账号信息缺失等）
                    notification_sent = True
                    self.last_token_refresh_status = "failed_session_expired"
                    self.current_token = None
                    await self._delete_cached_token()
                    return None

            # FAIL_SYS_TOKEN_EXOIRED/EXPIRED：允许自动重试一次
            try:
                if isinstance(res_json, dict) and token_expiry_retry_count < 1:
                    ret_value = res_json.get('ret', []) or []
                    ret_str = json.dumps(ret_value, ensure_ascii=False)
                    if 'FAIL_SYS_TOKEN_EXOIRED' in ret_str or 'FAIL_SYS_TOKEN_EXPIRED' in ret_str:
                        logger.warning(f"【{self.cookie_id}】检测到令牌过期，准备重试一次: {ret_value}")
                        await asyncio.sleep(0.5)
                        return await self.refresh_token(
                            captcha_retry_count=captcha_retry_count,
                            token_expiry_retry_count=token_expiry_retry_count + 1,
                        )
            except Exception as retry_e:
                logger.warning(f"【{self.cookie_id}】令牌过期重试判断异常: {self._safe_str(retry_e)}")

            logger.error(f"【{self.cookie_id}】Token刷新失败: {res_json}")
            self.current_token = None
            self.last_token_refresh_status = "failed_api"
            await self._delete_cached_token()

            if not notification_sent:
                await self.send_token_refresh_notification(f"Token刷新失败: {res_json}", "token_refresh_failed")
            return None

        except asyncio.TimeoutError:
            logger.error(f"【{self.cookie_id}】Token刷新API请求超时（30秒）")
            self.current_token = None
            self.last_token_refresh_status = "failed_timeout"
            # 超时属于网络问题，不代表 token 失效，保留数据库缓存 token 供下次重试，避免误删后被迫走滑块
            return None
        except aiohttp.ClientError as e:
            logger.error(f"【{self.cookie_id}】Token刷新网络错误: {type(e).__name__}: {e}")
            self.current_token = None
            self.last_token_refresh_status = "failed_network"
            # 网络错误同样不删数据库缓存 token，保留供下次重试
            return None
        except Exception as e:
            logger.error(f"【{self.cookie_id}】Token刷新异常: {type(e).__name__}: {self._safe_str(e)}")
            self.current_token = None
            self.last_token_refresh_status = "failed_exception"
            await self._delete_cached_token()

            if not notification_sent:
                await self.send_token_refresh_notification(f"Token刷新异常: {str(e)}", "token_refresh_exception")
            return None

    # ==================== 密码登录刷新 ====================

    async def try_password_login_refresh(self, trigger_reason: str = "令牌/Session过期"):
        """尝试通过密码登录刷新Cookie并重启实例

        每次调用都会写入一条账号登录日志（xy_account_login_logs），便于在
        「日志管理 / 账号登录日志」中复盘登录尝试结果与失败原因。
        """
        logger.warning(f"【{self.cookie_id}】检测到{trigger_reason}，准备刷新Cookie并重启实例...")

        # 记录账号登录日志的辅助变量与函数：在每个出口前调用一次，统一计算耗时
        start_ts = time.time()
        # username 在 account_info 加载后才会被赋值；闭包内只读取，赋值由外层完成
        login_username: str | None = None
        # 接口续期失败原因（在接口续期失败后赋值，供后续日志拼接）
        _api_renew_fail_msg: str = ""

        def _record_login_log(
            login_status: str,
            failure_reason: str | None = None,
            error_message: str | None = None,
            updated_cookie_names: str | None = None,
        ) -> None:
            """记录一条账号登录日志（写日志失败不影响主流程）。"""
            try:
                from common.db.compat import db_manager
                duration_ms = int((time.time() - start_ts) * 1000)
                # 如果接口续期失败了，在 error_message 前拼接续期失败信息
                final_error_message = error_message
                if _api_renew_fail_msg and error_message:
                    final_error_message = f"{_api_renew_fail_msg}，{error_message}"
                db_manager.add_account_login_log(
                    cookie_id=self.cookie_id,
                    login_status=login_status,
                    username=login_username,
                    trigger_reason=trigger_reason,
                    failure_reason=failure_reason,
                    error_message=final_error_message,
                    updated_cookie_names=updated_cookie_names,
                    duration_ms=duration_ms,
                )
            except Exception as log_e:
                logger.warning(f"【{self.cookie_id}】写入账号登录日志失败: {self._safe_str(log_e)}")

        try:
            from common.db.compat import db_manager
            
            # 检查密码登录冷却期
            current_time = time.time()
            last_password_login = self.parent._last_password_login_time.get(self.cookie_id, 0) if hasattr(self.parent, '_last_password_login_time') else 0
            password_login_cooldown = getattr(self.parent, '_password_login_cooldown', 300)
            time_since_last_login = current_time - last_password_login
            
            if last_password_login > 0 and time_since_last_login < password_login_cooldown:
                remaining_time = password_login_cooldown - time_since_last_login
                cooldown_msg = (
                    f"距离上次密码登录仅 {time_since_last_login:.1f} 秒，"
                    f"仍在冷却期内（还需等待 {remaining_time:.1f} 秒），跳过密码登录"
                )
                logger.warning(f"【{self.cookie_id}】{cooldown_msg}")
                _record_login_log("skipped_cooldown", "login_cooldown", cooldown_msg)
                # 返回 "skipped_cooldown" 而非 False，以便上层 refresh_token 把 status 标记为
                # 不计入禁用计数的 "skipped_cooldown"（避免 main 循环每 5 秒一次地累加
                # _token_fetch_failures，1 分钟内达到 10 次后误把账号自动禁用）。
                return "skipped_cooldown"
            
            # 检查账密错误冷却期（5小时）
            password_error_time = self.parent._password_error_cooldown_time.get(self.cookie_id, 0) if hasattr(self.parent, '_password_error_cooldown_time') else 0
            password_error_cooldown = getattr(self.parent, '_password_error_cooldown', 5 * 60 * 60)
            time_since_error = current_time - password_error_time
            
            if password_error_time > 0 and time_since_error < password_error_cooldown:
                remaining_hours = (password_error_cooldown - time_since_error) / 3600
                cooldown_msg = f"账密错误冷却期内（还需等待 {remaining_hours:.1f} 小时），跳过密码登录"
                logger.warning(f"【{self.cookie_id}】{cooldown_msg}")
                _record_login_log("skipped_cooldown", "password_error_cooldown", cooldown_msg)
                # 同上：账密错误已经在第一次发生时立即禁用了账号。当用户手动启用账号后，
                # cookie 仍然 Session 过期；冷却期内跳过密码登录是确定性的可恢复状态
                # （等待用户修正账密 / 等冷却结束），不应该被算作「真实故障」累加禁用计数。
                return "skipped_cooldown"

            logger.info(f"【{self.cookie_id}】{trigger_reason}触发Cookie刷新和实例重启")

            # ====== 优先尝试接口续期（轻量级，无需浏览器） ======
            try:
                from common.services.cookie_renew_api_service import cookie_renew_api_service
                logger.info(f"【{self.cookie_id}】先尝试接口续期（silentHasLogin + setLoginSettings）...")
                # 记录续期前的全量cookies
                logger.info(f"【{self.cookie_id}】[续期前全量Cookies] {self.cookies_str}")
                renew_result = await cookie_renew_api_service.renew(self.cookies_str, self.cookie_id)

                # 不管续期是否成功，只要有Cookie字段更新就先写入数据库
                if renew_result.updated_cookie_names:
                    self.cookies_str = renew_result.new_cookies_str
                    self.cookies = trans_cookies(self.cookies_str)
                    await self.update_config_cookies()
                    logger.info(
                        f"【{self.cookie_id}】接口返回Cookie已更新 "
                        f"{len(renew_result.updated_cookie_names)} 个字段："
                        f"{', '.join(renew_result.updated_cookie_names)}"
                    )

                # 记录续期后的全量cookies（不管成功失败都打印）
                logger.info(f"【{self.cookie_id}】[续期后全量Cookies] {self.cookies_str}")

                if renew_result.success:
                    # 续期成功（可能是接口续期或浏览器续期），跳过密码登录
                    renew_method_desc = "接口续期" if renew_result.renew_method == "api" else "浏览器续期"
                    logger.info(
                        f"【{self.cookie_id}】{renew_method_desc}成功，跳过密码登录"
                    )
                    log_reason = f"api_renew_success" if renew_result.renew_method == "api" else "browser_renew_success"
                    _record_login_log(
                        "success",
                        log_reason,
                        f"{renew_method_desc}成功，更新了 {len(renew_result.updated_cookie_names)} 个字段："
                        f"{', '.join(renew_result.updated_cookie_names)}，无需密码登录"
                        if renew_result.updated_cookie_names
                        else f"{renew_method_desc}成功，Cookie无变化，无需密码登录",
                        updated_cookie_names=",".join(renew_result.updated_cookie_names) if renew_result.updated_cookie_names else None,
                    )
                    return True
                else:
                    logger.info(
                        f"【{self.cookie_id}】续期未成功"
                        f"（{renew_result.api_message}），"
                        f"继续尝试密码登录..."
                    )
            except Exception as renew_exc:
                logger.warning(
                    f"【{self.cookie_id}】续期异常（不影响后续密码登录）: {self._safe_str(renew_exc)}"
                )

            # ====== 续期未成功，继续原有密码登录流程 ======
            # 标记续期失败原因（闭包变量，_record_login_log 会自动拼接）
            _api_renew_fail_msg = "接口续期和浏览器续期均失败"

            account_info = await self._load_account_info()
            
            if not account_info:
                err_msg = "无法获取账号信息"
                logger.error(f"【{self.cookie_id}】{err_msg}")
                _record_login_log("failed", "account_info_missing", err_msg)
                return False

            # 拿到 username 后赋给闭包变量，确保后续每条日志都带上账号快照
            login_username = (account_info.get('username') or '') or None
            
            # 检查数据库中的cookie是否已经更新
            db_cookie_value = account_info.get('cookie_value', '')
            if db_cookie_value and db_cookie_value != self.cookies_str:
                logger.info(f"【{self.cookie_id}】检测到数据库中的cookie已更新，重新加载cookie")
                self.cookies_str = db_cookie_value
                self.cookies = trans_cookies(self.cookies_str)
                logger.info(f"【{self.cookie_id}】Cookie已从数据库重新加载，跳过密码登录刷新")
                _record_login_log(
                    "success",
                    "cookie_already_updated_externally",
                    "数据库中的Cookie已被外部更新，直接复用，无需密码登录",
                )
                return True
            
            username = account_info.get('username', '')
            password = account_info.get('password', '')
            show_browser = account_info.get('show_browser', False)
            
            if not username or not password:
                err_msg = "未配置用户名或密码，无法自动刷新Cookie"
                logger.warning(f"【{self.cookie_id}】{err_msg}")
                await self.send_token_refresh_notification(
                    f"检测到{trigger_reason}，但未配置用户名或密码，无法自动刷新Cookie",
                    "no_credentials"
                )
                _record_login_log("no_credentials", "no_credentials", err_msg)
                return "no_credentials"  # 返回特殊值表示未配置密码，不触发重启
            
            # 使用 Playwright 登录
            from app.services.captcha.xianyu_slider_stealth import XianyuSliderStealth
            browser_mode = "有头" if show_browser else "无头"
            logger.info(f"【{self.cookie_id}】开始使用{browser_mode}浏览器进行密码登录刷新Cookie...")
            logger.info(f"【{self.cookie_id}】使用账号: {username}")
            
            # 在进入线程前捕获事件循环
            main_loop = asyncio.get_running_loop()
            
            # 同步回调函数（在工作线程中调用）
            def notification_callback_sync(message: str, screenshot_path: str = None, verification_url: str = None):
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.send_token_refresh_notification(
                            error_message=message,
                            notification_type="token_refresh",
                            chat_id=None,
                            attachment_path=screenshot_path,
                            verification_url=verification_url
                        ),
                        main_loop
                    )
                    future.result(timeout=10)  # 等待最多10秒
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】发送通知失败: {e}")
            
            # 把构造函数和登录都放到线程中，避免阻塞事件循环
            def _do_password_login():
                slider = XianyuSliderStealth(user_id=self.cookie_id, enable_learning=False, headless=not show_browser)
                try:
                    return slider.login_with_password_playwright(
                        account=username,
                        password=password,
                        show_browser=show_browser,
                        notification_callback=notification_callback_sync
                    )
                finally:
                    try:
                        slider.close()
                    except Exception:
                        pass
            
            # 密码登录同样驱动浏览器，必须走浏览器任务专用线程池，避免占用默认线程池
            result = await run_browser_task(_do_password_login)
            
            if result:
                logger.info(f"【{self.cookie_id}】密码登录成功，获取到Cookie")
                
                # 密码登录成功，清除旧的Token缓存（新Cookie需要重新获取Token）
                await self._delete_cached_token()
                
                new_cookies_str = '; '.join([f"{k}={v}" for k, v in result.items()])
                # 记录密码登录获取到的新cookies
                logger.info(f"【{self.cookie_id}】[密码登录获取的新Cookies] {new_cookies_str}")
                
                # 记录密码登录时间
                if hasattr(self.parent, '_last_password_login_time'):
                    self.parent._last_password_login_time[self.cookie_id] = time.time()
                logger.warning(f"【{self.cookie_id}】已记录密码登录时间，冷却期 {password_login_cooldown} 秒")
                
                try:
                    await self.send_token_refresh_notification(
                        f"账号密码登录成功，Cookie已获取，准备更新并重启",
                        "password_login_success"
                    )
                except Exception as notify_e:
                    logger.warning(f"【{self.cookie_id}】发送通知失败: {self._safe_str(notify_e)}")
                
                update_success = await self.update_cookies_and_restart(new_cookies_str)
                
                if update_success:
                    logger.info(f"【{self.cookie_id}】Cookie更新并重启任务成功")
                    _record_login_log("success", None, "密码登录成功，Cookie已更新且实例已重启")
                    return True
                else:
                    err_msg = "Cookie更新或实例重启失败（密码登录已成功）"
                    logger.error(f"【{self.cookie_id}】{err_msg}")
                    _record_login_log("failed", "cookie_update_failed", err_msg)
                    return False
                    
            else:
                err_msg = "密码登录失败，未获取到Cookie"
                logger.warning(f"【{self.cookie_id}】{err_msg}")
                _record_login_log("failed", "login_no_cookie_returned", err_msg)
                return False

        except Exception as refresh_e:
            # ============== baxia-punish 风控图形滑块特殊处理 ==============
            # 该异常表示账号本身正常，仅是闲鱼风控系统识别出可疑行为弹了图形验证（如"找两个松鼠"），
            # 处理策略：不禁用账号、设置 5 小时冷却避免反复触发风控、发送特定通知。
            # 必须通过 isinstance 单独识别，避免被下面的"账密错误"分支误判为禁用场景。
            try:
                from common.services.captcha.xianyu_slider_stealth import BaxiaPunishCaptchaException
                _is_baxia_punish = isinstance(refresh_e, BaxiaPunishCaptchaException)
            except Exception:
                _is_baxia_punish = False
            
            if _is_baxia_punish:
                punish_msg = self._safe_str(refresh_e)
                logger.warning(
                    f"【{self.cookie_id}】检测到 baxia-punish 风控图形滑块验证："
                    f"{punish_msg}；账号本身正常，仅设置冷却期，不禁用账号"
                )
                # 设置 5 小时冷却（与账密错误共用同一冷却字段）
                if hasattr(self.parent, '_password_error_cooldown_time'):
                    self.parent._password_error_cooldown_time[self.cookie_id] = time.time()
                    cooldown_hours = getattr(self.parent, '_password_error_cooldown', 5 * 60 * 60) / 3600
                    logger.warning(
                        f"【{self.cookie_id}】已设置 {cooldown_hours:.0f} 小时冷却期，期间不再尝试自动登录"
                    )
                # 发送通知
                try:
                    await self.send_token_refresh_notification(
                        (
                            f"账号在密码登录过程中触发了闲鱼风控图形验证（如\"找两个松鼠\"等图形识别滑块），"
                            f"系统无法自动通过此类验证。\n"
                            f"账号本身正常，已暂停 5 小时后再尝试自动登录。\n"
                            f"如急需登录，请手动登录账号或稍后再试。\n\n"
                            f"提示：{punish_msg}"
                        ),
                        "baxia_punish_captcha"
                    )
                except Exception as notify_e:
                    logger.warning(
                        f"【{self.cookie_id}】发送风控验证通知失败: {self._safe_str(notify_e)}"
                    )
                _record_login_log("failed", "baxia_punish_captcha", punish_msg)
                return False
            # ============== baxia-punish 处理结束 ==============
            
            error_msg = self._safe_str(refresh_e)
            logger.error(f"【{self.cookie_id}】Cookie刷新或实例重启失败: {error_msg}")

            # 检测账密错误，禁用账号并设置冷却期
            # 关键字命中只决定是否设置 5 小时冷却（避免被风控），其他类型错误（如冻结）不需要冷却
            is_bad_credentials = (
                '账密错误' in error_msg
                or '账号密码错误' in error_msg
                or '用户名或密码错误' in error_msg
            )
            if is_bad_credentials:
                # 直接使用原始错误文案作为禁用原因（不加前缀），与内层 _disable_account_on_timeout 保持一致
                disable_reason = error_msg if error_msg else "账号密码错误"
                try:
                    from common.db.compat import db_manager
                    db_manager.disable_account(self.cookie_id, reason=disable_reason)
                    logger.warning(f"【{self.cookie_id}】检测到账密错误，账号已自动禁用，原因: {disable_reason}")
                except Exception as disable_e:
                    logger.error(f"【{self.cookie_id}】禁用账号失败: {self._safe_str(disable_e)}")
                
                # 设置冷却期
                if hasattr(self.parent, '_password_error_cooldown_time'):
                    self.parent._password_error_cooldown_time[self.cookie_id] = time.time()
                    cooldown_hours = getattr(self.parent, '_password_error_cooldown', 5 * 60 * 60) / 3600
                    logger.warning(f"【{self.cookie_id}】已设置 {cooldown_hours:.0f} 小时冷却期，期间不再尝试自动登录")
                
                try:
                    await self.send_token_refresh_notification(
                        (
                            f"账号密码登录失败，账号已自动禁用，请检查账号密码是否正确后重新启用。\n"
                            f"失败原因: {error_msg or '未知错误'}"
                        ),
                        "password_error"
                    )
                except Exception as notify_e:
                    logger.warning(f"【{self.cookie_id}】发送账密错误通知失败: {self._safe_str(notify_e)}")
            
            # 异常分支统一记录登录日志：区分账密错误 / 其他异常
            _record_login_log(
                "failed",
                "bad_credentials" if is_bad_credentials else "exception",
                error_msg or repr(refresh_e),
            )
            return False

    # ==================== Cookie有效性验证 ====================

    async def verify_cookie_validity(self) -> dict:
        """验证Cookie的有效性，通过实际调用API测试"""
        logger.info(f"【{self.cookie_id}】开始验证Cookie有效性（使用真实API调用）...")
        
        result = {
            'valid': True,
            'confirm_api': None,
            'image_api': None,
            'details': []
        }
        
        try:
            logger.info(f"【{self.cookie_id}】测试图片上传API...")
            
            import tempfile
            import os
            from PIL import Image
            
            temp_dir = tempfile.gettempdir()
            test_image_path = os.path.join(temp_dir, f'cookie_test_{self.cookie_id}.png')
            
            try:
                img = Image.new('RGB', (1, 1), color='white')
                img.save(test_image_path, 'PNG')
                logger.info(f"【{self.cookie_id}】已创建测试图片: {test_image_path}")
                
                from common.utils.image_uploader import ImageUploader
                uploader = ImageUploader(cookies_str=self.cookies_str)
                
                await uploader.create_session()
                
                try:
                    upload_result = await uploader.upload_image(test_image_path)
                finally:
                    await uploader.close_session()
                
                if upload_result:
                    logger.info(f"【{self.cookie_id}】✅ 图片上传API验证通过")
                    result['image_api'] = True
                    result['details'].append("图片上传API: 通过验证")
                else:
                    logger.warning(f"【{self.cookie_id}】❌ 图片上传API验证失败")
                    result['image_api'] = False
                    result['valid'] = False
                    result['details'].append("图片上传API: 上传失败，可能Cookie已失效")
                
            finally:
                if os.path.exists(test_image_path):
                    try:
                        os.remove(test_image_path)
                        logger.info(f"【{self.cookie_id}】已清理测试图片")
                    except Exception:
                        pass
                        
        except Exception as e:
            logger.error(f"【{self.cookie_id}】图片上传API验证异常: {self._safe_str(e)}")
            result['image_api'] = True
            result['details'].append(f"图片上传API: 调用异常(可能非Cookie问题)")
        
        result['details'] = '; '.join(result['details'])
        logger.info(f"【{self.cookie_id}】Cookie有效性验证完成: {result}")
        return result

