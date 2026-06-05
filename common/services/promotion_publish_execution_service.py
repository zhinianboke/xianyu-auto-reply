"""
返佣系统专用商品发布执行服务

功能：
1. 统一执行返佣系统单品发布业务编排
2. 使用返佣系统专用闲鱼发布服务完成发布
3. 保留原公共发布执行服务不受影响
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from common.services.item_service import ItemService
from common.services.publish_address_service import PublishAddressService
from common.services.publish_log_service import PublishLogService
from common.services.promotion_xianyu_publish_service import publish_single_item


def _resolve_required_title_keyword(published_title: str | None) -> str | None:
    """根据发布标题提取用于同步命中的关键字。"""
    normalized_title = str(published_title or "").strip()
    if not normalized_title:
        return None

    trace_match = re.match(r"^(【[^】]+】)", normalized_title)
    if trace_match:
        return trace_match.group(1)

    return normalized_title


async def _get_account(session: AsyncSession, account_id: str, user_id: int) -> Optional[XYAccount]:
    """获取用户可用的闲鱼账号。"""
    stmt = (
        select(XYAccount)
        .where(
            XYAccount.account_id == account_id,
            XYAccount.owner_id == user_id,
        )
        .order_by(desc(XYAccount.id))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def _sync_account_items_after_publish(
    session: AsyncSession,
    account_id: str,
    account: XYAccount,
    published_title: str | None = None,
) -> Dict[str, Any]:
    """发布成功后自动同步账号商品。"""
    item_svc = ItemService(session)
    required_title_keyword = _resolve_required_title_keyword(published_title)
    try:
        sync_result = await item_svc.fetch_all_items_from_account(
            account=account,
            stop_when_page_all_existing=True,
            required_title_keyword=required_title_keyword,
        )
        sync_status = "success" if sync_result.get("success") else "failed"
        sync_total_count = int(sync_result.get("total_count") or 0)
        sync_saved_count = int(sync_result.get("saved_count") or 0)
        if sync_status == "success":
            sync_message = f"已自动获取 {sync_total_count} 个商品，入库 {sync_saved_count} 个商品"
            logger.info(
                f"账号 {account_id} 发布后自动获取商品完成：共 {sync_total_count} 件，保存 {sync_saved_count} 件"
            )
        else:
            sync_message = f"自动获取商品失败：{sync_result.get('message') or '未知错误'}"
            logger.warning(
                f"账号 {account_id} 发布后自动获取商品失败，不影响后续发布：{sync_result.get('message', '未知错误')}"
            )
        return {
            "sync_status": sync_status,
            "sync_message": sync_message,
            "sync_total_count": sync_total_count,
            "sync_saved_count": sync_saved_count,
        }
    except Exception as sync_exc:
        logger.warning(
            f"账号 {account_id} 发布后自动获取商品异常，不影响后续发布：{sync_exc}"
        )
        return {
            "sync_status": "failed",
            "sync_message": f"自动获取商品异常：{sync_exc}",
            "sync_total_count": 0,
            "sync_saved_count": 0,
        }


async def execute_single_publish(
    session: AsyncSession,
    user_id: int,
    account_id: str,
    item_data: dict,
    static_root: str | Path | None = None,
) -> Dict[str, Any]:
    """执行返佣系统单品发布并返回统一结果。"""
    log_svc = PublishLogService(session)
    address_svc = PublishAddressService(session)

    account = await _get_account(session=session, account_id=account_id, user_id=user_id)
    cookies_str = account.cookie if account and account.cookie else ""
    if not cookies_str:
        log = await log_svc.create_log(
            user_id=user_id,
            account_id=account_id,
            title=item_data.get("title", ""),
            description=item_data.get("description", ""),
            price=str(item_data.get("price", "")),
            material_id=item_data.get("id"),
            status="failed",
            error_message="账号不存在或无权使用",
        )
        return {"success": False, "message": "账号不存在或无权使用", "log_id": log.id}

    try:
        resolved_address = await address_svc.resolve_publish_address(account_id, item_data)
    except ValueError as exc:
        log = await log_svc.create_log(
            user_id=user_id,
            account_id=account_id,
            title=item_data.get("title", ""),
            description=item_data.get("description", ""),
            price=str(item_data.get("price", "")),
            material_id=item_data.get("id"),
            status="failed",
            error_message=str(exc),
        )
        return {"success": False, "message": str(exc), "log_id": log.id}

    publish_item_data = resolved_address.apply_to_item_data(item_data)
    log = await log_svc.create_log(
        user_id=user_id,
        account_id=account_id,
        title=item_data.get("title", ""),
        description=item_data.get("description", ""),
        price=str(item_data.get("price", "")),
        material_id=item_data.get("id"),
        status="publishing",
        **resolved_address.to_log_fields(),
    )

    result = None
    pub_error = None
    try:
        result = await publish_single_item(
            item_data=publish_item_data,
            cookie=cookies_str,
            static_root=static_root,
        )
    except Exception as exc:
        pub_error = exc
        logger.error(f"单品发布异常: {exc}")

    from common.db.session import async_session_maker

    try:
        async with async_session_maker() as fresh_session:
            fresh_log_svc = PublishLogService(fresh_session)
            if pub_error:
                await fresh_log_svc.update_log(
                    log_id=log.id,
                    status="failed",
                    error_message=str(pub_error),
                )
                return {"success": False, "message": f"发布异常: {str(pub_error)}", "log_id": log.id}

            status = "success" if result.get("success") else "failed"
            await fresh_log_svc.update_log(
                log_id=log.id,
                status=status,
                item_url=result.get("item_url"),
                item_id=result.get("item_id"),
                error_message=None if result.get("success") else result.get("message"),
            )
    except Exception as db_err:
        logger.error(f"更新发布日志失败: {db_err}")

    if pub_error:
        return {"success": False, "message": f"发布异常: {str(pub_error)}", "log_id": log.id}

    publish_success = result.get("success", False)
    sync_info = {
        "sync_status": "skipped",
        "sync_message": "发布未成功，未触发自动获取商品",
        "sync_total_count": 0,
        "sync_saved_count": 0,
    }
    if publish_success and account is not None:
        sync_info = await _sync_account_items_after_publish(
            session=session,
            account_id=account_id,
            account=account,
            published_title=item_data.get("title"),
        )

    message = result.get("message") or ("商品发布成功" if publish_success else "发布失败")
    if publish_success and sync_info.get("sync_message"):
        message = f"{message}，{sync_info['sync_message']}"

    return {
        "success": publish_success,
        "message": message,
        "item_url": result.get("item_url"),
        "item_id": result.get("item_id"),
        "log_id": log.id,
        **sync_info,
    }
