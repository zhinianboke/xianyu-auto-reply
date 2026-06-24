"""
闲鱼商品批量下架 API 服务

功能：
1. 调用 mtop.alibaba.idle.seller.pc.item.batch.offline 接口批量下架闲鱼在卖商品
   （下架 ≠ 删除：商品仍在卖家后台，可重新上架）
2. 支持令牌过期自动重试（使用响应 Set-Cookie 更新本地 Cookie）
3. 使用账号对应的 Cookie 进行鉴权

说明：
- 请求构造（签名、appKey、header 等）与删除商品接口
  (promotion/.../item_delete_api_service.py) 保持一致，仅 API 名、body、响应解析不同；
- body 为 data={"itemIds":"id1,id2,..."}（逗号拼接的商品ID串）。
"""
from __future__ import annotations

import json
import time

import aiohttp
from loguru import logger

from common.utils.cookie_refresh import (
    extract_cookies_from_response,
    merge_cookies,
    update_account_cookies_in_db,
)
from common.utils.xianyu_utils import generate_sign, trans_cookies

# mtop API 配置
BATCH_OFFLINE_API = "mtop.alibaba.idle.seller.pc.item.batch.offline"
BATCH_OFFLINE_URL = f"https://h5api.m.goofish.com/h5/{BATCH_OFFLINE_API}/1.0/"

# 最大令牌过期重试次数
MAX_TOKEN_RETRY = 1

# 请求超时（秒）
REQUEST_TIMEOUT = 20


async def batch_offline_items_from_xianyu(
    account_id: str,
    cookies_str: str,
    item_ids: list[str],
    retry_count: int = 0,
) -> dict:
    """调用闲鱼 mtop 接口批量下架商品

    Args:
        account_id: 闲鱼账号ID（用于日志和Cookie更新）
        cookies_str: 账号的Cookie字符串
        item_ids: 要下架的闲鱼商品ID列表
        retry_count: 令牌过期内部重试计数

    Returns:
        {
          "success": bool,            # 整体是否成功（至少一个成功视为True）
          "message": str,             # 中文结果说明
          "suc_count": int,           # 成功条数
          "fail_count": int,          # 失败条数
          "results": [{"item_id": str, "success": bool}, ...],  # 每个商品的下架结果
          "cookies_str": str,         # 更新后的cookies
        }
    """
    # 过滤空ID并去重保序，避免拼接出非法 itemIds
    cleaned_ids: list[str] = []
    seen: set[str] = set()
    for raw in item_ids or []:
        key = str(raw or "").strip()
        if key and key not in seen:
            seen.add(key)
            cleaned_ids.append(key)
    if not cleaned_ids:
        return {
            "success": False,
            "message": "没有有效的商品ID",
            "suc_count": 0,
            "fail_count": 0,
            "results": [],
            "cookies_str": cookies_str,
        }

    try:
        cookies = trans_cookies(cookies_str)
        timestamp = str(int(time.time() * 1000))

        # 构造请求数据：itemIds 为逗号拼接的商品ID串
        data_val = json.dumps(
            {"itemIds": ",".join(cleaned_ids)},
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
            "api": BATCH_OFFLINE_API,
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21107h.42826273.0.0",
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
            "referer": "https://seller.goofish.com/?site=COMMONPRO",
            "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        }

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                BATCH_OFFLINE_URL,
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
                        f"【{account_id}】批量下架API已从Set-Cookie合并 {len(new_cookies)} 个Cookie字段并更新到数据库"
                    )

                ret = res_json.get("ret", [])
                ret_str = ret[0] if ret else ""

                # 成功：解析每个商品的下架结果
                if "SUCCESS" in ret_str:
                    data = res_json.get("data", {})
                    code = data.get("code", "")
                    inner = data.get("data", {}) or {}
                    if code == "success":
                        results = [
                            {
                                "item_id": str(r.get("itemId", "")),
                                "success": bool(r.get("success")),
                            }
                            for r in (inner.get("itemProcessResultList") or [])
                        ]
                        suc_count = int(inner.get("sucCount", 0) or 0)
                        fail_count = int(inner.get("failCount", 0) or 0)
                        # 接口未返回计数时按 results 兜底统计
                        if not results and (suc_count or fail_count) == 0:
                            results = [{"item_id": i, "success": True} for i in cleaned_ids]
                            suc_count = len(cleaned_ids)
                        elif suc_count == 0 and fail_count == 0 and results:
                            suc_count = sum(1 for r in results if r["success"])
                            fail_count = len(results) - suc_count
                        logger.info(
                            f"【{account_id}】批量下架完成：成功{suc_count}，失败{fail_count}"
                        )
                        return {
                            "success": suc_count > 0,
                            "message": f"下架成功 {suc_count} 个，失败 {fail_count} 个",
                            "suc_count": suc_count,
                            "fail_count": fail_count,
                            "results": results,
                            "cookies_str": cookies_str,
                        }
                    # API返回SUCCESS但data层面失败
                    msg = data.get("msg", "") or str(data)
                    logger.warning(f"【{account_id}】批量下架API返回异常: {msg}")
                    return {
                        "success": False,
                        "message": msg,
                        "suc_count": 0,
                        "fail_count": len(cleaned_ids),
                        "results": [{"item_id": i, "success": False} for i in cleaned_ids],
                        "cookies_str": cookies_str,
                    }

                # 令牌过期 - 用更新后的cookie重试
                if _is_token_expired(ret) and retry_count < MAX_TOKEN_RETRY:
                    logger.info(
                        f"【{account_id}】批量下架令牌过期，准备重试({retry_count + 1})"
                    )
                    return await batch_offline_items_from_xianyu(
                        account_id=account_id,
                        cookies_str=cookies_str,
                        item_ids=cleaned_ids,
                        retry_count=retry_count + 1,
                    )

                # 其他错误
                logger.warning(f"【{account_id}】批量下架失败: {ret_str}")
                return {
                    "success": False,
                    "message": ret_str or "下架失败",
                    "suc_count": 0,
                    "fail_count": len(cleaned_ids),
                    "results": [{"item_id": i, "success": False} for i in cleaned_ids],
                    "cookies_str": cookies_str,
                }

    except aiohttp.ClientError as e:
        logger.warning(f"【{account_id}】批量下架网络失败: {e}")
        return {
            "success": False,
            "message": f"网络错误: {e}",
            "suc_count": 0,
            "fail_count": len(cleaned_ids),
            "results": [{"item_id": i, "success": False} for i in cleaned_ids],
            "cookies_str": cookies_str,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"【{account_id}】批量下架异常: {e}")
        return {
            "success": False,
            "message": str(e),
            "suc_count": 0,
            "fail_count": len(cleaned_ids),
            "results": [{"item_id": i, "success": False} for i in cleaned_ids],
            "cookies_str": cookies_str,
        }


def _is_token_expired(ret: list) -> bool:
    """判断mtop返回是否为令牌过期错误

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
