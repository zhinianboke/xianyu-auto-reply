"""
密码登录路由 - WebSocket服务

功能：
1. 账号密码登录接口（异步）
2. 登录状态轮询
3. 人脸认证支持
4. 登录会话管理

参照旧框架 backend/app/api/routes/password_login.py 实现
"""
from __future__ import annotations

import asyncio
import secrets
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

router = APIRouter(prefix="/password-login", tags=["密码登录"])


# ==================== 请求/响应模型 ====================

class PasswordLoginRequest(BaseModel):
    """密码登录请求"""
    account_id: str
    account: str
    password: str
    show_browser: bool = False
    user_id: int  # 用户ID，由backend-web传入


class PasswordLoginResponse(BaseModel):
    """密码登录响应"""
    success: bool
    session_id: Optional[str] = None
    status: str = ""
    message: str = ""


class LoginStatusResponse(BaseModel):
    """登录状态响应"""
    status: str
    message: str = ""
    verification_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    qr_code_url: Optional[str] = None
    account_id: Optional[str] = None
    is_new_account: Optional[bool] = None
    cookie_count: Optional[int] = None
    error: Optional[str] = None


# ==================== 会话管理 ====================

# 密码登录会话存储
password_login_sessions: Dict[str, Dict[str, Any]] = {}

# 会话锁
password_login_locks: Dict[str, asyncio.Lock] = {}


def get_session_lock(session_id: str) -> asyncio.Lock:
    """获取会话锁"""
    if session_id not in password_login_locks:
        password_login_locks[session_id] = asyncio.Lock()
    return password_login_locks[session_id]


def cleanup_expired_sessions():
    """清理过期会话（超过1小时）"""
    current_time = time.time()
    expired = [
        sid for sid, session in password_login_sessions.items()
        if current_time - session.get("timestamp", 0) > 3600
    ]
    for sid in expired:
        if sid in password_login_sessions:
            del password_login_sessions[sid]
        if sid in password_login_locks:
            del password_login_locks[sid]


# ==================== 登录线程 ====================

def _run_password_login_sync(
    session_id: str,
    account_id: str,
    account: str,
    password: str,
    show_browser: bool,
    user_id: int
):
    """同步执行密码登录（在独立线程中运行）
    
    注意：Windows上需要设置正确的事件循环策略才能在子线程中使用Playwright
    """
    # 检查账号是否已禁用
    from app.services.captcha.concurrency import should_skip_account
    if should_skip_account(account_id):
        password_login_sessions[session_id]['status'] = 'failed'
        password_login_sessions[session_id]['error'] = '账号已禁用，请先在账号管理中启用'
        logger.warning(f"【{account_id}】账号已禁用，跳过密码登录")
        return
    
    # Windows上需要设置事件循环策略，否则Playwright无法启动subprocess
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    from app.services.captcha.xianyu_slider_stealth import XianyuSliderStealth
    from app.services.captcha.concurrency import concurrency_manager
    
    slider_instance = None
    try:
        logger.info(f"【{account_id}】开始执行账号密码登录")
        
        # 创建 XianyuSliderStealth 实例
        slider_instance = XianyuSliderStealth(
            user_id=account_id,
            enable_learning=True,
            headless=not show_browser
        )
        
        # 更新会话信息
        password_login_sessions[session_id]['slider_instance'] = slider_instance
        
        # 定义通知回调函数
        def notification_callback(
            message: str, 
            screenshot_path: str = None, 
            verification_url: str = None, 
            screenshot_path_new: str = None
        ):
            """人脸认证通知回调"""
            try:
                actual_screenshot_path = screenshot_path_new if screenshot_path_new else screenshot_path
                
                if actual_screenshot_path:
                    password_login_sessions[session_id]['status'] = 'verification_required'
                    password_login_sessions[session_id]['screenshot_path'] = actual_screenshot_path
                    password_login_sessions[session_id]['verification_url'] = None
                    password_login_sessions[session_id]['qr_code_url'] = None
                    logger.info(f"【{account_id}】人脸认证截图已保存: {actual_screenshot_path}")
                elif verification_url:
                    password_login_sessions[session_id]['status'] = 'verification_required'
                    password_login_sessions[session_id]['verification_url'] = verification_url
                    password_login_sessions[session_id]['screenshot_path'] = None
                    password_login_sessions[session_id]['qr_code_url'] = None
                    logger.info(f"【{account_id}】人脸认证验证链接已保存: {verification_url}")
                
                # 发送通知（在已有事件循环中调度异步任务）
                try:
                    from app.services.xianyu.notification_manager import NotificationManager
                    import asyncio
                    
                    async def send_notification():
                        try:
                            notification_manager = NotificationManager(account_id)
                            await notification_manager.send_token_refresh_notification(
                                error_message=message,
                                notification_type="password_login_verification",
                                attachment_path=actual_screenshot_path,
                                verification_url=verification_url
                            )
                            logger.info(f"【{account_id}】✅ 人脸验证通知已发送")
                        except Exception as notify_error:
                            logger.error(f"【{account_id}】发送人脸验证通知失败: {str(notify_error)}")
                    
                    # 获取当前事件循环并调度任务
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.run_coroutine_threadsafe(send_notification(), loop)
                    except RuntimeError:
                        # 如果没有运行中的事件循环，创建新的
                        asyncio.run(send_notification())
                        
                except Exception as notify_error:
                    logger.error(f"【{account_id}】发送人脸验证通知失败: {str(notify_error)}")
                    
            except Exception as e:
                logger.error(f"【{account_id}】处理人脸认证通知失败: {str(e)}")
        
        # 执行登录
        cookies_dict = slider_instance.login_with_password_playwright(
            account=account,
            password=password,
            show_browser=show_browser,
            notification_callback=notification_callback
        )
        
        if cookies_dict is None:
            password_login_sessions[session_id]['status'] = 'failed'
            password_login_sessions[session_id]['error'] = '登录失败，请检查账号密码是否正确'
            logger.error(f"【{account_id}】账号密码登录失败")
            return
        
        # 将cookie字典转换为字符串格式
        cookies_str = '; '.join([f"{k}={v}" for k, v in cookies_dict.items()])
        
        logger.info(f"【{account_id}】账号密码登录成功，获取到 {len(cookies_dict)} 个Cookie字段")
        
        # 保存到数据库
        _save_login_result(
            session_id=session_id,
            account_id=account_id,
            account=account,
            password=password,
            show_browser=show_browser,
            cookies_str=cookies_str,
            cookies_dict=cookies_dict,
            user_id=user_id
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # ============== baxia-punish 风控图形滑块特殊处理 ==============
        # 此类异常表示账号本身正常，仅是闲鱼风控弹了图形识别滑块（如"找两个松鼠"）。
        # 用户主动触发的密码登录也会遇到此情况：
        # - 不禁用账号
        # - 写入全局冷却（5 小时），与自动后台刷新共用同一冷却字典
        # - 在 session 中标注 reason，便于前端区分提示
        # 注意：保持 status='failed' 以兼容前端现有状态机
        try:
            from common.services.captcha.xianyu_slider_stealth import BaxiaPunishCaptchaException
            _is_baxia_punish = isinstance(e, BaxiaPunishCaptchaException)
        except Exception:
            _is_baxia_punish = False
        
        if _is_baxia_punish:
            logger.warning(
                f"【{account_id}】触发风控图形滑块验证，账号本身正常，"
                f"仅设置 5 小时冷却（不禁用账号）：{error_msg}"
            )
            try:
                from common.utils.cookie_refresh import _password_error_cooldown
                import time as _time
                _password_error_cooldown[account_id] = _time.time()
            except Exception as cooldown_e:
                logger.warning(f"【{account_id}】写入风控冷却失败: {cooldown_e}")
            
            password_login_sessions[session_id]['status'] = 'failed'
            password_login_sessions[session_id]['error'] = (
                "触发闲鱼风控图形验证（如\"找两个松鼠\"），账号正常但暂时无法自动登录，"
                "已暂停 5 小时。请稍后重试或手动登录。"
            )
            password_login_sessions[session_id]['reason'] = 'baxia_punish_captcha'
            password_login_sessions[session_id]['cooldown_hours'] = 5
        else:
            password_login_sessions[session_id]['status'] = 'failed'
            password_login_sessions[session_id]['error'] = error_msg
        # ============== baxia-punish 处理结束 ==============
        
        logger.error(f"【{account_id}】账号密码登录失败: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # 清理实例：调用 slider_instance.close() 统一释放
        # 浏览器进程 + Playwright 资源 + 账号级互斥锁 + 全局并发槽位
        # （之前仅调用 concurrency_manager.unregister_instance 会导致账号锁与浏览器进程泄漏）
        if slider_instance is not None:
            try:
                slider_instance.close()
                logger.debug(f"【{account_id}】XianyuSliderStealth 实例已清理")
            except Exception as cleanup_e:
                logger.warning(f"【{account_id}】清理实例时出错: {str(cleanup_e)}")
        else:
            # 实例从未创建（如构造函数前就异常），仅尝试释放全局槽位作为兜底
            try:
                concurrency_manager.unregister_instance(account_id)
            except Exception:
                pass

        # 清理密码登录处理状态
        try:
            from app.services.captcha.password_login_state import password_login_state
            password_login_state.finish_processing(account_id)
        except Exception as state_e:
            logger.warning(f"【{account_id}】清理密码登录状态时出错: {str(state_e)}")


def _start_password_login_thread(
    session_id: str,
    account_id: str,
    account: str,
    password: str,
    show_browser: bool,
    user_id: int
):
    """启动密码登录线程"""
    login_thread = threading.Thread(
        target=_run_password_login_sync,
        args=(session_id, account_id, account, password, show_browser, user_id),
        daemon=True
    )
    login_thread.start()
    logger.info(f"【{account_id}】密码登录线程已启动: {session_id}")


def _save_login_result(
    session_id: str,
    account_id: str,
    account: str,
    password: str,
    show_browser: bool,
    cookies_str: str,
    cookies_dict: dict,
    user_id: int
):
    """保存登录结果到数据库（同步方法，在线程中调用）"""
    from datetime import datetime, timedelta, timezone
    
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    
    from common.core.config import BaseConfig
    from common.models.xy_account import XYAccount
    from common.services.account_limit_service import AccountLimitExceededError, AccountLimitService
    from common.utils.cookie_refresh import clear_cookie_refresh_snapshot
    from common.utils.xianyu_utils import trans_cookies
    
    try:
        # 创建新的事件循环
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        try:
            async def _do_save(session_maker):
                async with session_maker() as session:
                    # 检查账号是否已存在（全局唯一：account_id 不区分 owner_id）
                    stmt = select(XYAccount).where(
                        XYAccount.account_id == account_id
                    )
                    result = await session.execute(stmt)
                    existing_account = result.scalars().first()

                    # 账号ID已被其他用户占用时，禁止覆盖，直接报错
                    if existing_account and existing_account.owner_id != user_id:
                        raise ValueError(f"账号ID {account_id} 已被其他用户占用，无法登录")
                    
                    # 从cookie中提取unb
                    parsed_cookies = trans_cookies(cookies_str)
                    unb = parsed_cookies.get('unb', '')
                    
                    # 获取当前时间（北京时间）
                    beijing_tz = timezone(timedelta(hours=8))
                    now = datetime.now(beijing_tz)
                    
                    if existing_account:
                        # 更新现有账号
                        existing_account.cookie = cookies_str
                        existing_account.metadata_json = clear_cookie_refresh_snapshot(existing_account.metadata_json)
                        existing_account.username = account
                        existing_account.login_password = password
                        existing_account.show_browser = show_browser
                        existing_account.login_method = 'password'
                        existing_account.status = 'active'
                        existing_account.disable_reason = None  # 清空禁用原因
                        existing_account.last_login_at = now
                        if unb:
                            existing_account.unb = unb
                        session.add(existing_account)
                        is_new_account = False
                        logger.info(f"【{account_id}】现有账号Cookie和账号密码已更新")
                    else:
                        # 创建新账号
                        await AccountLimitService(session).ensure_can_add_account(user_id)
                        new_account = XYAccount(
                            owner_id=user_id,
                            account_id=account_id,
                            cookie=cookies_str,
                            username=account,
                            login_password=password,
                            show_browser=show_browser,
                            login_method='password',
                            status='active',
                            auto_confirm=False,
                            pause_duration=10,
                            unb=unb,
                            last_login_at=now,
                        )
                        session.add(new_account)
                        is_new_account = True
                        logger.info(f"【{account_id}】新账号Cookie和账号密码已保存")
                    
                    # 密码登录成功，清除该账号的Token缓存（新Cookie需要重新获取Token）
                    if unb:
                        from sqlalchemy import text
                        await session.execute(
                            text("DELETE FROM xy_token_cache WHERE user_id = :user_id"),
                            {"user_id": unb}
                        )
                        logger.info(f"【{account_id}】密码登录成功，已清除Token缓存: user_id={unb}")
                    
                    await session.commit()
                    
                    return is_new_account
            
            async def save_to_db():
                # 一次性事件循环内的临时引擎：仅需极小连接池，并加连接超时；
                # 用 try/finally 确保引擎及其连接池始终被释放，避免每次密码登录泄漏连接。
                config = BaseConfig()
                engine = create_async_engine(
                    config.async_database_url,
                    echo=False,
                    pool_pre_ping=config.db_pool_pre_ping,
                    pool_size=1,
                    max_overflow=2,
                    pool_timeout=config.db_pool_timeout,
                    pool_recycle=config.db_pool_recycle,
                    connect_args={"connect_timeout": config.db_connect_timeout},
                )
                session_maker = async_sessionmaker(engine, expire_on_commit=False)
                try:
                    return await _do_save(session_maker)
                finally:
                    await engine.dispose()
            
            is_new_account = new_loop.run_until_complete(save_to_db())
            
            # 启动WebSocket连接任务
            try:
                from app.services.xianyu.cookie_manager import get_manager
                manager = get_manager()
                if manager:
                    if is_new_account:
                        manager.add_cookie(account_id, cookies_str, user_id)
                        logger.info(f"【{account_id}】新账号已添加到CookieManager并启动WebSocket")
                    else:
                        manager.update_cookie(account_id, cookies_str, user_id)
                        logger.info(f"【{account_id}】现有账号Cookie已更新并重启WebSocket")
                else:
                    logger.warning(f"【{account_id}】CookieManager未初始化，无法启动WebSocket")
            except Exception as ws_e:
                logger.error(f"【{account_id}】启动WebSocket任务失败: {str(ws_e)}")
            
            # 更新会话状态
            password_login_sessions[session_id]['status'] = 'success'
            password_login_sessions[session_id]['account_id'] = account_id
            password_login_sessions[session_id]['is_new_account'] = is_new_account
            password_login_sessions[session_id]['cookie_count'] = len(cookies_dict)
            
        finally:
            new_loop.close()
            
    except AccountLimitExceededError as e:
        logger.warning(f"【{account_id}】保存登录结果失败: {str(e)}")
        password_login_sessions[session_id]['status'] = 'failed'
        password_login_sessions[session_id]['error'] = str(e)
    except Exception as e:
        logger.error(f"【{account_id}】保存登录结果失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        password_login_sessions[session_id]['status'] = 'failed'
        password_login_sessions[session_id]['error'] = f'保存登录结果失败: {str(e)}'


# ==================== 路由 ====================

@router.post("", response_model=PasswordLoginResponse)
async def password_login(request: PasswordLoginRequest):
    """
    账号密码登录接口（异步，支持人脸认证）
    
    启动后台登录任务，返回session_id用于轮询状态
    """
    try:
        if not request.account_id or not request.account or not request.password:
            return PasswordLoginResponse(
                success=False,
                message="账号ID、登录账号和密码不能为空"
            )
        
        # 检查账号是否正在处理中，防止重复触发
        from app.services.captcha.password_login_state import password_login_state
        if not password_login_state.start_processing(request.account_id):
            # 账号正在处理中，直接返回成功（丢弃请求，不报错）
            logger.info(f"【{request.account_id}】账号正在处理密码登录，丢弃本次请求")
            return PasswordLoginResponse(
                success=True,
                status="processing",
                message="账号正在处理中，请稍候..."
            )
        
        logger.info(f"【{request.account_id}】开始账号密码登录")
        
        # 生成会话ID
        session_id = secrets.token_urlsafe(16)
        
        # 创建登录会话
        password_login_sessions[session_id] = {
            "account_id": request.account_id,
            "account": request.account,
            "password": request.password,
            "show_browser": request.show_browser,
            "status": "processing",
            "verification_url": None,
            "screenshot_path": None,
            "qr_code_url": None,
            "slider_instance": None,
            "task": None,
            "timestamp": time.time(),
            "user_id": request.user_id,
            "error": None,
        }
        
        # 启动后台登录线程
        _start_password_login_thread(
            session_id=session_id,
            account_id=request.account_id,
            account=request.account,
            password=request.password,
            show_browser=request.show_browser,
            user_id=request.user_id
        )
        
        logger.info(f"密码登录会话已创建: {session_id}")
        
        return PasswordLoginResponse(
            success=True,
            session_id=session_id,
            status="processing",
            message="登录任务已启动，请等待..."
        )
        
    except Exception as e:
        logger.error(f"账号密码登录异常: {e}")
        try:
            from app.services.captcha.password_login_state import password_login_state
            if request.account_id:
                password_login_state.finish_processing(request.account_id)
        except Exception:
            pass
        return PasswordLoginResponse(
            success=False,
            message=f"登录失败: {str(e)}"
        )


@router.get("/check/{session_id}", response_model=LoginStatusResponse)
async def check_login_status(session_id: str):
    """
    检查账号密码登录状态
    
    轮询此接口获取登录进度
    """
    try:
        cleanup_expired_sessions()
        
        if session_id not in password_login_sessions:
            return LoginStatusResponse(
                status="not_found",
                message="会话不存在或已过期"
            )
        
        session_data = password_login_sessions[session_id]
        status = session_data["status"]
        
        if status == "verification_required":
            return LoginStatusResponse(
                status="verification_required",
                verification_url=session_data.get("verification_url"),
                screenshot_path=session_data.get("screenshot_path"),
                qr_code_url=session_data.get("qr_code_url"),
                message="需要人脸验证，请查看验证截图" if session_data.get("screenshot_path") else "需要人脸验证，请点击验证链接"
            )
        elif status == "success":
            result = LoginStatusResponse(
                status="success",
                message=f"账号 {session_data['account_id']} 登录成功",
                account_id=session_data["account_id"],
                is_new_account=session_data.get("is_new_account", False),
                cookie_count=session_data.get("cookie_count", 0)
            )
            del password_login_sessions[session_id]
            return result
        elif status == "failed":
            error_msg = session_data.get("error", "登录失败")
            result = LoginStatusResponse(
                status="failed",
                message=error_msg,
                error=error_msg
            )
            del password_login_sessions[session_id]
            return result
        else:
            return LoginStatusResponse(
                status="processing",
                message="登录处理中，请稍候..."
            )
        
    except Exception as e:
        logger.error(f"检查登录状态异常: {e}")
        return LoginStatusResponse(
            status="error",
            message=str(e)
        )


@router.delete("/cancel/{session_id}")
async def cancel_login(session_id: str):
    """取消登录会话"""
    try:
        if session_id not in password_login_sessions:
            return {
                "success": False,
                "code": 404,
                "message": "会话不存在",
                "data": None
            }
        
        # 清理会话
        del password_login_sessions[session_id]
        if session_id in password_login_locks:
            del password_login_locks[session_id]
        
        logger.info(f"登录会话已取消: {session_id}")
        
        return {
            "success": True,
            "code": 200,
            "message": "登录会话已取消",
            "data": None
        }
        
    except Exception as e:
        logger.error(f"取消登录会话异常: {e}")
        return {
            "success": False,
            "code": 500,
            "message": str(e),
            "data": None
        }
