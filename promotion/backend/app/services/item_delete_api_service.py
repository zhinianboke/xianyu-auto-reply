"""
返佣系统 - 闲鱼商品删除API服务

功能：
1. 调用 mtop.alibaba.idle.seller.pc.item.delete 接口删除闲鱼商品
2. 支持令牌过期自动重试（使用响应 Set-Cookie 更新本地 Cookie）
3. 使用账号对应的 Cookie 进行鉴权
"""
from __future__ import annotations

import json
import time

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_sign, trans_cookies
from common.utils.cookie_refresh import (
    extract_cookies_from_response,
    merge_cookies,
    update_account_cookies_in_db,
)

# mtop API 配置
DELETE_ITEM_API = "mtop.alibaba.idle.seller.pc.item.delete"
DELETE_ITEM_URL = f"https://h5api.m.goofish.com/h5/{DELETE_ITEM_API}/1.0/"

# 最大令牌过期重试次数
MAX_TOKEN_RETRY = 1

# 请求超时（秒）
REQUEST_TIMEOUT = 20


async def delete_item_from_xianyu(
    account_id: str,
    cookies_str: str,
    item_id: str,
    retry_count: int = 0,
) -> dict:
    """
    调用闲鱼 mtop 接口删除商品

    Args:
        account_id: 闲鱼账号ID（用于日志和Cookie更新）
        cookies_str: 账号的Cookie字符串
        item_id: 要删除的闲鱼商品ID
        retry_count: 令牌过期内部重试计数

    Returns:
        {"success": True/False, "message": "...", "cookies_str": "更新后的cookies"}
    """
    try:
        cookies = trans_cookies(cookies_str)
        timestamp = str(int(time.time() * 1000))

        # 构造请求数据
        data_val = json.dumps(
            {"itemId": str(item_id), "draftId": None},
            separators=(",", ":"),
        )

        # 从cookie获取token并生成签名
        token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
        sign = generate_sign(timestamp, token, data_val)

        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": timestamp,
            "sign": sign,
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "needLoginPC": "true",
            "showErrorToast": "true",
            "api": DELETE_ITEM_API,
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21107h.42829799.0.0",
        }

        headers = {
            "accept": "application/json",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "idle_site_biz_code": "COMMONPRO",
            "idle_user_group_member_id": "",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="146", "Not=A?Brand";v="8", "Chromium";v="146"',
            "sec-ch-ua-arch": '"x64"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Win32"',
            "sec-ch-ua-platform-version": '"10.0.0"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "referer": "https://seller.goofish.com/?site=COMMONPRO",
            "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        }

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                DELETE_ITEM_URL,
                params=params,
                data={"data": data_val},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                res_json = await response.json(content_type=None)

                # 处理响应中的 Set-Cookie，合并更新到内存和数据库
                new_cookies = extract_cookies_from_response(response)
                if new_cookies:
                    cookies_str = merge_cookies(cookies_str, new_cookies)
                    await update_account_cookies_in_db(account_id, cookies_str)
                    logger.info(
                        f"【{account_id}】删除商品API已从Set-Cookie合并 {len(new_cookies)} 个Cookie字段并更新到数据库"
                    )

                ret = res_json.get("ret", [])
                ret_str = ret[0] if ret else ""

                # 成功
                if "SUCCESS" in ret_str:
                    data = res_json.get("data", {})
                    code = data.get("code", "")
                    if code == "success" or data.get("data") is True:
                        logger.info(f"【{account_id}】删除商品[{item_id}]成功")
                        return {"success": True, "message": "删除成功", "cookies_str": cookies_str}
                    # API返回SUCCESS但data层面失败
                    msg = data.get("msg", "") or str(data)
                    logger.warning(f"【{account_id}】删除商品[{item_id}]API返回异常: {msg}")
                    return {"success": False, "message": msg, "cookies_str": cookies_str}

                # 令牌过期 - 用更新后的cookie重试
                if _is_token_expired(ret) and retry_count < MAX_TOKEN_RETRY:
                    logger.info(
                        f"【{account_id}】删除商品[{item_id}]令牌过期，"
                        f"准备重试({retry_count + 1})"
                    )
                    return await delete_item_from_xianyu(
                        account_id=account_id,
                        cookies_str=cookies_str,
                        item_id=item_id,
                        retry_count=retry_count + 1,
                    )

                # 其他错误
                logger.warning(f"【{account_id}】删除商品[{item_id}]失败: {ret_str}")
                return {"success": False, "message": ret_str, "cookies_str": cookies_str}

    except aiohttp.ClientError as e:
        logger.warning(f"【{account_id}】删除商品[{item_id}]网络失败: {e}")
        return {"success": False, "message": f"网络错误: {e}", "cookies_str": cookies_str}
    except Exception as e:
        logger.error(f"【{account_id}】删除商品[{item_id}]异常: {e}")
        return {"success": False, "message": str(e), "cookies_str": cookies_str}


def _is_token_expired(ret: list) -> bool:
    """
    判断mtop返回是否为令牌过期错误

    覆盖 FAIL_SYS_TOKEN_EXOIRED（API实际返回的拼写错误）
    和 FAIL_SYS_TOKEN_EXPIRED（正确拼写）两种变体
    """
    if not ret:
        return False
    ret_str = str(ret)
    return (
        "FAIL_SYS_TOKEN_EXOIRED" in ret_str
        or "FAIL_SYS_TOKEN_EXPIRED" in ret_str
        or "令牌过期" in ret_str
    )
