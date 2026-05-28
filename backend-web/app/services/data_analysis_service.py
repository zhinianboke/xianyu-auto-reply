"""
数据分析服务

功能：
1. 调用闲鱼卖家数据罗盘API获取卖家数据概览
2. 支持多账号查询
3. 支持多种时间范围（近1天、近7天、近30天）
4. 带重试机制
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_sign, trans_cookies


# 卖家数据概览API配置
SELLER_SUMMARY_API = "mtop.alibaba.idle.seller.pc.datacompass.singleuser.seller.summary"
SELLER_SUMMARY_URL = f"https://h5api.m.goofish.com/h5/{SELLER_SUMMARY_API}/1.0/"

# 最大重试次数
MAX_RETRY = 3
# 重试间隔（秒）
RETRY_DELAY = 1.0


async def fetch_seller_summary(
    cookies_str: str,
    date_type: str = "recent7d",
    date_range: str = "",
    retry_count: int = 0,
) -> Dict[str, Any]:
    """
    获取卖家数据概览

    Args:
        cookies_str: 账号Cookie字符串
        date_type: 时间范围类型（recent1d/recent7d/recent30d）
        date_range: 自定义日期范围（可选）
        retry_count: 当前重试次数

    Returns:
        API返回的数据字典
    """
    if retry_count >= MAX_RETRY:
        logger.error(f"获取卖家数据概览失败，已达最大重试次数({MAX_RETRY})")
        return {"success": False, "message": f"请求失败，已重试{MAX_RETRY}次"}

    if not cookies_str:
        return {"success": False, "message": "账号Cookie为空"}

    try:
        cookies = trans_cookies(cookies_str)
    except Exception as e:
        return {"success": False, "message": f"Cookie解析失败: {e}"}

    # 生成时间戳和签名
    timestamp = str(int(time.time() * 1000))
    data_obj = {
        "dateRange": date_range,
        "dateType": date_type,
        "ms": "",
        "selectedSellerId": "undefined",
    }
    data_val = json.dumps(data_obj, separators=(",", ":"), ensure_ascii=False)

    # 从Cookie中提取token
    token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
    sign = generate_sign(timestamp, token, data_val)

    # 构建请求参数
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
        "showErrorToast": "true",
        "api": SELLER_SUMMARY_API,
        "sessionOption": "AutoLoginOnly",
    }

    # 构建请求头
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": cookies_str,
        "Referer": "https://seller.goofish.com/?site=COMMONPRO",
        "idle_site_biz_code": "COMMONPRO",
        "idle_user_group_member_id": "",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SELLER_SUMMARY_URL,
                params=params,
                data={"data": data_val},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                try:
                    res_json = await response.json(content_type=None)
                except Exception:
                    text = await response.text()
                    logger.warning(f"卖家数据概览响应解析失败: {text[:200]}")
                    # 重试
                    await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
                    return await fetch_seller_summary(
                        cookies_str, date_type, date_range, retry_count + 1
                    )

                ret = res_json.get("ret", [])
                ret_str = ret[0] if ret else ""

                if "SUCCESS" in ret_str:
                    return {
                        "success": True,
                        "message": "获取成功",
                        "data": res_json.get("data", {}),
                    }
                else:
                    logger.warning(f"卖家数据概览接口返回错误: {ret_str}")
                    # 非成功响应，进行重试
                    await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
                    return await fetch_seller_summary(
                        cookies_str, date_type, date_range, retry_count + 1
                    )

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(
            f"卖家数据概览请求失败(第{retry_count + 1}次): {e}"
        )
        await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
        return await fetch_seller_summary(
            cookies_str, date_type, date_range, retry_count + 1
        )
    except Exception as e:
        logger.error(f"卖家数据概览请求异常: {e}")
        return {"success": False, "message": f"请求异常: {str(e)}"}


# 流量分布API配置
BROWSE_SUMMARY_API = "mtop.alibaba.idle.seller.pc.datacompass.singleuser.browse.summary"
BROWSE_SUMMARY_URL = f"https://h5api.m.goofish.com/h5/{BROWSE_SUMMARY_API}/1.0/"


async def fetch_browse_summary(
    cookies_str: str,
    date_type: str = "recent7d",
    date_range: str = "",
    retry_count: int = 0,
) -> Dict[str, Any]:
    """
    获取流量分布数据（来源分布、商品分布、时间分布、地域分布）

    Args:
        cookies_str: 账号Cookie字符串
        date_type: 时间范围类型（recent1d/recent7d/recent30d/customDate）
        date_range: 自定义日期范围（可选，格式: yyyyMMdd|yyyyMMdd）
        retry_count: 当前重试次数

    Returns:
        API返回的数据字典
    """
    if retry_count >= MAX_RETRY:
        logger.error(f"获取流量分布失败，已达最大重试次数({MAX_RETRY})")
        return {"success": False, "message": f"请求失败，已重试{MAX_RETRY}次"}

    if not cookies_str:
        return {"success": False, "message": "账号Cookie为空"}

    try:
        cookies = trans_cookies(cookies_str)
    except Exception as e:
        return {"success": False, "message": f"Cookie解析失败: {e}"}

    # 生成时间戳和签名
    timestamp = str(int(time.time() * 1000))
    # 流量分布接口的请求体较简单
    data_obj: Dict[str, str] = {"dateType": date_type}
    if date_type == "customDate" and date_range:
        data_obj["dateRange"] = date_range
    data_val = json.dumps(data_obj, separators=(",", ":"), ensure_ascii=False)

    # 从Cookie中提取token
    token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
    sign = generate_sign(timestamp, token, data_val)

    # 构建请求参数
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
        "showErrorToast": "true",
        "api": BROWSE_SUMMARY_API,
        "sessionOption": "AutoLoginOnly",
    }

    # 构建请求头
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": cookies_str,
        "Referer": "https://seller.goofish.com/?site=COMMONPRO",
        "idle_site_biz_code": "COMMONPRO",
        "idle_user_group_member_id": "",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BROWSE_SUMMARY_URL,
                params=params,
                data={"data": data_val},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                try:
                    res_json = await response.json(content_type=None)
                except Exception:
                    text = await response.text()
                    logger.warning(f"流量分布响应解析失败: {text[:200]}")
                    await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
                    return await fetch_browse_summary(
                        cookies_str, date_type, date_range, retry_count + 1
                    )

                ret = res_json.get("ret", [])
                ret_str = ret[0] if ret else ""

                if "SUCCESS" in ret_str:
                    return {
                        "success": True,
                        "message": "获取成功",
                        "data": res_json.get("data", {}),
                    }
                else:
                    logger.warning(f"流量分布接口返回错误: {ret_str}")
                    await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
                    return await fetch_browse_summary(
                        cookies_str, date_type, date_range, retry_count + 1
                    )

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(f"流量分布请求失败(第{retry_count + 1}次): {e}")
        await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
        return await fetch_browse_summary(
            cookies_str, date_type, date_range, retry_count + 1
        )
    except Exception as e:
        logger.error(f"流量分布请求异常: {e}")
        return {"success": False, "message": f"请求异常: {str(e)}"}
