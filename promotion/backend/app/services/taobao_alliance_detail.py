"""
淘宝联盟 - 商品详情服务

功能：
1. 调用淘宝开放平台 taobao.tbk.item.info.get 接口获取商品详情
2. 返回多张商品图片、叶子类目、是否包邮等额外信息
"""
from __future__ import annotations

import json
import time

import aiohttp
from loguru import logger

from app.services.taobao_alliance_service import (
    TAOBAO_API_URL,
    _generate_sign,
    _fix_image_url,
    get_taobao_account,
)

# 商品详情API方法名
DETAIL_API_METHOD = "taobao.tbk.item.info.get"
# 响应根节点
DETAIL_RESPONSE_KEY = "tbk_item_info_get_response"


async def get_product_detail(
    item_id: str,
    session=None,
    user_id: int = 0,
    account_id: int | None = None,
) -> dict:
    """
    获取商品详情

    调用 taobao.tbk.item.info.get 接口，返回商品多图、类目、是否包邮等信息

    Args:
        item_id: 商品ID
        session: 数据库会话
        user_id: 当前用户ID
        account_id: 指定账号ID

    Returns:
        包含商品详情的字典
    """
    if not item_id:
        return {"success": False, "message": "商品ID不能为空"}

    # 获取账号信息
    account = await get_taobao_account(session, user_id, account_id) if session else None
    if not account:
        return {"success": False, "message": "未找到可用的淘宝账号"}

    app_key = account.app_key or ""
    app_secret = account.app_secret or ""
    if not app_key or not app_secret:
        return {"success": False, "message": "淘宝账号未配置AppKey/AppSecret"}

    # 构建请求参数
    params = _build_detail_params(item_id, app_key, app_secret)

    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(TAOBAO_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
                logger.info(f"商品详情API返回: {data}")

                if "error_response" in data:
                    err = data["error_response"]
                    error_msg = err.get("sub_msg") or err.get("msg") or "接口调用失败"
                    return {"success": False, "message": f"淘宝联盟接口错误: {error_msg}"}

                return _parse_detail_response(data)

    except aiohttp.ClientError as e:
        logger.error(f"商品详情网络异常: {e}")
        return {"success": False, "message": f"网络请求异常: {str(e)}"}
    except Exception as e:
        logger.error(f"商品详情查询异常: {e}")
        return {"success": False, "message": f"查询异常: {str(e)}"}


def _build_detail_params(item_id: str, app_key: str, app_secret: str) -> dict:
    """
    构建商品详情API请求参数

    Args:
        item_id: 商品ID
        app_key: 应用Key
        app_secret: 应用密钥

    Returns:
        签名后的请求参数
    """
    params = {
        "method": DETAIL_API_METHOD,
        "app_key": app_key,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "num_iids": item_id,
        "platform": "2",  # 无线端
    }
    params["sign"] = _generate_sign(params, app_secret)
    return params


def _parse_detail_response(data: dict) -> dict:
    """
    解析商品详情API返回数据

    Args:
        data: 原始API返回

    Returns:
        格式化后的商品详情
    """
    response = data.get(DETAIL_RESPONSE_KEY, {})
    results = response.get("results", {}).get("n_tbk_item", [])

    if not results:
        return {"success": False, "message": "未找到商品信息"}

    item = results[0]

    # 多图列表
    small_images = item.get("small_images", {}).get("string", [])
    images = [_fix_image_url(img) for img in small_images if img]
    # 主图放在首位
    main_pic = _fix_image_url(item.get("pict_url", ""))
    if main_pic and main_pic not in images:
        images.insert(0, main_pic)

    detail = {
        "item_id": str(item.get("num_iid", "")),
        "title": item.get("title", ""),
        "pic": main_pic,
        "images": images,
        "price": item.get("reserve_price", ""),
        "zk_final_price": item.get("zk_final_price", ""),
        "volume": str(item.get("volume", 0)),
        "shop_title": item.get("nick", ""),
        "seller_id": str(item.get("seller_id", "")),
        "user_type": item.get("user_type", 0),
        "provcity": item.get("provcity", ""),
        "cat_name": item.get("cat_name", ""),
        "cat_leaf_name": item.get("cat_leaf_name", ""),
        "free_shipment": item.get("free_shipment", False),
        "hot_flag": item.get("hot_flag", ""),
        "item_url": item.get("item_url", ""),
        "tk_total_sales": str(item.get("tk_total_sales", "")),
        "tk_total_commi": str(item.get("tk_total_commi", "")),
        "coupon_info": item.get("coupon_info", ""),
    }

    return {"success": True, "data": detail}


# ==================== 淘口令生成 ====================

# 淘口令生成API方法名
TPWD_API_METHOD = "taobao.tbk.tpwd.create"
# 响应根节点
TPWD_RESPONSE_KEY = "tbk_tpwd_create_response"


async def create_tpwd(
    text: str,
    url: str,
    logo: str = "",
    session=None,
    user_id: int = 0,
    account_id: int | None = None,
) -> dict:
    """
    生成淘口令

    调用 taobao.tbk.tpwd.create 接口，将推广链接转为淘口令（如 ￥xxx￥）

    Args:
        text: 口令弹框内容（商品标题）
        url: 口令跳转目标页URL（推广链接）
        logo: 口令弹框logoURL（可选，商品图片）
        session: 数据库会话
        user_id: 当前用户ID
        account_id: 指定账号ID

    Returns:
        包含淘口令的字典
    """
    if not url:
        return {"success": False, "message": "推广链接不能为空"}

    # 获取账号信息
    account = await get_taobao_account(session, user_id, account_id) if session else None
    if not account:
        return {"success": False, "message": "未找到可用的淘宝账号"}

    app_key = account.app_key or ""
    app_secret = account.app_secret or ""
    if not app_key or not app_secret:
        return {"success": False, "message": "淘宝账号未配置AppKey/AppSecret"}

    # 构建请求参数
    params = _build_tpwd_params(text, url, logo, app_key, app_secret)

    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(TAOBAO_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
                logger.info(f"淘口令生成API返回: {data}")

                if "error_response" in data:
                    err = data["error_response"]
                    error_msg = err.get("sub_msg") or err.get("msg") or "接口调用失败"
                    return {"success": False, "message": f"淘口令生成失败: {error_msg}"}

                return _parse_tpwd_response(data)

    except aiohttp.ClientError as e:
        logger.error(f"淘口令生成网络异常: {e}")
        return {"success": False, "message": f"网络请求异常: {str(e)}"}
    except Exception as e:
        logger.error(f"淘口令生成异常: {e}")
        return {"success": False, "message": f"生成异常: {str(e)}"}


def _build_tpwd_params(text: str, url: str, logo: str, app_key: str, app_secret: str) -> dict:
    """
    构建淘口令生成API请求参数

    Args:
        text: 口令弹框内容
        url: 口令跳转目标页URL
        logo: 口令弹框logoURL
        app_key: 应用Key
        app_secret: 应用密钥

    Returns:
        签名后的请求参数
    """
    params = {
        "method": TPWD_API_METHOD,
        "app_key": app_key,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "text": text,
        "url": url,
    }
    if logo:
        params["logo"] = logo
    params["sign"] = _generate_sign(params, app_secret)
    return params


def _parse_tpwd_response(data: dict) -> dict:
    """
    解析淘口令生成API返回数据

    Args:
        data: 原始API返回

    Returns:
        包含淘口令的字典
    """
    response = data.get(TPWD_RESPONSE_KEY, {})
    tpwd_data = response.get("data", {})
    model = tpwd_data.get("model", "")

    if not model:
        return {"success": False, "message": "淘口令生成失败，未返回口令"}

    return {
        "success": True,
        "data": {
            "tpwd": model,
            "password_simple": tpwd_data.get("password_simple", ""),
        },
    }


SPREAD_API_METHOD = "taobao.tbk.spread.get"
SPREAD_RESPONSE_KEY = "tbk_spread_get_response"


async def create_short_url(
    url: str,
    session=None,
    user_id: int = 0,
    account_id: int | None = None,
) -> dict:
    if not url:
        return {"success": False, "message": "推广链接不能为空"}

    account = await get_taobao_account(session, user_id, account_id) if session else None
    if not account:
        return {"success": False, "message": "未找到可用的淘宝账号"}

    app_key = account.app_key or ""
    app_secret = account.app_secret or ""
    if not app_key or not app_secret:
        return {"success": False, "message": "淘宝账号未配置AppKey/AppSecret"}

    params = _build_short_url_params(url=url, app_key=app_key, app_secret=app_secret)

    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(TAOBAO_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
                logger.info(f"短连接生成API返回: {data}")

                if "error_response" in data:
                    err = data["error_response"]
                    error_msg = err.get("sub_msg") or err.get("msg") or "接口调用失败"
                    return {"success": False, "message": f"短连接生成失败: {error_msg}"}

                return _parse_short_url_response(data)

    except aiohttp.ClientError as e:
        logger.error(f"短连接生成网络异常: {e}")
        return {"success": False, "message": f"网络请求异常: {str(e)}"}
    except Exception as e:
        logger.error(f"短连接生成异常: {e}")
        return {"success": False, "message": f"生成异常: {str(e)}"}


def _build_short_url_params(url: str, app_key: str, app_secret: str) -> dict:
    params = {
        "method": SPREAD_API_METHOD,
        "app_key": app_key,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "requests": json.dumps([{"url": url}], ensure_ascii=False, separators=(",", ":")),
    }
    params["sign"] = _generate_sign(params, app_secret)
    return params


def _parse_short_url_response(data: dict) -> dict:
    response = data.get(SPREAD_RESPONSE_KEY, {})
    spread_list = response.get("results", {}).get("tbk_spread", [])
    if not spread_list:
        return {"success": False, "message": "短连接生成失败，未返回结果"}

    first_result = spread_list[0] or {}
    err_msg = str(first_result.get("err_msg") or "").strip()
    short_url = str(first_result.get("content") or "").strip()
    if not short_url:
        return {"success": False, "message": f"短连接生成失败: {err_msg or '未返回短连接'}"}
    if err_msg and err_msg.upper() != "OK":
        return {"success": False, "message": f"短连接生成失败: {err_msg}"}

    return {
        "success": True,
        "data": {
            "short_url": short_url,
        },
    }
