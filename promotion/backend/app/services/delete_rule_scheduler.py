"""
返佣系统 - 删除规则定时任务

功能：
1. 每10分钟执行一次，扫描所有启用的删除规则
2. 根据删除规则，关联主项目消息日志，查找从未被回复过的商品
3. 按发布时间从早到晚删除商品，使用 mtop API
4. 自动管理每日删除计数，跨日自动重置
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker

# 定时任务间隔（秒）：10分钟
SCHEDULER_INTERVAL = 600

# 北京时间时区
TZ_BEIJING = timezone(timedelta(hours=8))


async def run_delete_rule_scheduler() -> None:
    """
    删除规则定时任务入口

    每10分钟执行一次，扫描启用的删除规则并执行删除逻辑。
    """
    logger.info("删除规则定时任务启动，间隔: 10分钟")
    while True:
        try:
            await _execute_all_rules()
        except asyncio.CancelledError:
            logger.info("删除规则定时任务被取消")
            break
        except Exception as e:
            logger.error(f"删除规则定时任务异常: {e}")

        await asyncio.sleep(SCHEDULER_INTERVAL)


async def _execute_all_rules() -> None:
    """扫描并执行所有启用的删除规则"""
    from common.models.fy_delete_rule import FYDeleteRule

    try:
        async with async_session_maker() as session:
            today = datetime.now(TZ_BEIJING).date()

            # 查询所有启用的删除规则
            stmt = select(FYDeleteRule).where(FYDeleteRule.enabled == True)  # noqa: E712
            result = await session.execute(stmt)
            rules = result.scalars().all()

            if not rules:
                return

            logger.info(f"删除规则定时任务开始执行，共 {len(rules)} 条启用规则")

            for rule in rules:
                try:
                    await _execute_single_rule(session, rule, today)
                except Exception as e:
                    logger.error(
                        f"执行删除规则[{rule.id}] {rule.rule_name} 异常: {e}"
                    )

    except Exception as e:
        logger.error(f"删除规则定时任务查询规则失败: {e}")


async def _execute_single_rule(
    session: AsyncSession,
    rule,
    today: date,
) -> None:
    """
    执行单条删除规则

    Args:
        session: 数据库会话
        rule: 删除规则ORM对象
        today: 当天日期
    """
    # 跨日重置今日删除数
    if rule.last_run_date != today:
        rule.today_count = 0
        rule.last_run_date = today

    # 计算今天还能删除多少
    remaining = rule.daily_count - rule.today_count
    if remaining <= 0:
        return

    # 检查账号是否处于Session过期冷却期
    from common.utils.cookie_refresh import is_account_session_cooled
    if is_account_session_cooled(rule.account_id):
        return

    # 获取账号Cookie
    cookies_str = await _get_account_cookies(session, rule.account_id)
    if not cookies_str:
        logger.warning(
            f"删除规则[{rule.id}] 账号{rule.account_id}无可用Cookie，跳过"
        )
        return

    # 查找待删除的商品（从未被回复过的，发布满足天数的，按发布时间从早到晚排序）
    min_days = rule.min_publish_days or 7
    candidate_items = await _find_unreplied_items(
        session, rule.account_id, remaining, min_publish_days=min_days
    )
    if not candidate_items:
        logger.info(
            f"删除规则[{rule.id}] 账号{rule.account_id}暂无符合条件的待删除商品"
        )
        # 更新执行时间
        rule.last_run_at = datetime.now(TZ_BEIJING)
        session.add(rule)
        await session.commit()
        return

    logger.info(
        f"删除规则[{rule.id}] 账号{rule.account_id}找到 {len(candidate_items)} 个待删除商品"
    )

    # 逐个删除
    deleted_count = 0
    for item_id, item_title in candidate_items:
        result = await _delete_single_item(
            account_id=rule.account_id,
            cookies_str=cookies_str,
            item_id=item_id,
        )
        if result["success"]:
            deleted_count += 1
            # 如果Cookie被更新了，使用最新的Cookie
            cookies_str = result.get("cookies_str", cookies_str)
            logger.info(
                f"删除规则[{rule.id}] 成功删除商品: [{item_id}] {item_title or ''}"
            )
            # 同步清理主项目数据库中的商品记录和关联卡券
            await _sync_delete_from_db(session, rule.owner_id, item_id)
        else:
            cookies_str = result.get("cookies_str", cookies_str)
            logger.warning(
                f"删除规则[{rule.id}] 删除商品[{item_id}]失败: {result['message']}"
            )
            # Session过期等严重错误，标记冷却并触发后台密码登录
            if result.get("session_expired") and result.get(
                "session_recovery_triggered"
            ):
                logger.warning(
                    f"删除规则[{rule.id}] 检测到Session过期，删除服务已触发后台密码登录，"
                    "停止本轮删除"
                )
                break
            if _is_session_expired_error(result["message"]):
                from common.utils.cookie_refresh import (
                    mark_account_session_expired,
                    trigger_password_login_async,
                )
                mark_account_session_expired(rule.account_id)
                trigger_password_login_async(rule.account_id)
                logger.warning(
                    f"删除规则[{rule.id}] 检测到Session过期，已标记冷却并触发后台密码登录，停止本轮删除"
                )
                break

        # 删除间隔，避免请求过于频繁
        await asyncio.sleep(2)

    # 更新规则计数
    rule.today_count += deleted_count
    rule.total_deleted_count = (rule.total_deleted_count or 0) + deleted_count
    rule.last_run_at = datetime.now(TZ_BEIJING)
    session.add(rule)
    await session.commit()

    logger.info(
        f"删除规则[{rule.id}] 本轮执行完成，删除 {deleted_count} 个商品，"
        f"今日累计 {rule.today_count}/{rule.daily_count}"
    )


async def _get_account_cookies(session: AsyncSession, account_id: str) -> str | None:
    """
    获取闲鱼账号的Cookie

    Args:
        session: 数据库会话
        account_id: 闲鱼账号ID

    Returns:
        Cookie字符串，不存在或为空返回None
    """
    from common.models.xy_account import XYAccount

    stmt = select(XYAccount.cookie).where(
        XYAccount.account_id == account_id,
        XYAccount.status == "active",
    )
    result = await session.execute(stmt)
    cookie = result.scalar_one_or_none()
    return cookie if cookie and cookie.strip() else None


async def _find_unreplied_items(
    session: AsyncSession,
    account_id: str,
    limit: int,
    min_publish_days: int = 7,
) -> list[tuple[str, str | None]]:
    """
    查找从未被回复过的闲鱼商品，按发布时间从早到晚排序

    逻辑：
    1. 从 xy_catalog_items 中查找该账号的所有商品
    2. 过滤掉在 xy_auto_reply_message_logs 中存在记录的商品（已有回复记录）
    3. 只保留发布时间超过 min_publish_days 天的商品
    4. 按创建时间（发布时间）升序排列

    Args:
        session: 数据库会话
        account_id: 闲鱼账号ID
        limit: 最多返回条数
        min_publish_days: 发布满多少天才能删除

    Returns:
        [(item_id, item_title), ...] 列表
    """
    from common.models.xy_account import XYAccount
    from common.models.xy_catalog_item import XYCatalogItem
    from common.models.auto_reply_message_log import XYAutoReplyMessageLog

    # 先获取账号的PK（xy_catalog_items.account_id 存的是PK）
    account_stmt = select(XYAccount.id).where(
        XYAccount.account_id == account_id
    )
    account_result = await session.execute(account_stmt)
    account_pk = account_result.scalar_one_or_none()
    if not account_pk:
        logger.warning(f"未找到闲鱼账号记录: {account_id}")
        return []

    # 子查询：该账号在消息日志中出现过的item_id集合
    replied_item_ids_subquery = (
        select(XYAutoReplyMessageLog.item_id)
        .where(
            XYAutoReplyMessageLog.account_id == account_id,
            XYAutoReplyMessageLog.item_id.isnot(None),
            XYAutoReplyMessageLog.item_id != "",
        )
        .distinct()
        .scalar_subquery()
    )

    # 计算截止日期：只删除发布时间早于此日期的商品
    cutoff_datetime = datetime.now(TZ_BEIJING) - timedelta(days=min_publish_days)

    # 主查询：该账号所有商品中，item_id 不在已回复集合中且发布满足天数的
    items_stmt = (
        select(XYCatalogItem.item_id, XYCatalogItem.title)
        .where(
            XYCatalogItem.account_pk == account_pk,
            XYCatalogItem.item_id.notin_(replied_item_ids_subquery),
            XYCatalogItem.created_at <= cutoff_datetime,
        )
        .order_by(XYCatalogItem.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(items_stmt)
    return [(row[0], row[1]) for row in result.all()]


async def _delete_single_item(
    account_id: str,
    cookies_str: str,
    item_id: str,
) -> dict:
    """
    调用mtop API删除单个商品

    Args:
        account_id: 闲鱼账号ID
        cookies_str: Cookie字符串
        item_id: 商品ID

    Returns:
        删除结果字典
    """
    from app.services.item_delete_api_service import delete_item_from_xianyu

    return await delete_item_from_xianyu(
        account_id=account_id,
        cookies_str=cookies_str,
        item_id=item_id,
    )


async def _sync_delete_from_db(
    session: AsyncSession,
    owner_id: int,
    item_id: str,
) -> None:
    """
    闲鱼商品删除成功后，同步清理主项目数据库中的关联数据

    包括：xy_catalog_items、xy_cards、xy_card_item_relations

    Args:
        session: 数据库会话
        owner_id: 所属用户ID
        item_id: 闲鱼商品ID
    """
    try:
        from app.services.item_delete_sync_service import sync_delete_item_from_db
        await sync_delete_item_from_db(session, owner_id, item_id)
    except Exception as e:
        logger.error(f"同步清理商品[{item_id}]数据库记录异常: {e}")


def _is_session_expired_error(message: str) -> bool:
    """判断是否为Session过期类严重错误"""
    if not message:
        return False
    keywords = ["SESSION_EXPIRED", "Session过期", "FAIL_SYS_SESSION_EXPIRED"]
    return any(kw in message for kw in keywords)
