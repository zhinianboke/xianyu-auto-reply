"""
返佣系统 - 发布规则定时任务

功能：
1. 每10分钟执行一次，遍历所有启用的发布规则
2. 判断今天是否已完成（today_count >= daily_count）
3. 未完成则从素材库取未发布的素材
4. 调用返佣专用发布器将素材发布到闲鱼
5. 发布成功后标记素材为已发布
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from uuid import uuid4

from loguru import logger
from sqlalchemy import desc, select

from common.utils.time_utils import get_beijing_now, get_beijing_now_naive

# 定时任务间隔（秒）：10分钟
PUBLISH_SCHEDULE_INTERVAL = 10 * 60

# 全局标记：是否正在执行
_publish_running = False
_publish_rule_lock = asyncio.Lock()
_running_rule_keys: set[str] = set()
_manual_execute_tasks: dict[str, dict] = {}
_manual_task_rule_map: dict[str, str] = {}

def _build_rule_execution_key(rule_id: int, user_id: int) -> str:
    return f"{user_id}:{rule_id}"

def _format_task_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""

def _get_beijing_today() -> date:
    return get_beijing_now().date()

def _manual_task_to_dict(task: dict) -> dict:
    return {
        "task_id": task["task_id"],
        "rule_id": task["rule_id"],
        "status": task["status"],
        "message": task.get("message", ""),
        "published_count": task.get("published_count", 0),
        "created_at": _format_task_datetime(task.get("created_at")),
        "started_at": _format_task_datetime(task.get("started_at")),
        "finished_at": _format_task_datetime(task.get("finished_at")),
        "updated_at": _format_task_datetime(task.get("updated_at")),
    }
def _update_manual_task(task_id: str, **kwargs) -> None:
    task = _manual_execute_tasks.get(task_id)
    if not task:
        return
    task.update(kwargs)
    task["updated_at"] = get_beijing_now_naive()
def _prune_manual_tasks() -> None:
    if len(_manual_execute_tasks) <= 200:
        return
    finished_tasks = [
        (task_id, task)
        for task_id, task in _manual_execute_tasks.items()
        if task.get("status") in {"success", "failed"}
    ]
    finished_tasks.sort(key=lambda item: item[1].get("updated_at") or datetime.min)
    for task_id, _ in finished_tasks[:-100]:
        _manual_execute_tasks.pop(task_id, None)

async def _acquire_rule_execution(rule_id: int, user_id: int, task_id: str | None = None) -> tuple[bool, str | None]:
    rule_key = _build_rule_execution_key(rule_id, user_id)
    async with _publish_rule_lock:
        if rule_key in _running_rule_keys:
            return False, _manual_task_rule_map.get(rule_key)
        _running_rule_keys.add(rule_key)
        if task_id:
            _manual_task_rule_map[rule_key] = task_id
        return True, None


async def _release_rule_execution(rule_id: int, user_id: int) -> None:
    rule_key = _build_rule_execution_key(rule_id, user_id)
    async with _publish_rule_lock:
        _running_rule_keys.discard(rule_key)
        _manual_task_rule_map.pop(rule_key, None)

def _generate_publish_trace_code() -> str:
    return uuid4().hex[:8].upper()

def _build_publish_title_with_trace(title: str | None, trace_code: str) -> str:
    base_title = (title or "好物推荐").strip() or "好物推荐"
    trace_prefix = f"【{trace_code}】"
    max_title_length = max(1, 200 - len(trace_prefix))
    return f"{trace_prefix}{base_title[:max_title_length]}"

async def _find_published_item_id_by_trace_code(
    user_id: int,
    account_id: str,
    trace_code: str,
) -> str | None:
    from common.db.session import async_session_maker
    from common.models.xy_account import XYAccount
    from common.models.xy_catalog_item import XYCatalogItem

    trace_keyword = f"【{trace_code}】"
    for attempt in range(3):
        async with async_session_maker() as lookup_session:
            stmt = (
                select(XYCatalogItem.item_id)
                .join(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
                .where(
                    XYAccount.owner_id == user_id,
                    XYAccount.account_id == account_id,
                    XYCatalogItem.title.like(f"%{trace_keyword}%"),
                )
                .order_by(
                    desc(XYCatalogItem.updated_at),
                    desc(XYCatalogItem.created_at),
                    desc(XYCatalogItem.id),
                )
                .limit(1)
            )
            result = await lookup_session.execute(stmt)
            item_id = result.scalars().first()
            if item_id:
                return str(item_id)
        if attempt < 2:
            await asyncio.sleep(2)
    return None

async def get_manual_execute_publish_rule_status(task_id: str, user_id: int) -> dict:
    task = _manual_execute_tasks.get(task_id)
    if not task or task.get("user_id") != user_id:
        return {"success": False, "message": "执行任务不存在或无权限查看"}
    return {"success": True, "data": _manual_task_to_dict(task)}

async def _run_manual_execute_publish_rule_task(task_id: str, rule_id: int, user_id: int) -> None:
    from common.db.session import async_session_maker
    from common.models.fy_publish_rule import FYPublishRule

    _update_manual_task(
        task_id,
        status="running",
        message="发布规则执行中",
        started_at=get_beijing_now_naive(),
    )

    try:
        # 用短会话加载规则信息，避免长时间持有数据库连接
        async with async_session_maker() as session:
            stmt = select(FYPublishRule).where(
                FYPublishRule.id == rule_id,
                FYPublishRule.owner_id == user_id,
            )
            result = await session.execute(stmt)
            rule = result.scalar_one_or_none()
            if not rule:
                _update_manual_task(
                    task_id,
                    status="failed",
                    message="规则不存在或无权限",
                    finished_at=get_beijing_now_naive(),
                )
                return
            rule_info = {
                "id": rule.id,
                "rule_name": rule.rule_name,
                "owner_id": rule.owner_id,
                "account_id": rule.account_id,
                "daily_count": rule.daily_count,
                "today_count": rule.today_count,
                "last_run_date": rule.last_run_date,
            }

        published = await _execute_single_publish_rule(rule_info, _get_beijing_today(), force=True, task_id=task_id)
        current_message = _manual_execute_tasks.get(task_id, {}).get("message", "")
        finish_message = current_message if "停止后续素材发布" in current_message else f"手动执行完成，成功发布{published}个商品"
        _update_manual_task(
            task_id,
            status="success",
            message=finish_message,
            published_count=published,
            finished_at=get_beijing_now_naive(),
        )
    except Exception as e:
        logger.error(f"手动执行发布规则[{rule_id}]异常: {e}")
        _update_manual_task(
            task_id,
            status="failed",
            message=f"执行失败: {str(e)}",
            finished_at=get_beijing_now_naive(),
        )
    finally:
        await _release_rule_execution(rule_id, user_id)
        _prune_manual_tasks()

async def run_publish_rule_scheduler():
    """
    发布规则定时任务主循环

    每10分钟执行一次发布规则检查和执行
    """
    logger.info("发布规则定时任务已启动，间隔: 10分钟")
    # 启动后等待60秒再首次执行
    await asyncio.sleep(60)

    while True:
        try:
            await _execute_all_publish_rules()
        except Exception as e:
            logger.error(f"发布规则定时任务执行异常: {e}")
        await asyncio.sleep(PUBLISH_SCHEDULE_INTERVAL)


async def manual_execute_publish_rule(rule_id: int, user_id: int) -> dict:
    """
    手动执行指定发布规则

    不受当日已完成限制，但固定只发布1个商品

    Args:
        rule_id: 规则ID
        user_id: 用户ID

    Returns:
        执行结果字典
    """
    from common.db.session import async_session_maker
    from common.models.fy_publish_rule import FYPublishRule

    async with async_session_maker() as session:
        stmt = select(FYPublishRule).where(
            FYPublishRule.id == rule_id,
            FYPublishRule.owner_id == user_id,
        )
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()
        if not rule:
            return {"success": False, "message": "规则不存在或无权限"}

    task_id = uuid4().hex
    acquired, existing_task_id = await _acquire_rule_execution(rule_id, user_id, task_id=task_id)
    if not acquired:
        if existing_task_id and existing_task_id in _manual_execute_tasks:
            existing_task = _manual_execute_tasks[existing_task_id]
            if existing_task.get("user_id") == user_id:
                return {
                    "success": True,
                    "message": "规则已在后台执行",
                    "data": _manual_task_to_dict(existing_task),
                }
        return {"success": False, "message": "规则正在执行中，请稍后重试"}

    now = get_beijing_now_naive()
    _manual_execute_tasks[task_id] = {
        "task_id": task_id,
        "rule_id": rule_id,
        "user_id": user_id,
        "status": "pending",
        "message": "任务已创建，等待执行",
        "published_count": 0,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "updated_at": now,
    }
    asyncio.create_task(_run_manual_execute_publish_rule_task(task_id=task_id, rule_id=rule_id, user_id=user_id))
    return {
        "success": True,
        "message": "已开始后台执行发布规则",
        "data": _manual_task_to_dict(_manual_execute_tasks[task_id]),
    }


async def _execute_all_publish_rules():
    """
    遍历所有启用的发布规则并执行

    跳过今天已完成的规则
    """
    global _publish_running
    if _publish_running:
        logger.info("发布规则定时任务正在执行中，跳过本次")
        return
    _publish_running = True

    try:
        from common.db.session import async_session_maker
        from common.models.fy_publish_rule import FYPublishRule

        # 用短会话加载所有启用的规则基本信息，避免长时间持有数据库连接
        async with async_session_maker() as session:
            stmt = select(FYPublishRule).where(FYPublishRule.enabled == True)
            result = await session.execute(stmt)
            rules = result.scalars().all()
            if not rules:
                logger.info("没有启用的发布规则，跳过")
                return
            rule_snapshots = [
                {
                    "id": r.id,
                    "rule_name": r.rule_name,
                    "owner_id": r.owner_id,
                    "account_id": r.account_id,
                    "daily_count": r.daily_count,
                    "today_count": r.today_count,
                    "last_run_date": r.last_run_date,
                }
                for r in rules
            ]

        today = _get_beijing_today()
        for rule_info in rule_snapshots:
            acquired, _ = await _acquire_rule_execution(rule_info["id"], rule_info["owner_id"])
            if not acquired:
                logger.info(f"发布规则[{rule_info['id']}]{rule_info['rule_name']}正在执行中，跳过本次")
                continue
            try:
                await _execute_single_publish_rule(rule_info, today)
            except Exception as e:
                logger.error(f"执行发布规则[{rule_info['id']}]{rule_info['rule_name']}异常: {e}")
            finally:
                await _release_rule_execution(rule_info["id"], rule_info["owner_id"])

    finally:
        _publish_running = False


async def _execute_single_publish_rule(
    rule_info: dict,
    today: date,
    force: bool = False,
    task_id: str | None = None,
):
    """
    执行单个发布规则

    Args:
        rule_info: 发布规则信息字典
        today: 今天日期
        force: 是否强制执行（手动触发时为True）
        task_id: 手动执行任务ID

    Returns:
        成功发布数量
    """
    from common.db.session import async_session_maker
    from common.models.fy_material import FYMaterial, PUBLISH_STATUS_UNPUBLISHED
    from app.services.publish_rule_persistence_service import (
        get_account_product_total_count,
        save_publish_failure,
        save_publish_rule_progress,
        save_publish_success,
    )

    rule_id = rule_info["id"]
    rule_name = rule_info["rule_name"]
    owner_id = rule_info["owner_id"]
    account_id = rule_info["account_id"]
    daily_count = rule_info["daily_count"]
    current_today_count = 0 if rule_info["last_run_date"] != today else (rule_info["today_count"] or 0)

    # 今天已完成（force模式跳过此检查）
    if not force and current_today_count >= daily_count:
        logger.info(f"发布规则[{rule_id}]{rule_name}今天已完成({current_today_count}/{daily_count})，跳过")
        return 0

    # 还需要发布多少条
    remaining = 1 if force else (daily_count - current_today_count)
    logger.info(f"执行发布规则[{rule_id}]{rule_name}，今天还需发布{remaining}条")

    # 用短会话获取未发布的素材，避免长时间持有数据库连接
    async with async_session_maker() as session:
        stmt = (
            select(FYMaterial)
            .where(
                FYMaterial.owner_id == owner_id,
                FYMaterial.account_id == account_id,
                FYMaterial.publish_status == PUBLISH_STATUS_UNPUBLISHED,
            )
            .order_by(FYMaterial.id.asc())
            .limit(remaining)
        )
        result = await session.execute(stmt)
        materials = result.scalars().all()
        if not materials:
            await save_publish_rule_progress(rule_id=rule_id, today=today, today_count=current_today_count)
            logger.info(f"发布规则[{rule_id}]没有待发布的素材")
            return 0
        # 提取素材信息到普通字典，避免会话关闭后无法访问ORM属性
        material_list = [
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "price": m.price,
                "stock": m.stock,
                "images": m.images,
            }
            for m in materials
        ]

    # 逐个发布（会话已关闭，不会因发布耗时导致数据库连接超时）
    published_count = 0
    for mat in material_list:
        total_product_count = await get_account_product_total_count(owner_id=owner_id, account_id=account_id)
        if total_product_count >= 300:
            limit_message = (
                f"账号[{account_id}]商品管理商品总数为{total_product_count}，已达到上限300，"
                f"取消本次发布任务并停止后续素材发布，已成功发布{published_count}个商品"
            )
            if task_id:
                _update_manual_task(task_id, message=limit_message, published_count=published_count)
            logger.warning(f"发布规则[{rule_id}]{rule_name}：{limit_message}")
            break
        try:
            publish_result = await _publish_material_to_xianyu(
                material=mat,
                account_id=account_id,
                user_id=owner_id,
            )
            if publish_result.get("success"):
                published_at = get_beijing_now_naive()
                current_today_count += 1
                await save_publish_success(
                    rule_id=rule_id,
                    material_id=mat["id"],
                    today=today,
                    today_count=current_today_count,
                    published_at=published_at,
                    published_item_id=publish_result.get("published_item_id"),
                    publish_random_str=publish_result.get("publish_random_str"),
                )
                published_count += 1
                if task_id:
                    _update_manual_task(task_id, message=f"发布规则执行中，已成功发布{published_count}个商品", published_count=published_count)
                logger.info(f"素材[{mat['id']}]{(mat['title'] or '')[:30]}发布成功")
            else:
                fail_message = publish_result.get("message", "")
                await save_publish_failure(material_id=mat["id"])
                logger.warning(f"素材[{mat['id']}]{(mat['title'] or '')[:30]}发布失败: {fail_message}")
                if any(keyword in fail_message for keyword in ("Cookie已失效", "未登录", "账号不存在或无权使用")):
                    if task_id:
                        _update_manual_task(task_id, message=f"账号[{account_id}]未登录，本轮停止后续素材发布，已成功发布{published_count}个商品", published_count=published_count)
                    logger.warning(f"发布规则[{rule_id}]{rule_name}账号[{account_id}]未登录，本轮停止后续素材发布，等待下次定时任务")
                    break
        except Exception as e:
            logger.error(f"素材[{mat['id']}]发布异常: {e}")
            raise
        await asyncio.sleep(5)

    await save_publish_rule_progress(rule_id=rule_id, today=today, today_count=current_today_count)

    logger.info(f"发布规则[{rule_id}]{rule_name}本次发布{published_count}条，今日合计{current_today_count}/{daily_count}")
    return published_count
async def _publish_material_to_xianyu(
    material: dict,
    account_id: str,
    user_id: int,
) -> dict:
    """
    通过返佣专用发布器直接将素材发布到闲鱼

    Args:
        material: 素材信息字典
        account_id: 闲鱼账号ID
        user_id: 用户ID

    Returns:
        是否发布成功
    """
    from common.db.session import async_session_maker
    from common.services.promotion_publish_execution_service import execute_single_publish

    # 解析素材图片
    images = []
    if material["images"]:
        try:
            parsed = json.loads(material["images"]) if isinstance(material["images"], str) else material["images"]
            if isinstance(parsed, list):
                images = [img for img in parsed if img]
        except (json.JSONDecodeError, TypeError):
            pass

    if not images:
        logger.warning(f"素材[{material['id']}]没有图片，跳过发布")
        return {"success": False, "message": "素材没有图片，跳过发布"}

    # 构建发布请求数据
    trace_code = _generate_publish_trace_code()
    # 标题截取前30字符作为闲鱼标题
    title = _build_publish_title_with_trace(material["title"], trace_code)
    # 描述：使用素材的description，如果没有则构建默认描述
    description = (material["description"] or "").removeprefix(material["title"] or "").lstrip()
    # 价格：使用素材的售价
    price = float(material["price"]) if material["price"] else 0.1
    stock = int(material["stock"]) if material["stock"] is not None else 999
    if stock <= 0:
        stock = 999

    payload = {
        "id": material["id"],
        "account_id": account_id,
        "title": title,
        "description": description,
        "price": price,
        "stock": stock,
        "images": images,
        "delivery_method": "express",
        "postage": 0,
        "condition": "全新",
    }

    try:
        async with async_session_maker() as publish_session:
            result = await execute_single_publish(
                session=publish_session,
                user_id=user_id,
                account_id=account_id,
                item_data=payload,
            )
        if result.get("success"):
            published_item_id = await _find_published_item_id_by_trace_code(
                user_id=user_id,
                account_id=account_id,
                trace_code=trace_code,
            )
            if not published_item_id:
                published_item_id = str(result.get("item_id") or "").strip() or None
                if published_item_id:
                    logger.warning(f"素材[{material['id']}]未通过追踪码匹配到发布商品，改用发布结果中的商品ID回写: {published_item_id}")
                else:
                    logger.warning(f"素材[{material['id']}]发布成功，但未匹配到发布后商品ID，已保留追踪码: {trace_code}")
            logger.info(f"素材[{material['id']}]发布到闲鱼成功: {result.get('message', '')}")
            return {
                "success": True,
                "published_item_id": published_item_id or "",
                "publish_random_str": trace_code,
                "message": result.get("message", ""),
            }
        message = result.get("message", "未知错误")
        logger.warning(f"素材[{material['id']}]发布到闲鱼失败: {message}")
        return {"success": False, "message": message}
    except Exception as e:
        logger.error(f"素材[{material['id']}]返佣专用发布器执行异常: {e}")
        return {"success": False, "message": str(e)}
