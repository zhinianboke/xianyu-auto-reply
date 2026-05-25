"""
返佣系统 - 删除规则服务

功能：
1. 删除规则的增删改查
2. 分页查询当前用户的规则列表
3. 启用/禁用规则
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def list_rules(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    is_admin: bool = False,
) -> dict:
    """
    分页查询删除规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        page: 页码
        page_size: 每页条数
        is_admin: 是否管理员（管理员查看所有用户数据）

    Returns:
        包含规则列表和总数的字典
    """
    from common.models.fy_delete_rule import FYDeleteRule

    # 基础条件：管理员不过滤owner_id
    conditions = [] if is_admin else [FYDeleteRule.owner_id == user_id]

    # 总数
    count_stmt = select(func.count()).select_from(FYDeleteRule).where(*conditions)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页列表
    offset = (page - 1) * page_size
    list_stmt = (
        select(FYDeleteRule)
        .where(*conditions)
        .order_by(FYDeleteRule.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(list_stmt)
    rules = result.scalars().all()

    return {
        "success": True,
        "data": {
            "list": [_rule_to_dict(r) for r in rules],
            "total": total,
        },
    }


async def create_rule(
    session: AsyncSession,
    user_id: int,
    data: dict,
) -> dict:
    """
    新建删除规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        data: 规则数据

    Returns:
        创建结果
    """
    from common.models.fy_delete_rule import FYDeleteRule
    from app.services.product_rule_service import validate_xy_account

    account_id = (data.get("account_id") or "").strip()
    if not account_id:
        return {"success": False, "message": "请选择闲鱼账号"}
    is_valid, error_message = await validate_xy_account(session, user_id, account_id)
    if not is_valid:
        return {"success": False, "message": error_message}

    existing_rule = await _get_user_rule_by_account(session, user_id, account_id)
    if existing_rule:
        return {"success": False, "message": "同一闲鱼账号只允许创建一条删除规则，请直接编辑现有规则"}

    rule = FYDeleteRule(
        owner_id=user_id,
        rule_name=(data.get("rule_name") or "").strip() or "未命名删除规则",
        account_id=account_id,
        daily_count=max(1, int(data.get("daily_count") or 5)),
        min_publish_days=max(1, int(data.get("min_publish_days") or 7)),
        enabled=data.get("enabled", True),
        remark=(data.get("remark") or "").strip() or None,
    )
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_delete_rule_account_duplicate_error(exc):
            return {"success": False, "message": "同一闲鱼账号只允许创建一条删除规则，请直接编辑现有规则"}
        raise
    await session.refresh(rule)
    logger.info(f"用户{user_id}创建删除规则: id={rule.id}, name={rule.rule_name}")
    return {
        "success": True,
        "data": _rule_to_dict(rule),
    }


async def update_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
    data: dict,
) -> dict:
    """
    更新删除规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        rule_id: 规则ID
        data: 更新数据

    Returns:
        更新结果
    """
    from app.services.product_rule_service import validate_xy_account

    rule = await _get_user_rule(session, user_id, rule_id)
    if not rule:
        return {"success": False, "message": "规则不存在或无权限"}

    if "rule_name" in data:
        rule.rule_name = (data["rule_name"] or "").strip() or "未命名删除规则"
    if "account_id" in data:
        account_id = (data["account_id"] or "").strip()
        if not account_id:
            return {"success": False, "message": "请选择闲鱼账号"}
        is_valid, error_message = await validate_xy_account(session, user_id, account_id)
        if not is_valid:
            return {"success": False, "message": error_message}
        existing_rule = await _get_user_rule_by_account(session, user_id, account_id, exclude_rule_id=rule.id)
        if existing_rule:
            return {"success": False, "message": "同一闲鱼账号只允许创建一条删除规则，请直接编辑现有规则"}
        rule.account_id = account_id
    if "daily_count" in data:
        rule.daily_count = max(1, int(data["daily_count"] or 5))
    if "min_publish_days" in data:
        rule.min_publish_days = max(1, int(data["min_publish_days"] or 7))
    if "enabled" in data:
        rule.enabled = bool(data["enabled"])
    if "remark" in data:
        rule.remark = (data["remark"] or "").strip() or None

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_delete_rule_account_duplicate_error(exc):
            return {"success": False, "message": "同一闲鱼账号只允许创建一条删除规则，请直接编辑现有规则"}
        raise
    await session.refresh(rule)
    logger.info(f"用户{user_id}更新删除规则: id={rule.id}")
    return {
        "success": True,
        "data": _rule_to_dict(rule),
    }


async def delete_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
) -> dict:
    """
    删除删除规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        rule_id: 规则ID

    Returns:
        删除结果
    """
    rule = await _get_user_rule(session, user_id, rule_id)
    if not rule:
        return {"success": False, "message": "规则不存在或无权限"}

    await session.delete(rule)
    await session.commit()
    logger.info(f"用户{user_id}删除删除规则: id={rule_id}")
    return {"success": True, "message": "删除成功"}


async def toggle_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
    enabled: bool,
) -> dict:
    """
    启用/禁用删除规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        rule_id: 规则ID
        enabled: 是否启用

    Returns:
        操作结果
    """
    rule = await _get_user_rule(session, user_id, rule_id)
    if not rule:
        return {"success": False, "message": "规则不存在或无权限"}

    rule.enabled = enabled
    await session.commit()
    status = "启用" if enabled else "禁用"
    logger.info(f"用户{user_id}{status}删除规则: id={rule_id}")
    return {"success": True, "message": f"已{status}"}


async def _get_user_rule(session: AsyncSession, user_id: int, rule_id: int):
    """获取用户的指定删除规则"""
    from common.models.fy_delete_rule import FYDeleteRule

    stmt = select(FYDeleteRule).where(
        FYDeleteRule.id == rule_id,
        FYDeleteRule.owner_id == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_user_rule_by_account(
    session: AsyncSession,
    user_id: int,
    account_id: str,
    exclude_rule_id: int | None = None,
):
    """按账号获取用户的删除规则，用于同账号唯一校验。"""
    from common.models.fy_delete_rule import FYDeleteRule

    stmt = select(FYDeleteRule).where(
        FYDeleteRule.owner_id == user_id,
        FYDeleteRule.account_id == account_id,
    )
    if exclude_rule_id is not None:
        stmt = stmt.where(FYDeleteRule.id != exclude_rule_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _is_delete_rule_account_duplicate_error(exc: IntegrityError) -> bool:
    """判断是否为删除规则同账号唯一约束冲突。"""
    message = str(getattr(exc, "orig", exc) or "")
    return "uq_fy_delete_rules_owner_account" in message or "Duplicate entry" in message


def _rule_to_dict(rule) -> dict:
    """将删除规则ORM对象转为字典"""
    return {
        "id": rule.id,
        "owner_id": rule.owner_id,
        "rule_name": rule.rule_name,
        "account_id": rule.account_id or "",
        "daily_count": rule.daily_count,
        "min_publish_days": rule.min_publish_days or 7,
        "total_deleted_count": rule.total_deleted_count or 0,
        "enabled": rule.enabled,
        "remark": rule.remark or "",
        "last_run_date": str(rule.last_run_date) if rule.last_run_date else "",
        "today_count": rule.today_count or 0,
        "last_run_at": rule.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if rule.last_run_at else "",
        "created_at": rule.created_at.strftime("%Y-%m-%d %H:%M:%S") if rule.created_at else "",
        "updated_at": rule.updated_at.strftime("%Y-%m-%d %H:%M:%S") if rule.updated_at else "",
    }
