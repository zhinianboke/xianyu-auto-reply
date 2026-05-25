"""
淘宝联盟 - 选品广场服务

功能：
1. 调用淘宝开放平台升级版API（taobao.tbk.dg.material.optional.upgrade）
2. 使用AppKey + AppSecret签名鉴权
3. 支持关键词搜索、排序、分页
"""
from __future__ import annotations

import hashlib
import json
import time

import aiohttp
from loguru import logger


# 淘宝开放平台网关地址
TAOBAO_API_URL = "https://gw.api.taobao.com/router/rest"

# 升级版API方法名
API_METHOD = "taobao.tbk.dg.material.optional.upgrade"

# 升级版API响应根节点（方法名下划线格式 + _response）
API_RESPONSE_KEY = "tbk_dg_material_optional_upgrade_response"

# 排序字段映射（前端key -> 升级版API sort字段值）
# 支持：total_sales(销量), tk_rate(淘客收入比率), tk_mkt_rate(营销佣金),
#       tk_total_sales(累计推广量), tk_total_commi(总支出佣金),
#       final_promotion_price(预估到手价), match(匹配分)
SORT_MAP = {
    "default": "",
    "total_sales_des": "total_sales_des",
    "total_sales_asc": "total_sales_asc",
    "tk_rate_des": "tk_rate_des",
    "tk_rate_asc": "tk_rate_asc",
    "tk_mkt_rate_des": "tk_mkt_rate_des",
    "tk_mkt_rate_asc": "tk_mkt_rate_asc",
    "tk_total_sales_des": "tk_total_sales_des",
    "tk_total_sales_asc": "tk_total_sales_asc",
    "tk_total_commi_des": "tk_total_commi_des",
    "tk_total_commi_asc": "tk_total_commi_asc",
    "final_promotion_price_asc": "final_promotion_price_asc",
    "final_promotion_price_des": "final_promotion_price_des",
    "match_des": "match_des",
    "match_asc": "match_asc",
}


def _generate_sign(params: dict, app_secret: str) -> str:
    """
    生成淘宝开放平台API签名（MD5方式）

    签名规则：
    1. 按参数名ASCII升序排列
    2. 拼接成 secret + key1value1key2value2... + secret
    3. 对拼接串做MD5，转大写

    Args:
        params: API请求参数（不含sign）
        app_secret: 应用密钥

    Returns:
        签名字符串（大写MD5）
    """
    sorted_keys = sorted(params.keys())
    sign_str = app_secret
    for key in sorted_keys:
        value = params[key]
        if value is not None and value != "":
            sign_str += f"{key}{value}"
    sign_str += app_secret

    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()


def _build_api_params(
    keyword: str,
    page_no: int,
    page_size: int,
    sort: str,
    material_id: int,
    app_key: str,
    app_secret: str,
    adzone_id: str,
    cat: str = "",
    has_coupon: bool | None = None,
    need_free_shipment: bool | None = None,
    is_tmall: bool | None = None,
    start_tk_rate: int | None = None,
    end_tk_rate: int | None = None,
    start_price: float | None = None,
    end_price: float | None = None,
) -> dict:
    """
    构建淘宝开放平台升级版API请求参数

    Args:
        keyword: 搜索关键词
        page_no: 页码（从1开始）
        page_size: 每页数量
        sort: 排序方式
        material_id: 物料ID（默认80309）
        app_key: 应用Key
        app_secret: 应用密钥
        adzone_id: 推广位ID
        cat: 商品类目ID，多个用逗号分隔
        has_coupon: 是否有优惠券
        need_free_shipment: 是否包邮
        is_tmall: 是否天猫商品
        start_tk_rate: 最低佣金率（基点，如1350表示13.5%）
        end_tk_rate: 最高佣金率（基点）
        start_price: 最低价格（元）
        end_price: 最高价格（元）

    Returns:
        完整的请求参数字典（含签名）
    """
    # 系统参数
    params = {
        "method": API_METHOD,
        "app_key": app_key,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
    }

    # 业务参数
    if keyword:
        params["q"] = keyword
    if adzone_id:
        params["adzone_id"] = adzone_id
    # 物料ID（不传时API默认80309）
    params["material_id"] = str(material_id) if material_id else "80309"
    params["page_no"] = str(page_no)
    params["page_size"] = str(page_size)
    if sort and sort in SORT_MAP and SORT_MAP[sort]:
        params["sort"] = SORT_MAP[sort]
    # 商品类目ID
    if cat:
        params["cat"] = cat
    # 是否有优惠券
    if has_coupon is True:
        params["has_coupon"] = "true"
    # 是否包邮
    if need_free_shipment is True:
        params["need_free_shipment"] = "true"
    # 是否天猫
    if is_tmall is True:
        params["is_tmall"] = "true"
    # 佣金率范围（基点）
    if start_tk_rate is not None and start_tk_rate > 0:
        params["start_tk_rate"] = str(start_tk_rate)
    if end_tk_rate is not None and end_tk_rate > 0:
        params["end_tk_rate"] = str(end_tk_rate)
    # 价格范围（元）
    if start_price is not None and start_price > 0:
        params["start_price"] = str(start_price)
    if end_price is not None and end_price > 0:
        params["end_price"] = str(end_price)

    # 生成签名
    params["sign"] = _generate_sign(params, app_secret)

    return params


async def get_taobao_account(session, user_id: int, account_id: int | None = None):
    """
    获取用户的淘宝类型账号（含AppKey/AppSecret）

    Args:
        session: 数据库会话
        user_id: 用户ID
        account_id: 指定账号ID（可选）

    Returns:
        FYAccount对象或None
    """
    from sqlalchemy import select
    from common.models.fy_account import FYAccount, FYAccountType

    stmt = select(FYAccount).where(
        FYAccount.owner_id == user_id,
        FYAccount.account_type == FYAccountType.TAOBAO,
        FYAccount.enabled == True,
    )
    if account_id:
        stmt = stmt.where(FYAccount.id == account_id)
    stmt = stmt.order_by(FYAccount.id.asc()).limit(1)

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def search_products(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    sort: str = "default",
    material_id: int = 0,
    cat: str = "",
    has_coupon: bool | None = None,
    need_free_shipment: bool | None = None,
    is_tmall: bool | None = None,
    start_tk_rate: int | None = None,
    end_tk_rate: int | None = None,
    start_price: float | None = None,
    end_price: float | None = None,
    session=None,
    user_id: int = 0,
    account_id: int | None = None,
) -> dict:
    """
    通过淘宝开放平台API搜索商品

    从用户的淘宝账号中读取AppKey/AppSecret

    Args:
        keyword: 搜索关键词
        page: 页码（从1开始）
        page_size: 每页数量（最大100）
        sort: 排序方式
        material_id: 物料ID（0表示不限）
        cat: 商品类目ID，多个用逗号分隔
        has_coupon: 是否有优惠券
        need_free_shipment: 是否包邮
        is_tmall: 是否天猫商品
        start_tk_rate: 最低佣金率（基点）
        end_tk_rate: 最高佣金率（基点）
        start_price: 最低价格（元）
        end_price: 最高价格（元）
        session: 数据库会话
        user_id: 当前用户ID
        account_id: 指定账号ID

    Returns:
        包含商品列表的字典
    """
    # 从数据库获取淘宝账号
    account = await get_taobao_account(session, user_id, account_id) if session else None
    if not account:
        return {"success": False, "message": "未找到可用的淘宝账号，请先在账号管理中添加淘宝类型账号"}

    app_key = account.app_key or ""
    app_secret = account.app_secret or ""
    adzone_id_raw = account.adzone_id or ""

    if not app_key or not app_secret:
        return {"success": False, "message": "淘宝账号未配置AppKey/AppSecret，请更新账号信息"}

    if not adzone_id_raw:
        return {"success": False, "message": "淘宝账号未配置推广位ID，请更新账号信息"}

    # 解析推广位ID：纯数字直接用，含_取最后一段
    adzone_id = _parse_adzone_id(adzone_id_raw)

    # 构建请求参数
    params = _build_api_params(
        keyword=keyword,
        page_no=page,
        page_size=page_size,
        sort=sort,
        material_id=material_id,
        app_key=app_key,
        app_secret=app_secret,
        adzone_id=adzone_id,
        cat=cat,
        has_coupon=has_coupon,
        need_free_shipment=need_free_shipment,
        is_tmall=is_tmall,
        start_tk_rate=start_tk_rate,
        end_tk_rate=end_tk_rate,
        start_price=start_price,
        end_price=end_price,
    )

    # 打印请求参数（脱敏敏感字段）
    log_params = {k: v for k, v in params.items() if k not in ("sign",)}
    if "app_key" in log_params:
        log_params["app_key"] = log_params["app_key"][:4] + "****"
    logger.info(f"淘宝开放平台请求参数: {log_params}")

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(
                TAOBAO_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"淘宝开放平台请求失败: HTTP {resp.status}")
                    return {"success": False, "message": f"淘宝开放平台请求失败: HTTP {resp.status}"}

                data = await resp.json(content_type=None)
                logger.info(f"淘宝开放平台返回: {json.dumps(data, ensure_ascii=False)}")

                # 检查错误
                if "error_response" in data:
                    err = data["error_response"]
                    error_msg = err.get("sub_msg") or err.get("msg") or "接口调用失败"
                    logger.warning(f"淘宝开放平台错误: code={err.get('code')}, msg={error_msg}")
                    return {"success": False, "message": f"淘宝联盟接口错误: {error_msg}"}

                # 解析商品数据
                return _parse_api_response(data)

    except aiohttp.ClientError as e:
        logger.error(f"淘宝开放平台网络异常: {e}")
        return {"success": False, "message": f"网络请求异常: {str(e)}"}
    except Exception as e:
        logger.error(f"淘宝联盟选品搜索异常: {e}")
        return {"success": False, "message": f"搜索异常: {str(e)}"}


def _parse_api_response(data: dict) -> dict:
    """
    解析升级版API返回数据

    升级版响应结构（嵌套）：
    {
        "tbk_dg_material_optional_upgrade_response": {
            "total_results": 100,
            "result_list": {
                "map_data": [{
                    "item_id": "xxx",
                    "item_basic_info": { title, pict_url, volume, shop_title, ... },
                    "publish_info": { income_rate, click_url, income_info: {...}, ... },
                    "price_promotion_info": { final_promotion_price, zk_final_price, ... }
                }]
            }
        }
    }

    Args:
        data: 原始API返回数据

    Returns:
        格式化后的商品列表
    """
    response = data.get(API_RESPONSE_KEY, {})
    total_results = response.get("total_results", 0)
    result_list = response.get("result_list", {}).get("map_data", [])

    products = []
    for item in result_list:
        basic = item.get("item_basic_info", {})
        publish = item.get("publish_info", {})
        price_promo = item.get("price_promotion_info", {})
        income = publish.get("income_info", {})

        # 收入比率（佣金率+补贴率，如 "5.50" 表示5.50%）
        income_rate = publish.get("income_rate", "0")
        income_rate_display = f"{income_rate}%"

        # 佣金率和佣金金额（API返回基点格式：1350表示13.50%，需除以100）
        commission_rate_raw = income.get("commission_rate", "0")
        commission_amount_str = income.get("commission_amount", "0")
        try:
            commission_rate_pct = f"{float(commission_rate_raw) / 100:.2f}"
        except (ValueError, TypeError):
            commission_rate_pct = "0"

        # 补贴信息（同样是基点格式）
        subsidy_rate_raw = income.get("subsidy_rate", "0")
        subsidy_amount = income.get("subsidy_amount", "0")
        try:
            subsidy_rate_pct = f"{float(subsidy_rate_raw) / 100:.2f}"
        except (ValueError, TypeError):
            subsidy_rate_pct = "0"

        # 价格信息
        reserve_price = price_promo.get("reserve_price", "0")  # 一口价/划线价
        zk_final_price = price_promo.get("zk_final_price", "0")  # 销售价
        final_promotion_price = price_promo.get("final_promotion_price", "0")  # 预估到手价

        # 预估佣金 = 佣金金额 + 补贴金额
        try:
            total_earn = round(float(commission_amount_str) + float(subsidy_amount), 2)
        except (ValueError, TypeError):
            total_earn = 0

        # 推广链接
        click_url = publish.get("click_url", "")
        coupon_share_url = publish.get("coupon_share_url", "")
        promotion_path = _build_promotion_path(price_promo)

        product = {
            "item_id": item.get("item_id", ""),
            "title": basic.get("title", ""),
            "short_title": basic.get("short_title", ""),
            "pic": _fix_image_url(basic.get("pict_url", "")),
            "white_image": _fix_image_url(basic.get("white_image", "") or basic.get("pict_url", "")),
            "price": reserve_price,
            "zk_final_price": zk_final_price,
            "promotion_price": final_promotion_price,
            "shop_title": basic.get("shop_title", ""),
            "brand_name": basic.get("brand_name", ""),
            "commission_rate": f"{commission_rate_pct}%",
            "income_rate": income_rate_display,
            "commission_amount": f"¥{commission_amount_str}",
            "subsidy_rate": f"{subsidy_rate_pct}%",
            "subsidy_amount": f"¥{subsidy_amount}",
            "total_earn": f"¥{total_earn}",
            "commission_type": publish.get("commission_type", ""),
            "volume": str(basic.get("volume", "") or basic.get("tk_total_sales", "") or "0"),
            "tk_total_sales": basic.get("tk_total_sales", "0"),
            "annual_vol": basic.get("annual_vol", ""),
            "two_hour_sales": str(publish.get("two_hour_promotion_sales", "")),
            "daily_sales": str(publish.get("daily_promotion_sales", "")),
            "user_type": basic.get("user_type", 0),
            "seller_id": str(basic.get("seller_id", "")),
            "category_name": basic.get("category_name", "") or basic.get("level_one_category_name", ""),
            "provcity": basic.get("provcity", ""),
            "real_post_fee": basic.get("real_post_fee", ""),
            "click_url": _fix_image_url(click_url),
            "coupon_share_url": _fix_image_url(coupon_share_url),
            "coupon_info": _build_coupon_info_from_promotion_path(promotion_path),
            "promotion_tags": _build_promotion_tags(item),
            "promotion_path": promotion_path,
        }
        products.append(product)

    return {
        "success": True,
        "data": {
            "products": products,
            "total": total_results,
            "sort_options": [],
        },
    }


def _build_promotion_tags(item: dict) -> list[str]:
    """
    从升级版商品数据中提取促销标签

    标签来源：
    1. price_promotion_info.promotion_tag_list（88VIP、花呗免息等）
    2. publish_info.include_dxjh（定向计划）
    3. publish_info.commission_type（佣金类型）
    4. item_basic_info.real_post_fee（包邮）
    5. price_promotion_info.gov_subsidy（国家补贴）
    """
    tags = []
    basic = item.get("item_basic_info", {})
    publish = item.get("publish_info", {})
    price_promo = item.get("price_promotion_info", {})

    # 平台标签
    tag_list = price_promo.get("promotion_tag_list", {}).get("promotion_tag_map_data", [])
    if isinstance(tag_list, dict):
        tag_list = [tag_list]
    for tag_item in tag_list:
        tag_name = tag_item.get("tag_name", "")
        if tag_name:
            tags.append(tag_name)

    # 国家补贴
    gov_subsidy = price_promo.get("gov_subsidy", {})
    if gov_subsidy and gov_subsidy.get("tag_name"):
        tags.append(gov_subsidy["tag_name"])

    # 佣金类型
    comm_type = publish.get("commission_type", "")
    if comm_type == "MKT":
        tags.append("营销计划")
    elif comm_type == "SP":
        tags.append("定向计划")

    # 包邮
    if str(basic.get("real_post_fee", "")) == "0.00":
        tags.append("包邮")

    return tags


def _build_promotion_path(price_promo: dict) -> list[dict]:
    """
    提取到手价优惠路径

    来源：price_promotion_info.final_promotion_path_list
    """
    path_list = price_promo.get("final_promotion_path_list", {}).get("final_promotion_path_map_data", [])
    if isinstance(path_list, dict):
        path_list = [path_list]
    result = []
    for p in path_list:
        result.append({
            "title": p.get("promotion_title", ""),
            "desc": p.get("promotion_desc", ""),
            "fee": p.get("promotion_fee", ""),
        })
    return result


def _build_coupon_info_from_promotion_path(promotion_path: list[dict]) -> str:
    """根据选品广场的优惠路径生成优惠券信息文本。"""
    parts: list[str] = []
    seen: set[str] = set()
    for path in promotion_path:
        if not isinstance(path, dict):
            continue
        title = str(path.get("title") or "").strip()
        desc = str(path.get("desc") or "").strip()
        if title and desc:
            text = f"{title}: {desc}"
        else:
            text = title or desc
        if text and text not in seen:
            seen.add(text)
            parts.append(text)
    return "；".join(parts)


def _parse_adzone_id(raw: str) -> str:
    """
    解析推广位ID

    规则：纯数字直接使用，包含_则分割取最后一段
    例如：mm_123_456_789 -> 789，123456 -> 123456
    """
    raw = raw.strip()
    if "_" in raw:
        return raw.rsplit("_", 1)[-1]
    return raw


def _fix_image_url(url: str) -> str:
    """修复图片URL，补全协议头"""
    if url and url.startswith("//"):
        return f"https:{url}"
    if url and not url.startswith("http"):
        return f"https://{url}"
    return url
