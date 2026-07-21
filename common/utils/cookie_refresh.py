"""
Cookie刷新工具模块

功能：
1. 检测闲鱼API返回的令牌过期错误（FAIL_SYS_TOKEN_EXOIRED）
2. 检测Session过期错误（FAIL_SYS_SESSION_EXPIRED）
3. 从响应头的Set-Cookie中提取新Cookie
4. 合并新旧Cookie
5. 更新数据库中的Cookie
6. Session过期时触发后台异步密码登录（不阻塞当前任务）

参照自动发货模块（BaseShippingService._handle_response_cookies）实现
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional, Tuple

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from common.utils.xianyu_utils import trans_cookies


COOKIE_REFRESH_SNAPSHOT_KEY = "cookies_refresh_snapshot"


def _normalize_json_like_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_json_like_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_json_like_value(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def normalize_browser_cookie_snapshot(cookies: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized_cookies: list[dict[str, Any]] = []
    for cookie in cookies or []:
        if not isinstance(cookie, dict):
            continue
        normalized_cookie = {
            str(key): _normalize_json_like_value(item)
            for key, item in cookie.items()
            if key is not None
        }
        name = str(normalized_cookie.get("name") or "").strip()
        if not name:
            continue
        normalized_cookie["name"] = name
        normalized_cookie["value"] = str(normalized_cookie.get("value") or "")
        normalized_cookie["domain"] = str(normalized_cookie.get("domain") or "")
        normalized_cookie["path"] = str(normalized_cookie.get("path") or "/")
        normalized_cookies.append(normalized_cookie)
    return sorted(
        normalized_cookies,
        key=lambda item: (
            str(item.get("domain") or ""),
            str(item.get("path") or "/"),
            str(item.get("name") or ""),
            str(item.get("value") or ""),
        ),
    )


def get_cookie_refresh_snapshot(metadata_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(metadata_json, dict):
        return []
    snapshot = metadata_json.get(COOKIE_REFRESH_SNAPSHOT_KEY)
    if not isinstance(snapshot, list):
        return []
    return normalize_browser_cookie_snapshot(snapshot)


def set_cookie_refresh_snapshot(
    metadata_json: dict[str, Any] | None,
    cookies: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    metadata = dict(metadata_json or {})
    metadata[COOKIE_REFRESH_SNAPSHOT_KEY] = normalize_browser_cookie_snapshot(cookies)
    return metadata


def clear_cookie_refresh_snapshot(metadata_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata_json, dict) or COOKIE_REFRESH_SNAPSHOT_KEY not in metadata_json:
        return metadata_json
    metadata = dict(metadata_json)
    metadata.pop(COOKIE_REFRESH_SNAPSHOT_KEY, None)
    return metadata or None


def build_playwright_cookie_payloads_from_snapshot(
    cookies: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for cookie in normalize_browser_cookie_snapshot(cookies):
        name = str(cookie.get("name") or "").strip()
        if not name:
            continue
        payload: dict[str, Any] = {
            "name": name,
            "value": str(cookie.get("value") or ""),
        }
        domain = str(cookie.get("domain") or "").strip()
        if domain:
            payload["domain"] = domain
            payload["path"] = str(cookie.get("path") or "/")
        else:
            continue
        expires = cookie.get("expires")
        if isinstance(expires, (int, float)) and expires > 0:
            payload["expires"] = expires
        http_only = cookie.get("httpOnly")
        if isinstance(http_only, bool):
            payload["httpOnly"] = http_only
        secure = cookie.get("secure")
        if isinstance(secure, bool):
            payload["secure"] = secure
        same_site = cookie.get("sameSite")
        if same_site:
            payload["sameSite"] = str(same_site)
        payloads.append(payload)
    return payloads


def build_cookie_string_from_browser_cookies(cookies: list[dict[str, Any]] | None) -> str:
    cookie_map: dict[str, str] = {}
    for cookie in normalize_browser_cookie_snapshot(cookies):
        name = str(cookie.get("name") or "").strip()
        if not name:
            continue
        cookie_map[name] = str(cookie.get("value") or "")
    return "; ".join(f"{name}={value}" for name, value in cookie_map.items())


def is_token_expired_error(ret_list: list) -> bool:
    """判断API返回是否为令牌过期/令牌为空错误

    令牌过期（FAIL_SYS_TOKEN_EXOIRED）与令牌为空（FAIL_SYS_TOKEN_EMPTY）
    在闲鱼接口中均会在响应头返回新的 Set-Cookie（含新的 _m_h5_tk），
    处理方式一致：提取新 Cookie 后刷新并重试，不需要重新登录。

    Args:
        ret_list: API响应中的ret列表

    Returns:
        True表示令牌过期或令牌为空
    """
    if not ret_list:
        return False
    ret_str = str(ret_list)
    return (
        'FAIL_SYS_TOKEN_EXOIRED' in ret_str
        or 'FAIL_SYS_TOKEN_EXPIRED' in ret_str
        or 'FAIL_SYS_TOKEN_EMPTY' in ret_str
        or '令牌过期' in ret_str
        or '令牌为空' in ret_str
    )


def is_session_expired_error(ret_list: list) -> bool:
    """判断API返回是否为Session过期错误
    
    Args:
        ret_list: API响应中的ret列表
        
    Returns:
        True表示Session过期
    """
    if not ret_list:
        return False
    ret_str = str(ret_list)
    return 'FAIL_SYS_SESSION_EXPIRED' in ret_str or 'Session过期' in ret_str


def extract_cookies_from_response(response: aiohttp.ClientResponse) -> Dict[str, str]:
    """从HTTP响应头中提取Set-Cookie

    Args:
        response: aiohttp响应对象

    Returns:
        提取到的Cookie字典（可能为空）
    """
    new_cookies = {}
    try:
        for cookie_header in response.headers.getall('set-cookie', []):
            if '=' in cookie_header:
                name_value = cookie_header.split(';')[0]
                name, value = name_value.split('=', 1)
                new_cookies[name.strip()] = value.strip()
    except Exception as e:
        logger.warning(f"提取Set-Cookie失败: {e}")
    return new_cookies


def merge_cookies(old_cookies_str: str, new_cookies: Dict[str, str]) -> str:
    """合并新旧Cookie

    Args:
        old_cookies_str: 原始Cookie字符串
        new_cookies: 从响应中提取的新Cookie字典

    Returns:
        合并后的Cookie字符串
    """
    merged = parse_cookie_string(old_cookies_str)
    merged.update(new_cookies)
    return '; '.join(f'{k}={v}' for k, v in merged.items())


def normalize_cookie_string(cookie_string: str) -> str:
    """规范化Cookie字符串，兼容分号后无空格的情况。"""
    return '; '.join(part.strip() for part in cookie_string.split(';') if part.strip())


def parse_cookie_string(cookie_string: str) -> Dict[str, str]:
    """将Cookie字符串解析为字典。"""
    normalized_cookie_string = normalize_cookie_string(cookie_string)
    if not normalized_cookie_string:
        return {}
    return trans_cookies(normalized_cookie_string)


async def get_account_by_identity(
    account_id: str,
    owner_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
) -> Optional[XYAccount]:
    async def _query(db_session: AsyncSession) -> Optional[XYAccount]:
        if owner_id is not None:
            owner_stmt = (
                select(XYAccount)
                .where(XYAccount.owner_id == owner_id, XYAccount.account_id == account_id)
                .order_by(XYAccount.id.desc())
                .limit(1)
            )
            owner_result = await db_session.execute(owner_stmt)
            owner_account = owner_result.scalars().first()
            if owner_account:
                return owner_account

        stmt = select(XYAccount).where(XYAccount.account_id == account_id).order_by(XYAccount.id.desc()).limit(2)
        result = await db_session.execute(stmt)
        accounts = result.scalars().all()
        if len(accounts) > 1:
            logger.warning(f"【{account_id}】检测到重复账号ID，已按最新记录处理Cookie数据库操作")
        return accounts[0] if accounts else None

    if session:
        return await _query(session)

    from common.db.session import async_session_maker

    async with async_session_maker() as db_session:
        return await _query(db_session)


async def update_account_cookies_in_db(
    account_id: str,
    new_cookies_str: str,
    owner_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
) -> bool:
    """更新数据库中账号的Cookie
    
    Args:
        account_id: 账号ID（account_id字段）
        new_cookies_str: 新的Cookie字符串
        owner_id: 所属用户ID，传入后优先按 owner_id + account_id 精确命中
        session: 可选的数据库会话，为None时自动创建
        
    Returns:
        是否更新成功
    """
    try:
        if session:
            account = await get_account_by_identity(account_id, owner_id=owner_id, session=session)
            if not account:
                logger.warning(f"【{account_id}】数据库中未找到账号，无法更新Cookie")
                return False
            account.cookie = new_cookies_str
            account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
            session.add(account)
            await session.commit()
        else:
            from common.db.session import async_session_maker
            async with async_session_maker() as db_session:
                account = await get_account_by_identity(account_id, owner_id=owner_id, session=db_session)
                if not account:
                    logger.warning(f"【{account_id}】数据库中未找到账号，无法更新Cookie")
                    return False
                account.cookie = new_cookies_str
                account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
                db_session.add(account)
                await db_session.commit()
        
        logger.info(f"【{account_id}】令牌过期后已更新Cookie到数据库")
        return True
    except Exception as e:
        logger.error(f"【{account_id}】更新Cookie到数据库失败: {e}")
        return False


def handle_token_expired_response(
    response: aiohttp.ClientResponse,
    old_cookies_str: str,
) -> Tuple[bool, str]:
    """处理令牌过期的响应：提取新Cookie并合并

    Args:
        response: HTTP响应对象
        old_cookies_str: 原始Cookie字符串

    Returns:
        (是否有新Cookie, 合并后的新Cookie字符串)
    """
    new_cookies = extract_cookies_from_response(response)
    if not new_cookies:
        logger.warning("令牌过期但响应中没有Set-Cookie，无法刷新")
        return False, old_cookies_str
    
    merged_str = merge_cookies(old_cookies_str, new_cookies)
    logger.info(f"令牌过期，已从Set-Cookie合并 {len(new_cookies)} 个Cookie字段")
    return True, merged_str


# ==================== Session过期账号冷却 ====================

# Session过期后，该账号所有定时任务冷却5分钟，避免重复请求已过期的Session
_session_expired_cooldown: Dict[str, float] = {}
_SESSION_EXPIRED_COOLDOWN_SECONDS = 300  # 5分钟冷却


def mark_account_session_expired(account_id: str) -> None:
    """标记账号Session已过期，进入冷却期
    
    Args:
        account_id: 账号ID
    """
    import time
    _session_expired_cooldown[account_id] = time.time()
    logger.warning(
        f"【{account_id}】Session过期，账号进入 "
        f"{_SESSION_EXPIRED_COOLDOWN_SECONDS // 60} 分钟冷却期"
    )


def is_account_session_cooled(account_id: str) -> bool:
    """检查账号是否处于Session过期冷却期内
    
    Args:
        account_id: 账号ID
        
    Returns:
        True表示仍在冷却期内，应跳过该账号
    """
    import time
    expired_time = _session_expired_cooldown.get(account_id, 0)
    if expired_time <= 0:
        return False
    
    elapsed = time.time() - expired_time
    if elapsed < _SESSION_EXPIRED_COOLDOWN_SECONDS:
        remaining = _SESSION_EXPIRED_COOLDOWN_SECONDS - elapsed
        logger.info(
            f"【{account_id}】账号处于Session过期冷却期内"
            f"（还需等待 {remaining:.0f} 秒），跳过"
        )
        return True
    
    # 冷却期已过，清除记录
    _session_expired_cooldown.pop(account_id, None)
    return False


# ==================== Session过期后台密码登录 ====================

# 密码登录冷却记录：防止短时间内重复触发
_password_login_cooldown: Dict[str, float] = {}
_PASSWORD_LOGIN_COOLDOWN_SECONDS = 300  # 5分钟冷却

# 账密错误冷却记录：防止反复尝试错误密码
_password_error_cooldown: Dict[str, float] = {}
_PASSWORD_ERROR_COOLDOWN_SECONDS = 5 * 60 * 60  # 5小时冷却


def trigger_password_login_async(account_id: str) -> None:
    """触发后台异步密码登录（不阻塞当前任务）
    
    检测到Session过期时调用，通过HTTP调用websocket服务的密码登录API，
    不关心登录结果，不重试当前任务。
    
    Args:
        account_id: 账号ID
    """
    import time
    current_time = time.time()
    
    # 检查密码登录冷却期
    last_login_time = _password_login_cooldown.get(account_id, 0)
    if last_login_time > 0 and (current_time - last_login_time) < _PASSWORD_LOGIN_COOLDOWN_SECONDS:
        remaining = _PASSWORD_LOGIN_COOLDOWN_SECONDS - (current_time - last_login_time)
        logger.warning(
            f"【{account_id}】Session过期触发密码登录，"
            f"但仍在冷却期内（还需等待 {remaining:.0f} 秒），跳过"
        )
        return
    
    # 检查账密错误冷却期
    error_time = _password_error_cooldown.get(account_id, 0)
    if error_time > 0 and (current_time - error_time) < _PASSWORD_ERROR_COOLDOWN_SECONDS:
        remaining_hours = (_PASSWORD_ERROR_COOLDOWN_SECONDS - (current_time - error_time)) / 3600
        logger.warning(
            f"【{account_id}】Session过期触发密码登录，"
            f"但处于账密错误冷却期（还需等待 {remaining_hours:.1f} 小时），跳过"
        )
        return
    
    # 记录触发时间
    _password_login_cooldown[account_id] = current_time
    
    logger.info(f"【{account_id}】Session过期，已触发后台异步密码登录（通过WebSocket服务API）")
    
    # 新起一个线程在后台调用WebSocket服务的密码登录API
    thread = threading.Thread(
        target=_do_password_login_via_api,
        args=(account_id,),
        name=f"password_login_{account_id}",
        daemon=True
    )
    thread.start()


def _do_password_login_via_api(account_id: str) -> None:
    """通过HTTP调用WebSocket服务的密码登录API（在独立线程中运行）
    
    流程：
    1. 调用 websocket 服务的 /internal/accounts/{account_id}/password-login-refresh 接口
    2. 该接口会执行密码登录并更新Cookie到数据库
    
    Args:
        account_id: 账号ID
    """
    import time
    import requests
    
    try:
        logger.info(f"【{account_id}】[后台密码登录] 开始通过API调用WebSocket服务...")
        
        # 获取WebSocket服务地址
        from common.core.config import get_settings
        settings = get_settings()
        websocket_url = settings.websocket_service_url
        
        # 调用密码登录刷新API
        api_url = f"{websocket_url}/internal/accounts/{account_id}/password-login-refresh"
        
        try:
            response = requests.post(
                api_url,
                json={"trigger_reason": "Session过期"},
                timeout=10  # API立即返回，无需长时间等待
            )
            
            result = response.json()
            
            if result.get('success'):
                logger.info(f"【{account_id}】[后台密码登录] 任务已提交: {result.get('message')}")
            else:
                error_msg = result.get('message', '未知错误')
                logger.warning(f"【{account_id}】[后台密码登录] API调用失败: {error_msg}")
                    
        except requests.exceptions.Timeout:
            logger.error(f"【{account_id}】[后台密码登录] API调用超时")
        except requests.exceptions.ConnectionError:
            logger.error(f"【{account_id}】[后台密码登录] 无法连接到WebSocket服务: {websocket_url}")
        except Exception as req_e:
            logger.error(f"【{account_id}】[后台密码登录] API请求异常: {req_e}")
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"【{account_id}】[后台密码登录] 执行异常: {error_msg}")
        import traceback
        logger.error(f"【{account_id}】[后台密码登录] 详细堆栈:\n{traceback.format_exc()}")
