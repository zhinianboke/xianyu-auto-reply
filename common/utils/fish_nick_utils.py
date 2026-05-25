"""
闲鱼昵称获取工具

通过 mtop.taobao.idlemessage.pc.user.query/4.0 接口获取买家的闲鱼明文昵称。
支持令牌过期自动刷新Cookie并重试。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Optional

import aiohttp
from loguru import logger

APP_KEY = "34839810"
USER_QUERY_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.user.query/4.0/"
REQUEST_TIMEOUT = 10
MAX_RETRY = 2


def _generate_sign(timestamp: str, token: str, data: str) -> str:
    """生成 mtop 签名"""
    msg = f"{token}&{timestamp}&{APP_KEY}&{data}"
    return hashlib.md5(msg.encode("utf-8")).hexdigest()


def _get_h5_tk_token(cookies_str: str) -> str:
    """从 cookie 字符串中提取 _m_h5_tk 的 token 部分"""
    for part in cookies_str.split("; "):
        if part.startswith("_m_h5_tk="):
            value = part.split("=", 1)[1]
            return value.split("_")[0]
    return ""


async def get_buyer_fish_nick(
    cookies_str: str,
    chat_id: str,
    account_id: str = "",
) -> Optional[str]:
    """获取买家的闲鱼明文昵称

    通过聊天会话ID调用 user.query 接口获取对方的 fishNick。
    支持令牌过期时自动从响应中提取新Cookie、更新数据库并重试。

    Args:
        cookies_str: 当前账号的 cookie 字符串
        chat_id: 聊天会话ID（sessionId）
        account_id: 账号ID，仅用于日志标识

    Returns:
        闲鱼昵称（明文），获取失败返回 None
    """
    if not cookies_str or not chat_id:
        return None

    return await _fetch_fish_nick(cookies_str, chat_id, account_id, retry_count=0)


async def _fetch_fish_nick(
    cookies_str: str,
    chat_id: str,
    account_id: str,
    retry_count: int,
) -> Optional[str]:
    """内部实现：发起请求获取买家昵称，令牌过期时刷新Cookie重试

    Args:
        cookies_str: 当前Cookie字符串
        chat_id: 聊天会话ID
        account_id: 账号ID（日志用）
        retry_count: 当前重试次数

    Returns:
        闲鱼昵称（明文），获取失败返回 None
    """
    try:
        timestamp = str(int(time.time() * 1000))
        data_str = json.dumps(
            {"type": 0, "sessionType": 1, "sessionId": str(chat_id), "isOwner": False},
            separators=(",", ":"),
        )
        token = _get_h5_tk_token(cookies_str)
        sign = _generate_sign(timestamp, token, data_str)

        params = {
            "jsv": "2.7.2",
            "appKey": APP_KEY,
            "t": timestamp,
            "sign": sign,
            "v": "4.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "referer": "https://www.goofish.com/",
            "origin": "https://www.goofish.com",
            "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                USER_QUERY_URL,
                params=params,
                data={"data": data_str},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                # 从响应中提取新Cookie（令牌过期时服务端会返回新的_m_h5_tk）
                updated_cookies_str = await _handle_response_cookies(
                    resp, cookies_str, account_id
                )

                text = await resp.text()
                res = json.loads(text)

                ret = res.get("ret", [])
                logger.info(
                    f"【{account_id}】获取买家昵称接口响应: chat_id={chat_id}, "
                    f"ret={ret}, data keys={list(res.get('data', {}).keys())}"
                )

                if not any("SUCCESS" in str(r) for r in ret):
                    # 检查是否为令牌过期错误，若是则用更新后的Cookie重试
                    from common.utils.cookie_refresh import is_token_expired_error
                    if is_token_expired_error(ret) and retry_count < MAX_RETRY:
                        logger.info(
                            f"【{account_id}】获取买家昵称令牌过期，已更新Cookie，"
                            f"准备重试({retry_count + 1}/{MAX_RETRY})..."
                        )
                        await asyncio.sleep(0.5)
                        return await _fetch_fish_nick(
                            updated_cookies_str, chat_id, account_id, retry_count + 1
                        )

                    logger.warning(
                        f"【{account_id}】获取买家昵称失败: chat_id={chat_id}, ret={ret}"
                    )
                    return None

                user_info = res.get("data", {}).get("userInfo", {})
                fish_nick = user_info.get("fishNick")
                if fish_nick:
                    logger.info(
                        f"【{account_id}】获取买家闲鱼昵称成功: chat_id={chat_id}, fishNick={fish_nick}"
                    )
                    return fish_nick

                logger.warning(
                    f"【{account_id}】接口成功但未返回fishNick: chat_id={chat_id}, "
                    f"userInfo={user_info}"
                )
                return None

    except Exception as e:
        logger.warning(f"【{account_id}】获取买家昵称异常: chat_id={chat_id}, error={e}")
        if retry_count < MAX_RETRY:
            await asyncio.sleep(0.5)
            return await _fetch_fish_nick(cookies_str, chat_id, account_id, retry_count + 1)
        return None


async def _handle_response_cookies(
    response: aiohttp.ClientResponse,
    old_cookies_str: str,
    account_id: str,
) -> str:
    """处理响应中的Set-Cookie，合并到本地Cookie并更新数据库

    令牌过期时服务端会在响应头中返回新的cookie（包含新的_m_h5_tk），
    存储后重试请求即可使用新的token签名。

    Args:
        response: HTTP响应对象
        old_cookies_str: 原始Cookie字符串
        account_id: 账号ID

    Returns:
        合并后的Cookie字符串（如果没有新Cookie则返回原始字符串）
    """
    try:
        from common.utils.cookie_refresh import (
            extract_cookies_from_response, merge_cookies,
            update_account_cookies_in_db
        )

        new_cookies = extract_cookies_from_response(response)
        if new_cookies:
            merged_str = merge_cookies(old_cookies_str, new_cookies)
            # 写入数据库
            await update_account_cookies_in_db(account_id, merged_str)
            logger.info(
                f"【{account_id}】[获取昵称]已从响应中合并 {len(new_cookies)} 个Cookie字段并更新到数据库"
            )
            return merged_str
    except Exception as e:
        logger.warning(f"【{account_id}】[获取昵称]处理响应Cookie失败: {e}")

    return old_cookies_str
