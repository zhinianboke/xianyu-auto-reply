"""
用户头像查询服务

功能：
1. 调用 mtop.taobao.idlemessage.pc.user.query 查询闲鱼用户头像
2. 使用 Redis 缓存头像URL，过期时间24小时
3. 支持令牌过期自动重试，并保存返回的cookies到数据库

参照项目中定时补发货（freeshipping_service）和登录续期（login_renew_task）的 mtop 调用模式
"""
from __future__ import annotations

import json
import time
from typing import Optional

import aiohttp
from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.redis_client import get_redis_client
from common.models.xy_account import XYAccount
from common.utils.xianyu_utils import generate_sign, trans_cookies

# Redis缓存键前缀
AVATAR_CACHE_PREFIX = "chat:avatar:"
# 缓存过期时间（24小时）
AVATAR_CACHE_TTL = 86400

# mtop API 配置
USER_QUERY_API = "mtop.taobao.idlemessage.pc.user.query"
USER_QUERY_URL = f"https://h5api.m.goofish.com/h5/{USER_QUERY_API}/4.0/"

# 最大令牌过期重试次数
MAX_TOKEN_RETRY = 1


async def get_user_info(
    account_id: str,
    cid: str,
    cookies_str: str,
    db: AsyncSession,
) -> Optional[dict]:
    """
    获取闲鱼对方用户信息（头像 + 昵称）

    优先从 Redis 缓存获取，缓存未命中时调用 mtop API 查询

    Args:
        account_id: 账号ID（用于日志和cookie更新）
        cid: 会话ID（作为 user.query 的 sessionId 参数）
        cookies_str: 账号的Cookie字符串
        db: 数据库会话（用于更新cookie）

    Returns:
        {"avatar": "头像URL", "nick": "昵称"} 或 None
    """
    # 1. 检查 Redis 缓存
    cache_key = f"{AVATAR_CACHE_PREFIX}{cid}"
    try:
        redis = await get_redis_client()
        cached = await redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                # 兼容旧格式（纯 URL 字符串）→ nick 为空，需重新查询
                if isinstance(data, str):
                    data = {"avatar": data, "nick": ""}
                # 如果 avatar 和 nick 都有值，直接返回缓存
                if data.get("avatar") and data.get("nick"):
                    return data
                # nick 或 avatar 缺失，继续往下重新查 API
            except (json.JSONDecodeError, TypeError):
                # 旧格式为纯 URL 字符串，需重新查询
                pass
    except Exception as e:
        logger.warning(f"【{account_id}】Redis读取用户信息缓存失败: {e}")

    # 2. 调用 mtop API 查询
    user_info = await _fetch_user_info_from_api(
        account_id=account_id,
        cid=cid,
        cookies_str=cookies_str,
        db=db,
        retry_count=0,
    )

    # 3. 写入 Redis 缓存
    if user_info:
        try:
            redis = await get_redis_client()
            await redis.set(cache_key, json.dumps(user_info, ensure_ascii=False), ex=AVATAR_CACHE_TTL)
        except Exception as e:
            logger.warning(f"【{account_id}】Redis写入用户信息缓存失败: {e}")

    return user_info


async def get_owner_user_info(
    account_id: str,
    cid: str,
    cookies_str: str,
    db: AsyncSession,
) -> Optional[dict]:
    """Query the seller profile for a conversation without using buyer cache."""
    return await _fetch_user_info_from_api(
        account_id=account_id,
        cid=cid,
        cookies_str=cookies_str,
        db=db,
        retry_count=0,
        is_owner=True,
    )


async def _fetch_user_info_from_api(
    account_id: str,
    cid: str,
    cookies_str: str,
    db: AsyncSession,
    retry_count: int = 0,
    is_owner: bool = False,
) -> Optional[dict]:
    """
    调用 mtop.taobao.idlemessage.pc.user.query 获取对方用户信息

    Args:
        account_id: 账号ID
        cid: 会话ID（用于 sessionId 参数）
        cookies_str: Cookie字符串
        db: 数据库会话
        retry_count: 令牌过期重试次数

    Returns:
        {"avatar": "头像URL", "nick": "昵称"} 或 None
    """
    try:
        cookies = trans_cookies(cookies_str)
        timestamp = str(int(time.time() * 1000))

        # 构造请求数据（sessionId 为会话ID，不是用户ID）
        data_val = json.dumps({
            "type": 0,
            "sessionType": 1,
            "sessionId": str(cid),
            "isOwner": is_owner,
        }, separators=(",", ":"))

        # 从cookie获取token并生成签名
        token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
        sign = generate_sign(timestamp, token, data_val)

        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": timestamp,
            "sign": sign,
            "v": "4.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": USER_QUERY_API,
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.im.0.0",
            "spm_pre": "a21ybx.home.sidebar.2.4c053da6MpVe1m",
            "log_id": "4c053da6MpVe1m",
        }

        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "referer": "https://www.goofish.com/",
            "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        }

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                USER_QUERY_URL,
                params=params,
                data={"data": data_val},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                res_json = await response.json()

                # 处理响应中的 set-cookie，合并更新到数据库
                new_cookies_str = _handle_response_cookies(response, cookies_str)
                if new_cookies_str and new_cookies_str != cookies_str:
                    await _update_account_cookies(db, account_id, new_cookies_str)
                    # 后续重试使用新cookie
                    cookies_str = new_cookies_str

                ret = res_json.get("ret", [])
                ret_str = ret[0] if ret else ""

                # 成功
                if "SUCCESS" in ret_str:
                    user_data = res_json.get("data", {}).get("userInfo", {})
                    logo = user_data.get("logo", "")
                    nick = user_data.get("nick", "")
                    if logo or nick:
                        logger.info(
                            f"【{account_id}】获取会话 {cid} 对方信息成功: "
                            f"nick={nick}"
                        )
                        return {"avatar": logo, "nick": nick}
                    return None

                # 令牌过期 - 用更新后的cookie重试
                if ("TOKEN_EXOIRED" in ret_str or "TOKEN_EXPIRED" in ret_str) and retry_count < MAX_TOKEN_RETRY:
                    logger.info(f"【{account_id}】查询用户信息令牌过期，准备重试({retry_count + 1})")
                    return await _fetch_user_info_from_api(
                        account_id=account_id,
                        cid=cid,
                        cookies_str=cookies_str,
                        db=db,
                        retry_count=retry_count + 1,
                        is_owner=is_owner,
                    )

                # Session过期等其他错误
                logger.warning(f"【{account_id}】查询用户信息失败: {ret_str}")
                return None

    except aiohttp.ClientError as e:
        logger.warning(f"【{account_id}】查询用户信息网络失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"【{account_id}】查询用户信息异常: {e}")
        return None


def _handle_response_cookies(response, original_cookies_str: str) -> Optional[str]:
    """
    处理响应中的 set-cookie 头，合并到原始Cookie

    Args:
        response: HTTP响应对象
        original_cookies_str: 原始Cookie字符串

    Returns:
        合并后的Cookie字符串，无更新返回None
    """
    try:
        set_cookies = response.headers.getall("Set-Cookie", [])
        if not set_cookies:
            return None

        original_cookies = trans_cookies(original_cookies_str)

        for cookie_str in set_cookies:
            if "=" in cookie_str:
                cookie_part = cookie_str.split(";")[0]
                if "=" in cookie_part:
                    key, value = cookie_part.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        original_cookies[key] = value

        new_str = "; ".join([f"{k}={v}" for k, v in original_cookies.items()])
        return new_str
    except Exception as e:
        logger.warning(f"处理头像响应Cookie失败: {e}")
        return None


async def _update_account_cookies(
    db: AsyncSession, account_id: str, new_cookies_str: str
) -> None:
    """
    更新账号Cookie到数据库

    Args:
        db: 数据库会话
        account_id: 账号ID
        new_cookies_str: 新的Cookie字符串
    """
    try:
        await db.execute(
            update(XYAccount)
            .where(XYAccount.account_id == account_id)
            .values(cookie=new_cookies_str)
        )
        await db.commit()
        logger.info(f"【{account_id}】头像查询后已更新Cookie到数据库")
    except Exception as e:
        logger.warning(f"【{account_id}】更新Cookie到数据库失败: {e}")
        await db.rollback()
