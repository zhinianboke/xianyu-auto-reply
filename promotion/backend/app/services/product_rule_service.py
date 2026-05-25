"""
返佣系统 - 选品规则服务

功能：
1. 选品规则的增删改查
2. 分页查询当前用户的规则列表
3. 启用/禁用规则
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import func, or_, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession


async def validate_xy_account(session: AsyncSession, user_id: int, account_id: str) -> tuple[bool, str]:
    from common.models.xy_account import XYAccount

    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return False, "请选择闲鱼账号"
    stmt = select(XYAccount).where(
        XYAccount.account_id == normalized_account_id,
        XYAccount.owner_id == user_id,
    ).order_by(XYAccount.id.desc()).limit(1)
    result = await session.execute(stmt)
    account = result.scalars().first()
    if not account:
        return False, "所选闲鱼账号不存在或不属于当前用户"
    if account.status != "active":
        return False, "所选闲鱼账号未启用，请先启用账号后再保存规则"
    return True, ""


async def list_rules(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    is_admin: bool = False,
) -> dict:
    """
    分页查询选品规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        page: 页码
        page_size: 每页条数
        is_admin: 是否管理员（管理员查看所有用户数据）

    Returns:
        包含规则列表和总数的字典
    """
    from common.models.fy_product_rule import FYProductRule

    # 基础条件：管理员不过滤owner_id
    conditions = [] if is_admin else [FYProductRule.owner_id == user_id]

    # 总数
    count_stmt = select(func.count()).select_from(FYProductRule).where(*conditions)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页列表
    offset = (page - 1) * page_size
    list_stmt = (
        select(FYProductRule)
        .where(*conditions)
        .order_by(FYProductRule.id.desc())
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
    新建选品规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        data: 规则数据

    Returns:
        创建结果
    """
    from common.models.fy_product_rule import FYProductRule

    account_id = (data.get("account_id") or "").strip()
    is_valid, error_message = await validate_xy_account(session, user_id, account_id)
    if not is_valid:
        return {"success": False, "message": error_message}

    # 校验：类目和关键词至少填一个
    cat = (data.get("cat") or "").strip()
    keyword = (data.get("keyword") or "").strip()
    if not cat and not keyword:
        return {"success": False, "message": "商品类目和关键词至少填写一项"}

    rule = FYProductRule(
        owner_id=user_id,
        account_id=account_id,
        rule_name=(data.get("rule_name") or "").strip() or "未命名规则",
        cat=cat or None,
        cat_name=(data.get("cat_name") or "").strip() or None,
        keyword=keyword or None,
        sort=(data.get("sort") or "default").strip(),
        daily_count=max(1, int(data.get("daily_count") or 10)),
        enabled=data.get("enabled", True),
        remark=(data.get("remark") or "").strip() or None,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    logger.info(f"用户{user_id}创建选品规则: id={rule.id}, name={rule.rule_name}")
    return {"success": True, "data": _rule_to_dict(rule)}


async def update_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
    data: dict,
) -> dict:
    """
    更新选品规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        rule_id: 规则ID
        data: 更新数据

    Returns:
        更新结果
    """
    from common.models.fy_material import PUBLISH_STATUS_PUBLISHED, FYMaterial
    from common.models.fy_product_rule import FYProductRule

    rule = await _get_user_rule(session, user_id, rule_id)
    if not rule:
        return {"success": False, "message": "规则不存在或无权限"}

    previous_account_id = str(rule.account_id or "").strip()
    account_id = (data.get("account_id") or "").strip() if "account_id" in data else str(rule.account_id or "").strip()
    is_valid, error_message = await validate_xy_account(session, user_id, account_id)
    if not is_valid:
        return {"success": False, "message": error_message}

    # 校验：类目和关键词至少填一个
    cat = (data.get("cat") or "").strip() if "cat" in data else (rule.cat or "")
    keyword = (data.get("keyword") or "").strip() if "keyword" in data else (rule.keyword or "")
    if not cat and not keyword:
        return {"success": False, "message": "商品类目和关键词至少填写一项"}

    # 更新字段
    if "account_id" in data:
        rule.account_id = account_id
        if account_id != previous_account_id:
            await session.execute(
                update(FYMaterial)
                .where(
                    FYMaterial.owner_id == user_id,
                    FYMaterial.rule_id == rule.id,
                    FYMaterial.publish_status != PUBLISH_STATUS_PUBLISHED,
                )
                .values(account_id=account_id)
            )
    if "rule_name" in data:
        rule.rule_name = (data["rule_name"] or "").strip() or "未命名规则"
    if "cat" in data:
        rule.cat = cat or None
    if "cat_name" in data:
        rule.cat_name = (data["cat_name"] or "").strip() or None
    if "keyword" in data:
        rule.keyword = keyword or None
    if "sort" in data:
        rule.sort = (data["sort"] or "default").strip()
    if "daily_count" in data:
        rule.daily_count = max(1, int(data["daily_count"] or 10))
    if "enabled" in data:
        rule.enabled = bool(data["enabled"])
    if "remark" in data:
        rule.remark = (data["remark"] or "").strip() or None

    await session.commit()
    await session.refresh(rule)
    logger.info(f"用户{user_id}更新选品规则: id={rule.id}")
    return {"success": True, "data": _rule_to_dict(rule)}


async def delete_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
) -> dict:
    """
    删除选品规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        rule_id: 规则ID

    Returns:
        删除结果
    """
    from common.models.fy_product_rule import FYProductRule

    rule = await _get_user_rule(session, user_id, rule_id)
    if not rule:
        return {"success": False, "message": "规则不存在或无权限"}

    await session.delete(rule)
    await session.commit()
    logger.info(f"用户{user_id}删除选品规则: id={rule_id}")
    return {"success": True, "message": "删除成功"}


async def toggle_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
    enabled: bool,
) -> dict:
    """
    启用/禁用选品规则

    Args:
        session: 数据库会话
        user_id: 用户ID
        rule_id: 规则ID
        enabled: 是否启用

    Returns:
        操作结果
    """
    from common.models.fy_product_rule import FYProductRule

    rule = await _get_user_rule(session, user_id, rule_id)
    if not rule:
        return {"success": False, "message": "规则不存在或无权限"}

    rule.enabled = enabled
    await session.commit()
    status = "启用" if enabled else "禁用"
    logger.info(f"用户{user_id}{status}选品规则: id={rule_id}")
    return {"success": True, "message": f"已{status}"}


async def _get_user_rule(session: AsyncSession, user_id: int, rule_id: int):
    """获取用户的指定规则"""
    from common.models.fy_product_rule import FYProductRule

    stmt = select(FYProductRule).where(
        FYProductRule.id == rule_id,
        FYProductRule.owner_id == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _build_rule_sync_key(rule) -> tuple:
    return (
        str(rule.rule_name or "").strip(),
        str(rule.cat or "").strip(),
        str(rule.cat_name or "").strip(),
        str(rule.keyword or "").strip(),
        str(rule.sort or "default").strip(),
        int(rule.daily_count or 0),
        bool(rule.enabled),
        str(rule.remark or "").strip(),
    )


async def sync_product_rules_to_publish_accounts(
    session: AsyncSession,
    user_id: int | None = None,
    target_account_id: str | None = None,
) -> int:
    from common.models.fy_product_rule import FYProductRule
    from common.models.fy_publish_rule import FYPublishRule

    publish_stmt = select(FYPublishRule.owner_id, FYPublishRule.account_id, FYPublishRule.id).where(
        FYPublishRule.account_id.is_not(None),
        FYPublishRule.account_id != "",
    )
    if user_id is not None:
        publish_stmt = publish_stmt.where(FYPublishRule.owner_id == user_id)
    if target_account_id:
        publish_stmt = publish_stmt.where(FYPublishRule.account_id == target_account_id)
    publish_stmt = publish_stmt.order_by(FYPublishRule.owner_id.asc(), FYPublishRule.id.asc())
    publish_result = await session.execute(publish_stmt)
    publish_rows = publish_result.all()
    if not publish_rows:
        return 0

    accounts_by_owner: dict[int, list[str]] = {}
    for owner_id_value, account_id_value, _ in publish_rows:
        normalized_account_id = str(account_id_value or "").strip()
        if not normalized_account_id:
            continue
        owner_accounts = accounts_by_owner.setdefault(int(owner_id_value), [])
        if normalized_account_id not in owner_accounts:
            owner_accounts.append(normalized_account_id)

    affected_count = 0
    for owner_id_value, account_ids in accounts_by_owner.items():
        rules_result = await session.execute(
            select(FYProductRule).where(FYProductRule.owner_id == owner_id_value).order_by(FYProductRule.id.asc())
        )
        rules = rules_result.scalars().all()
        if not rules:
            continue

        legacy_rules = [rule for rule in rules if not str(rule.account_id or "").strip()]
        if legacy_rules:
            primary_account_id = account_ids[0]
            for rule in legacy_rules:
                if str(rule.account_id or "").strip() != primary_account_id:
                    rule.account_id = primary_account_id
                    affected_count += 1

        if target_account_id:
            source_rules = [rule for rule in rules if str(rule.account_id or "").strip() != target_account_id]
        else:
            source_rules = legacy_rules
        if not source_rules:
            continue

        template_rules: dict[tuple, object] = {}
        for rule in source_rules:
            signature = _build_rule_sync_key(rule)
            if signature not in template_rules:
                template_rules[signature] = rule

        existing_by_account: dict[str, set[tuple]] = {}
        for rule in rules:
            normalized_account_id = str(rule.account_id or "").strip()
            if not normalized_account_id:
                continue
            existing_by_account.setdefault(normalized_account_id, set()).add(_build_rule_sync_key(rule))

        for account_id_value in account_ids:
            account_signatures = existing_by_account.setdefault(account_id_value, set())
            for signature, template_rule in template_rules.items():
                if signature in account_signatures:
                    continue
                new_rule = FYProductRule(
                    owner_id=owner_id_value,
                    account_id=account_id_value,
                    rule_name=template_rule.rule_name,
                    cat=template_rule.cat,
                    cat_name=template_rule.cat_name,
                    keyword=template_rule.keyword,
                    sort=template_rule.sort,
                    daily_count=template_rule.daily_count,
                    enabled=template_rule.enabled,
                    remark=template_rule.remark,
                    today_count=0,
                    last_run_at=None,
                    last_run_date=None,
                )
                session.add(new_rule)
                account_signatures.add(signature)
                affected_count += 1

    if affected_count > 0:
        await session.commit()
    return affected_count


async def sync_material_accounts_from_product_rules(
    session: AsyncSession,
    user_id: int | None = None,
    target_account_id: str | None = None,
) -> int:
    from common.models.fy_material import FYMaterial
    from common.models.fy_product_rule import FYProductRule

    stmt = (
        select(FYMaterial, FYProductRule.account_id)
        .join(FYProductRule, FYMaterial.rule_id == FYProductRule.id)
        .where(
            or_(FYMaterial.account_id.is_(None), FYMaterial.account_id == ""),
            FYProductRule.account_id.is_not(None),
            FYProductRule.account_id != "",
        )
    )
    if user_id is not None:
        stmt = stmt.where(FYMaterial.owner_id == user_id)
    if target_account_id:
        stmt = stmt.where(FYProductRule.account_id == target_account_id)
    result = await session.execute(stmt)
    rows = result.all()

    affected_count = 0
    for material, account_id_value in rows:
        normalized_account_id = str(account_id_value or "").strip()
        if not normalized_account_id:
            continue
        material.account_id = normalized_account_id
        affected_count += 1

    if affected_count > 0:
        await session.commit()
    return affected_count


def _rule_to_dict(rule) -> dict:
    """将规则ORM对象转为字典"""
    return {
        "id": rule.id,
        "owner_id": rule.owner_id,
        "account_id": rule.account_id or "",
        "rule_name": rule.rule_name,
        "cat": rule.cat or "",
        "cat_name": rule.cat_name or "",
        "keyword": rule.keyword or "",
        "sort": rule.sort or "default",
        "daily_count": rule.daily_count,
        "total_selected_count": rule.total_selected_count or 0,
        "enabled": rule.enabled,
        "remark": rule.remark or "",
        "last_run_date": str(rule.last_run_date) if rule.last_run_date else "",
        "today_count": rule.today_count or 0,
        "last_run_at": rule.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if rule.last_run_at else "",
        "created_at": rule.created_at.strftime("%Y-%m-%d %H:%M:%S") if rule.created_at else "",
        "updated_at": rule.updated_at.strftime("%Y-%m-%d %H:%M:%S") if rule.updated_at else "",
    }
