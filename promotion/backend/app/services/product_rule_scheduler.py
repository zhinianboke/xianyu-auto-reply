"""
返佣系统 - 选品规则定时任务

功能：
1. 每20分钟执行一次，遍历所有启用的选品规则
2. 判断今天是否已完成（today_count >= daily_count）
3. 未完成则调用选品广场接口获取商品
4. 为每个商品生成淘口令
5. 将商品写入素材库
6. 更新规则的执行状态
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

AUTO_COUPON_NOTICE = "\n".join([
    "该商品仅提供淘宝优惠券，实现购物优惠，非实物，请知悉！！！",
    "该商品仅提供淘宝优惠券，实现购物优惠，非实物，请知悉！！！",
    "该商品仅提供淘宝优惠券，实现购物优惠，非实物，请知悉！！！",
])

# 定时任务间隔（秒）：20分钟
SCHEDULE_INTERVAL = 20 * 60

# 全局标记：是否正在执行
_running = False


async def run_product_rule_scheduler():
    """
    定时任务主循环

    每20分钟执行一次选品规则检查和执行
    """
    logger.info("选品规则定时任务已启动，间隔: 20分钟")
    # 启动后等待30秒再首次执行，避免和启动过程冲突
    await asyncio.sleep(30)

    while True:
        try:
            await _execute_all_rules()
        except Exception as e:
            logger.error(f"选品规则定时任务执行异常: {e}")
        await asyncio.sleep(SCHEDULE_INTERVAL)


async def _execute_all_rules():
    """
    遍历所有启用的选品规则并执行

    跳过今天已完成的规则
    """
    global _running
    if _running:
        logger.info("选品规则定时任务正在执行中，跳过本次")
        return
    _running = True

    try:
        from common.db.session import async_session_maker
        from common.models.fy_product_rule import FYProductRule

        async with async_session_maker() as session:
            # 查询所有启用的规则
            stmt = select(FYProductRule).where(FYProductRule.enabled == True)
            result = await session.execute(stmt)
            rules = result.scalars().all()

            if not rules:
                logger.info("没有启用的选品规则，跳过")
                return

            today = date.today()
            for rule in rules:
                try:
                    await _execute_single_rule(session, rule, today)
                except Exception as e:
                    logger.error(f"执行规则[{rule.id}]{rule.rule_name}异常: {e}")

    finally:
        _running = False


async def manual_execute_rule(rule_id: int, user_id: int) -> dict:
    """
    手动执行指定选品规则

    不受当日已完成限制，直接按 daily_count 获取商品

    Args:
        rule_id: 规则ID
        user_id: 用户ID

    Returns:
        执行结果字典
    """
    from common.db.session import async_session_maker
    from common.models.fy_product_rule import FYProductRule

    async with async_session_maker() as session:
        stmt = select(FYProductRule).where(
            FYProductRule.id == rule_id,
            FYProductRule.owner_id == user_id,
        )
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()
        if not rule:
            return {"success": False, "message": "规则不存在或无权限"}

        today = date.today()
        try:
            added = await _execute_single_rule(session, rule, today, force=True)
            return {"success": True, "message": f"手动执行完成，新增{added}条素材"}
        except Exception as e:
            logger.error(f"手动执行规则[{rule_id}]异常: {e}")
            return {"success": False, "message": f"执行失败: {str(e)}"}


async def _execute_single_rule(session: AsyncSession, rule, today: date, force: bool = False):
    """
    执行单个选品规则

    Args:
        session: 数据库会话
        rule: 选品规则ORM对象
        today: 今天日期
        force: 是否强制执行（手动触发时为True，不受当日限制）

    Returns:
        新增素材数量
    """
    # 如果last_run_date不是今天，重置today_count
    if rule.last_run_date != today:
        rule.today_count = 0
        rule.last_run_date = today

    # 今天已完成（force模式跳过此检查）
    if not force and rule.today_count >= rule.daily_count:
        logger.info(f"规则[{rule.id}]{rule.rule_name}今天已完成({rule.today_count}/{rule.daily_count})，跳过")
        return 0

    # 还需要获取多少条（force模式按daily_count重新获取）
    remaining = rule.daily_count if force else (rule.daily_count - rule.today_count)
    logger.info(f"执行规则[{rule.id}]{rule.rule_name}，今天还需{remaining}条")

    # 调用选品广场接口
    from app.services.taobao_alliance_service import search_products
    from app.services.material_service import batch_create_materials, collect_creatable_material_items

    products: list[dict] = []
    creatable_products: list[dict] = []
    current_page = 1
    fetch_page_size = min(max(remaining, 20), 100)
    total_pages: int | None = None
    while len(creatable_products) < remaining:
        page_result = await search_products(
            keyword=rule.keyword or "",
            page=current_page,
            page_size=fetch_page_size,
            sort=rule.sort or "default",
            cat=rule.cat or "",
            has_coupon=True,
            session=session,
            user_id=rule.owner_id,
        )
        if not page_result.get("success"):
            if not products:
                logger.warning(f"规则[{rule.id}]搜索失败: {page_result.get('message')}")
                return 0
            logger.warning(f"规则[{rule.id}]翻页搜索失败，已提前结束: {page_result.get('message')}")
            break
        page_data = page_result.get("data") or {}
        page_products = page_result.get("data", {}).get("products", [])
        if not page_products:
            break
        products.extend(page_products)
        creatable_products = await collect_creatable_material_items(
            session=session,
            user_id=rule.owner_id,
            account_id=str(rule.account_id or "").strip(),
            items=products,
        )
        total_count = int(page_data.get("total") or 0)
        if total_count > 0:
            total_pages = max(1, (total_count + fetch_page_size - 1) // fetch_page_size)
        logger.info(
            f"规则[{rule.id}]{rule.rule_name}选品翻页第{current_page}页完成，"
            f"本页{len(page_products)}条，累计候选{len(products)}条，可新增{len(creatable_products)}条"
        )
        if len(creatable_products) >= remaining:
            break
        if len(page_products) < fetch_page_size:
            break
        if total_pages is not None and current_page >= total_pages:
            break
        current_page += 1

    if not creatable_products:
        logger.info(f"规则[{rule.id}]暂无可新增素材")
        return 0

    creatable_products = creatable_products[:remaining]

    # 为每个商品生成淘口令并组装素材数据
    materials = []
    for p in creatable_products:
        detail_data = await _get_product_detail_safe(session, rule.owner_id, p)
        coupon_info = await _get_coupon_info_safe(session, rule.owner_id, p, detail_data)
        tpwd = await _generate_tpwd_safe(session, rule.owner_id, p)
        short_url = await _generate_short_url_safe(session, rule.owner_id, p)
        detail_images = detail_data.get("images") if isinstance(detail_data.get("images"), list) else []
        materials.append({
            "item_id": p.get("item_id", ""),
            "title": p.get("title", ""),
            "price": 0.1,
            "stock": 999,
            "description": _build_description(p, detail_data, coupon_info, short_url),
            "images": detail_images or ([p.get("pic", "")] if p.get("pic") else []),
            "click_url": p.get("click_url", ""),
            "coupon_url": p.get("coupon_share_url", ""),
            "coupon_info": coupon_info,
            "tpwd": tpwd,
            "short_url": short_url,
            "original_price": detail_data.get("zk_final_price") or p.get("zk_final_price", ""),
            "promotion_price": p.get("promotion_price", "") or detail_data.get("zk_final_price") or "",
            "commission_rate": p.get("commission_rate", ""),
            "commission_amount": p.get("commission_amount", ""),
            "shop_title": detail_data.get("shop_title") or p.get("shop_title", ""),
            "volume": detail_data.get("volume") or p.get("volume", ""),
        })

    # 批量写入素材库
    added = await batch_create_materials(session, rule.owner_id, str(rule.account_id or "").strip(), rule.id, materials)

    # 更新规则状态
    rule.today_count = (rule.today_count or 0) + added
    rule.total_selected_count = (rule.total_selected_count or 0) + added
    rule.last_run_at = datetime.now()
    rule.last_run_date = today
    await session.commit()

    logger.info(f"规则[{rule.id}]{rule.rule_name}本次新增{added}条素材，今日合计{rule.today_count}/{rule.daily_count}")
    return added


async def _generate_tpwd_safe(session: AsyncSession, user_id: int, product: dict) -> str:
    """
    安全生成淘口令，失败返回空字符串

    Args:
        session: 数据库会话
        user_id: 用户ID
        product: 商品数据

    Returns:
        淘口令字符串，失败返回空
    """
    url = product.get("coupon_share_url") or product.get("click_url", "")
    if not url:
        return ""
    try:
        from app.services.taobao_alliance_detail import create_tpwd
        result = await create_tpwd(
            text=product.get("title", "好物推荐"),
            url=url,
            logo=product.get("pic", ""),
            session=session,
            user_id=user_id,
        )
        if result.get("success") and result.get("data"):
            return result["data"].get("tpwd", "")
    except Exception as e:
        logger.warning(f"生成淘口令失败: {e}")
    return ""


async def _generate_short_url_safe(session: AsyncSession, user_id: int, product: dict) -> str:
    url = product.get("coupon_share_url") or product.get("click_url", "")
    if not url:
        return ""
    try:
        from app.services.taobao_alliance_detail import create_short_url

        result = await create_short_url(
            url=url,
            session=session,
            user_id=user_id,
        )
        if result.get("success") and result.get("data"):
            return result["data"].get("short_url", "")
    except Exception as e:
        logger.warning(f"生成短连接失败: {e}")
    return ""


async def _get_product_detail_safe(session: AsyncSession, user_id: int, product: dict) -> dict:
    """安全获取商品详情，失败返回空字典。"""
    item_id = str(product.get("item_id") or "").strip()
    if not item_id:
        return {}
    try:
        from app.services.taobao_alliance_detail import get_product_detail

        result = await get_product_detail(item_id=item_id, session=session, user_id=user_id)
        if result.get("success") and isinstance(result.get("data"), dict):
            return result["data"]
    except Exception as e:
        logger.warning(f"获取商品[{item_id}]详情失败: {e}")
    return {}


async def _get_coupon_info_safe(session: AsyncSession, user_id: int, product: dict, detail_data: dict | None = None) -> str:
    coupon_info = str(product.get("coupon_info") or "").strip()
    if coupon_info:
        return coupon_info[:255]
    detail = detail_data or await _get_product_detail_safe(session, user_id, product)
    return str(detail.get("coupon_info") or "").strip()[:255]


def merge_short_url_into_description(description: str, short_url: str) -> str:
    normalized_description = str(description or "")
    normalized_short_url = str(short_url or "").strip()
    if not normalized_short_url:
        return normalized_description

    lines = normalized_description.split("\n")
    short_url_line = f"商品链接：{normalized_short_url}"

    for index, line in enumerate(lines):
        if line.startswith(("商品链接：", "商品链接:")):
            lines[index] = short_url_line
            return "\n".join(lines)

    for index, line in enumerate(lines):
        if line.startswith(("店铺:", "店铺：")):
            lines.insert(index + 1, short_url_line)
            return "\n".join(lines)

    notice_line = AUTO_COUPON_NOTICE.split("\n")[0]
    for index, line in enumerate(lines):
        if line == notice_line:
            lines.insert(index, short_url_line)
            return "\n".join(lines)

    if not normalized_description:
        return short_url_line
    return f"{normalized_description}\n{short_url_line}"


def _build_description(product: dict, detail_data: dict | None = None, coupon_info: str = "", short_url: str = "") -> str:
    """
    根据商品信息构建描述文本

    Args:
        product: 商品数据

    Returns:
        描述文本
    """
    detail = detail_data or {}
    parts: list[str] = []
    normalized_coupon_info = str(coupon_info or "").strip()
    if normalized_coupon_info:
        parts.append(f"优惠券信息: {normalized_coupon_info}")

    promotion_price = str(product.get("promotion_price") or "").strip()
    display_price = str(
        detail.get("zk_final_price")
        or product.get("zk_final_price")
        or detail.get("price")
        or product.get("price")
        or ""
    ).strip()
    if normalized_coupon_info and promotion_price:
        parts.append("")
    if promotion_price:
        parts.append(f"到手价: ¥{promotion_price}")
    if display_price and display_price != promotion_price:
        parts.append(f"价格: ¥{display_price}")

    shop_title = str(detail.get("shop_title") or product.get("shop_title") or "").strip()
    if shop_title:
        parts.append(f"店铺: {shop_title}")

    if shop_title:
        parts.extend(["", "", ""])
    parts.extend(AUTO_COUPON_NOTICE.split("\n"))

    return merge_short_url_into_description("\n".join(parts), short_url)
