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
from loguru import logger

from common.db.session import async_session_maker
from common.utils.cookie_refresh import get_account_by_identity, update_account_cookies_in_db
from common.utils.xianyu_utils import trans_cookies, generate_sign
from common.utils.time_utils import get_beijing_now_naive


class CookieTokenManager:
    """Cookie/Token管理器"""
    
    def __init__(self, parent):
        """
        初始化Cookie/Token管理器
        
        Args:
            parent: XianyuLive实例，用于访问共享资源
        """
        self.parent = parent
    
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

    async def _get_cached_token(self) -> dict | None:
        """从数据库获取缓存的token和device_id
        
        查询 xy_token_cache 表，如果存在未过期的记录则返回
        
        Returns:
            包含token和device_id的字典，不存在或已过期则返回None
        """
        try:
            from sqlalchemy import text
            
            async with async_session_maker() as session:
                result = await session.execute(
                    text("""
                        SELECT token, device_id, expire_at 
                        FROM xy_token_cache 
                        WHERE user_id = :user_id 
                        LIMIT 1
                    """),
                    {"user_id": self.myid}
                )
                row = result.fetchone()
                
                if row:
                    token_val, device_id_val, expire_at = row
                    now = get_beijing_now_naive()
                    # 检查是否过期
                    if expire_at and expire_at > now:
                        remaining = expire_at - now
                        remaining_hours = int(remaining.total_seconds() // 3600)
                        remaining_minutes = int((remaining.total_seconds() % 3600) // 60)
                        logger.info(f"【{self.cookie_id}】Token缓存命中: user_id={self.myid}, 剩余有效时间={remaining_hours}小时{remaining_minutes}分钟")
                        return {'token': token_val, 'device_id': device_id_val}
                    else:
                        logger.info(f"【{self.cookie_id}】Token缓存已过期: user_id={self.myid}, 过期时间={expire_at}")
                        # 过期了则删除
                        await self._delete_cached_token()
                else:
                    logger.info(f"【{self.cookie_id}】Token缓存未命中: user_id={self.myid}")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】获取Token缓存失败: {e}")
        return None

    async def _set_cached_token(self, token: str, device_id: str):
        """将token和device_id缓存到数据库
        
        使用 INSERT ... ON DUPLICATE KEY UPDATE 实现插入或更新
        过期时间为当前时间 + 8~10小时随机
        
        Args:
            token: IM Token
            device_id: 设备ID
        """
        try:
            from datetime import timedelta
            from sqlalchemy import text
            
            # 8-10小时随机过期时间
            ttl_hours = random.uniform(8, 10)
            expire_at = get_beijing_now_naive() + timedelta(hours=ttl_hours)
            
            async with async_session_maker() as session:
                await session.execute(
                    text("""
                        INSERT INTO xy_token_cache (user_id, token, device_id, expire_at, created_at, updated_at)
                        VALUES (:user_id, :token, :device_id, :expire_at, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE 
                            token = VALUES(token),
                            device_id = VALUES(device_id),
                            expire_at = VALUES(expire_at),
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
                logger.info(f"【{self.cookie_id}】Token已缓存到数据库 (过期时间={expire_at.strftime('%Y-%m-%d %H:%M:%S')}, TTL={ttl_hours:.1f}小时)")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】缓存Token到数据库失败: {e}")

    async def _delete_cached_token(self):
        """删除数据库中缓存的token"""
        try:
            from common.db.session import async_session_maker
            from sqlalchemy import text
            
            async with async_session_maker() as session:
                await session.execute(
                    text("DELETE FROM xy_token_cache WHERE user_id = :user_id"),
                    {"user_id": self.myid}
                )
                await session.commit()
                logger.info(f"【{self.cookie_id}】已清除Token缓存: user_id={self.myid}")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】清除Token缓存失败: {e}")

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
            if not isinstance(res_json, dict):
                return False

            # 记录res_json内容到日志
            res_json_str = json.dumps(res_json, ensure_ascii=False, separators=(',', ':'))
            logger.debug(f"【{self.cookie_id}】检查滑块验证响应: {res_json_str[:500]}")

            # 检查返回的错误信息
            ret_value = res_json.get('ret', [])
            if not ret_value:
                return False

            # 检查是否包含需要验证的关键词
            captcha_keywords = [
                'FAIL_SYS_USER_VALIDATE',  # 用户验证失败
                'RGV587_ERROR',            # 风控错误
                '哎哟喂,被挤爆啦',          # 被挤爆了
                '哎哟喂，被挤爆啦',         # 被挤爆了（中文逗号）
                '挤爆了',                  # 挤爆了
                '请稍后重试',              # 请稍后重试
                'punish?x5secdata',        # 惩罚页面
                'captcha',                 # 验证码
            ]

            error_msg = str(ret_value[0]) if ret_value else ''

            # 检查错误信息是否包含需要验证的关键词
            for keyword in captcha_keywords:
                if keyword in error_msg:
                    logger.info(f"【{self.cookie_id}】检测到需要滑块验证的关键词: {keyword}")
                    return True

            # 检查data字段中是否包含验证URL
            data = res_json.get('data', {})
            if isinstance(data, dict) and 'url' in data:
                url = data.get('url', '')
                if 'punish' in url or 'captcha' in url or 'validate' in url:
                    logger.info(f"【{self.cookie_id}】检测到验证URL: {url}")
                    return True

            return False

        except Exception as e:
            logger.error(f"【{self.cookie_id}】检查是否需要滑块验证时出错: {self._safe_str(e)}")
            return False


    # ==================== 滑块验证处理 ====================

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
            
            # 记录风控日志
            log_id = None
            captcha_start_time = time.time()
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

            try:
                from app.services.captcha.slider_stealth import run_slider_verification_with_fallback

                # 使用 asyncio.to_thread 在独立线程中运行同步的 Playwright 代码
                # 这样可以避免 greenlet 的线程切换问题
                # run_slider_verification_with_fallback: 主引擎(Playwright)失败后自动用 DrissionPage 兜底
                # 返回 (是否成功, cookies, 通过引擎: playwright/drissionpage/None)
                success, cookies, captcha_engine = await asyncio.to_thread(
                    run_slider_verification_with_fallback,
                    f"{self.cookie_id}",
                    verification_url,
                    True,   # enable_learning
                    False,  # headless（主引擎）
                    20,     # browser_timeout（主引擎）
                    self.cookies_str,  # existing_cookies_str，供 DrissionPage 兜底注入
                )

                if success and cookies:
                    logger.info(f"【{self.cookie_id}】滑块验证成功，获取到新的cookies")
                    # 打印滑块验证返回的全部cookies
                    logger.warning(f"【{self.cookie_id}】滑块验证返回的全部cookies: {cookies}")
                    
                    # 更新风控日志为成功状态
                    captcha_duration = time.time() - captcha_start_time
                    if log_id:
                        try:
                            from common.db.compat import db_manager
                            engine_label = '兜底引擎(DrissionPage)' if captcha_engine == 'drissionpage' else '主引擎(Playwright)'
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
                    logger.error(f"【{self.cookie_id}】滑块验证失败")
                    
                    # 更新风控日志为失败状态
                    captcha_duration = time.time() - captcha_start_time
                    if log_id:
                        try:
                            from common.db.compat import db_manager
                            db_manager.update_risk_control_log(
                                log_id=log_id,
                                processing_status='failed',
                                processing_result=f'滑块验证失败，耗时: {captcha_duration:.2f}秒'
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
            
            # 检查数据库Token缓存（仅首次调用时，滑块重试/令牌过期重试时跳过）
            if captcha_retry_count == 0 and token_expiry_retry_count == 0:
                cached = await self._get_cached_token()
                if cached:
                    cached_token = cached['token']
                    cached_device_id = cached['device_id']
                    # 恢复device_id，确保后续注册用同一个
                    self.parent.device_id = cached_device_id
                    self.current_token = cached_token
                    self.last_token_refresh_time = time.time()
                    self.last_token_refresh_status = "success_from_cache"
                    logger.info(f"【{self.cookie_id}】使用数据库缓存的Token和Device ID")
                    logger.info(f"【{self.cookie_id}】缓存Token: {cached_token}")
                    logger.info(f"【{self.cookie_id}】缓存Device ID: {cached_device_id}")
                    return cached_token
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

            # 生成时间戳
            timestamp = str(int(time.time() * 1000))

            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': '',
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idlemessage.pc.login.token',
                'sessionOption': 'AutoLoginOnly',
                'dangerouslySetWindvaneParams': '%5Bobject%20Object%5D',
                'smToken': 'token',
                'queryToken': 'sm',
                'sm': 'sm',
                'spm_cnt': 'a21ybx.im.0.0',
                'spm_pre': 'a21ybx.home.sidebar.1.4c053da6vYwnmf',
                'log_id': '4c053da6vYwnmf'
            }
            data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + self.device_id + '"}'
            data = {'data': data_val}

            # 获取token（使用已解析的self.cookies，避免重复解析）
            token = self.cookies.get('_m_h5_tk', '').split('_')[0] if self.cookies.get('_m_h5_tk') else ''
            sign = generate_sign(params['t'], token, data_val)
            params['sign'] = sign

            # 请求头
            headers = {
                'accept': 'application/json',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded',
                'pragma': 'no-cache',
                'priority': 'u=1, i',
                'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'referer': 'https://www.goofish.com/',
                'origin': 'https://www.goofish.com',
                'cookie': self.cookies_str.replace('\n', '').replace('\r', '') if self.cookies_str else ''
            }

            api_url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/'
            
            logger.info(f"【{self.cookie_id}】发起Token刷新API请求: {api_url}")
            request_start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    request_duration = time.time() - request_start_time
                    logger.info(f"【{self.cookie_id}】Token刷新API响应: 状态码={response.status}, 耗时={request_duration:.2f}秒")
                    res_json = await response.json()
                    logger.info(f"【{self.cookie_id}】Token刷新响应: {json.dumps(res_json, ensure_ascii=False)[:500]}")

                    # 检查并更新Cookie
                    if 'set-cookie' in response.headers:
                        new_cookies = {}
                        for cookie in response.headers.getall('set-cookie', []):
                            if '=' in cookie:
                                name, value = cookie.split(';')[0].split('=', 1)
                                new_cookies[name.strip()] = value.strip()

                        if new_cookies:
                            self.cookies.update(new_cookies)
                            self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                            await self.update_config_cookies()
                            logger.warning("已更新Cookie到数据库")

                    if isinstance(res_json, dict):
                        ret_value = res_json.get('ret', [])
                        if any('SUCCESS::调用成功' in ret for ret in ret_value):
                            if 'data' in res_json and 'accessToken' in res_json['data']:
                                new_token = res_json['data']['accessToken']
                                self.current_token = new_token
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

                            if new_cookies_str:
                                logger.info(f"【{self.cookie_id}】滑块验证成功，准备重新刷新token...")
                                # 滑块验证成功后，清除旧缓存并重新获取token
                                await self._delete_cached_token()
                                return await self.refresh_token(captcha_retry_count=captcha_retry_count + 1)
                            else:
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
                            elif refresh_result == True:
                                # 刷新成功，清除旧缓存并重新获取token
                                await self._delete_cached_token()
                                return await self.refresh_token(captcha_retry_count + 1)
                            elif refresh_result == "skipped_cooldown":
                                # 密码登录冷却期内跳过：包括「上次登录冷却 300 秒内」与「账密错误
                                # 冷却 5 小时内」两种确定性可恢复状态。账号本身一切正常，只是
                                # 当下不能立即用密码登录刷新 cookie，应等待冷却结束 / 用户修正
                                # 账密。标记为 skipped_cooldown（main 循环 non_counted_statuses
                                # 已包含此状态，不计入 _token_fetch_failures，避免被自动禁用）。
                                self.last_token_refresh_status = "skipped_cooldown"
                                self.current_token = None
                                await self._delete_cached_token()
                                return None
                            else:
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
            await self._delete_cached_token()
            return None
        except aiohttp.ClientError as e:
            logger.error(f"【{self.cookie_id}】Token刷新网络错误: {type(e).__name__}: {e}")
            self.current_token = None
            self.last_token_refresh_status = "failed_network"
            await self._delete_cached_token()
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
            
            result = await asyncio.to_thread(_do_password_login)
            
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

