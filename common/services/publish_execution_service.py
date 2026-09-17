"""
公共商品发布执行服务

功能：
1. 统一执行单品发布的业务编排
2. 在发布前处理地址解析和发布日志
3. 在发布成功后自动同步账号商品
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.services.item_service import ItemService
from common.services.publish_address_service import PublishAddressService
from common.services.publish_log_service import PublishLogService
from common.services.xianyu_publish_service import (
    detect_publish_account_capability,
    ensure_publish_capability_reliable,
    publish_personal_single_item,
    publish_single_item,
)

PERSONAL_SELLER_DEFAULT_STOCK = 1

# 发布成功后闲鱼平台商品列表存在索引延迟，立即拉取常常取不到刚发布的商品，
# 因此同步前固定等待若干秒，给平台留出收录时间。
SYNC_AFTER_PUBLISH_DELAY_SECONDS = 2


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
) -> Dict[str, Any]:
    """发布成功后自动同步账号商品。"""
    item_svc = ItemService(session)
    # 平台商品列表有索引延迟，先等待再拉取，避免刚发布的商品同步不到
    if SYNC_AFTER_PUBLISH_DELAY_SECONDS > 0:
        logger.info(
            f"账号 {account_id} 发布成功，等待 {SYNC_AFTER_PUBLISH_DELAY_SECONDS} 秒后再自动获取商品"
        )
        await asyncio.sleep(SYNC_AFTER_PUBLISH_DELAY_SECONDS)
    try:
        sync_result = await item_svc.fetch_all_items_from_account(account=account)
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
    publish_request_id: str | None = None,
    source_event_id: int | None = None,
) -> Dict[str, Any]:
    """执行单品发布并返回统一结果。"""
    log_svc = PublishLogService(session)
    address_svc = PublishAddressService(session)

    # 自动续售发布是不可回滚的外部副作用。已有成功结果直接复用，
    # 进行中或未知结果不得再次调用平台接口。
    existing_log = None
    if publish_request_id:
        existing_log = await log_svc.get_by_request_id(publish_request_id)
        if existing_log:
            if existing_log.status == "success" and existing_log.item_id:
                return {
                    "success": True,
                    "message": "发布请求已完成，复用已有结果",
                    "item_id": existing_log.item_id,
                    "item_url": existing_log.item_url,
                    "log_id": existing_log.id,
                    "idempotent_reused": True,
                }
            if existing_log.status in {"pending", "publishing", "unknown"}:
                return {
                    "success": False,
                    "unknown": True,
                    "message": "发布请求已有记录，结果需要对账后再处理",
                    "item_id": existing_log.item_id,
                    "item_url": existing_log.item_url,
                    "log_id": existing_log.id,
                }

    # 单品发布严格使用前端选择的账号；启用状态只控制自动任务，不限制手动发布。
    account = await _get_account(session=session, account_id=account_id, user_id=user_id)
    cookies_str = account.cookie if account and account.cookie else ""
    if not account or not cookies_str.strip():
        error_message = (
            "选择的闲鱼账号不存在或无权使用"
            if not account
            else "选择的闲鱼账号缺少Cookie，请重新登录账号"
        )
        if existing_log and existing_log.status == "failed":
            existing_log.error_message = error_message
            await session.commit()
            log = existing_log
        else:
            log = await log_svc.create_log(
                user_id=user_id,
                account_id=account_id,
                title=item_data.get("title", ""),
                description=item_data.get("description", ""),
                price=str(item_data.get("price", "")),
                material_id=item_data.get("id"),
                publish_request_id=publish_request_id,
                source_event_id=source_event_id,
                status="failed",
                error_message=error_message,
            )
        return {
            "success": False,
            "message": error_message,
            "log_id": log.id,
        }

    try:
        resolved_address = await address_svc.resolve_publish_address(account_id, item_data)
    except ValueError as exc:
        if existing_log and existing_log.status == "failed":
            existing_log.error_message = str(exc)
            await session.commit()
            log = existing_log
        else:
            log = await log_svc.create_log(
                user_id=user_id,
                account_id=account_id,
                title=item_data.get("title", ""),
                description=item_data.get("description", ""),
                price=str(item_data.get("price", "")),
                material_id=item_data.get("id"),
                publish_request_id=publish_request_id,
                source_event_id=source_event_id,
                status="failed",
                error_message=str(exc),
            )
        return {"success": False, "message": str(exc), "log_id": log.id}

    publish_item_data = resolved_address.apply_to_item_data(item_data)
    if existing_log and existing_log.status == "failed":
        # 明确失败未产生平台副作用，可安全复用同一幂等日志重试。
        existing_log.status = "publishing"
        existing_log.error_message = None
        existing_log.item_id = None
        existing_log.item_url = None
        await session.commit()
        log = existing_log
    else:
        try:
            log = await log_svc.create_log(
                user_id=user_id,
                account_id=account_id,
                title=item_data.get("title", ""),
                description=item_data.get("description", ""),
                price=str(item_data.get("price", "")),
                material_id=item_data.get("id"),
                status="publishing",
                publish_request_id=publish_request_id,
                source_event_id=source_event_id,
                **resolved_address.to_log_fields(),
            )
        except IntegrityError:
            # 并发调用同一请求号时，唯一约束只允许一个日志获胜；
            # 另一方必须读取已有状态，不能继续调用平台接口。
            await session.rollback()
            existing_log = await log_svc.get_by_request_id(publish_request_id or "")
            if existing_log:
                return {
                    "success": existing_log.status == "success" and bool(existing_log.item_id),
                    "unknown": existing_log.status != "failed",
                    "message": "发布请求已有记录，结果需要对账后再处理",
                    "item_id": existing_log.item_id,
                    "log_id": existing_log.id,
                }
            raise

    result = None
    pub_error = None
    publish_unknown = False
    publish_call_started = False
    refreshed_cookie: str | None = None
    try:
        capability = await detect_publish_account_capability(
            cookie=cookies_str,
            account_id=account.account_id,
            owner_id=user_id,
        )
        cookies_str = capability.get("cookies_str") or cookies_str
        # 鱼小铺账号必须走鱼小铺接口：判定不可信时报错不发布，不允许回落个人版发布
        capability = ensure_publish_capability_reliable(capability)
        if not capability.get("success"):
            result = capability
        elif capability.get("is_fish_shop"):
            # 鱼小铺账号继续使用已验证稳定的原发布逻辑，不改变任何载荷与接口。
            publish_call_started = True
            result = await publish_single_item(
                item_data=publish_item_data,
                cookie=cookies_str,
                account_id=account.account_id,
                owner_id=user_id,
                static_root=static_root,
            )
        else:
            # 普通卖家单品发布不提供视频能力，后端兜底丢弃绕过前端提交的视频。
            personal_item_data = {
                **publish_item_data,
                "videos": [],
                "quantity": PERSONAL_SELLER_DEFAULT_STOCK,
                "stock": PERSONAL_SELLER_DEFAULT_STOCK,
            }
            publish_call_started = True
            result = await publish_personal_single_item(
                item_data=personal_item_data,
                cookie=cookies_str,
                account_id=account.account_id,
                owner_id=user_id,
                static_root=static_root,
            )
        if result.get("account_invalid"):
            logger.warning(
                f"单品发布选定账号不可用，按要求不切换账号: account_id={account.account_id}, "
                f"error={result.get('message') or '账号失效'}"
            )
        # mtop 令牌刷新可能返回合并后的 Cookie，后续发布后的同步必须继续使用该账号的新 Cookie。
        refreshed_cookies = result.get("cookies_str")
        if refreshed_cookies and refreshed_cookies != account.cookie:
            account.cookie = refreshed_cookies
            refreshed_cookie = refreshed_cookies
        publish_unknown = publish_call_started and bool(
            result and (result.get("unknown") or result.get("_request_status_unknown"))
        )
    except Exception as exc:
        pub_error = exc
        # 一旦进入平台发布调用，异常无法证明平台未产生副作用；即使异常类型
        # 不是常见网络错误，也必须进入人工对账，避免自动续售重复上架。
        publish_unknown = publish_call_started
        logger.error(f"单品发布异常: {exc}")

    if not isinstance(result, dict):
        publish_unknown = publish_call_started
        result = {"success": False, "message": "发布接口未返回有效结果"}

    # 手动发布失败或商品列表没有发生变化时，后续流程可能不会提交调用方会话；
    # Cookie 刷新必须使用独立会话显式落库，确保下一次任务不会继续使用旧令牌。
    if refreshed_cookie:
        try:
            async with async_session_maker() as cookie_session:
                cookie_result = await cookie_session.execute(
                    select(XYAccount).where(
                        XYAccount.account_id == account.account_id,
                        XYAccount.owner_id == user_id,
                    )
                )
                cookie_account = cookie_result.scalars().first()
                if cookie_account:
                    cookie_account.cookie = refreshed_cookie
                    await cookie_session.commit()
        except Exception as cookie_exc:
            logger.error(
                f"发布后保存刷新 Cookie 失败: account_id={account.account_id}, error={cookie_exc}"
            )

    try:
        async with async_session_maker() as fresh_session:
            fresh_log_svc = PublishLogService(fresh_session)
            if pub_error:
                await fresh_log_svc.update_log(
                    log_id=log.id,
                    status="publishing" if publish_unknown else "failed",
                    error_message="发布请求已提交，结果未知，请先对账" if publish_unknown else str(pub_error),
                )
                return {
                    "success": False,
                    "unknown": publish_unknown,
                    "message": "发布请求结果未知，请先对账" if publish_unknown else f"发布异常: {str(pub_error)}",
                    "log_id": log.id,
                }

            if publish_unknown:
                await fresh_log_svc.update_log(
                    log_id=log.id,
                    status="publishing",
                    error_message="发布请求结果未知，请先对账",
                )
                return {
                    "success": False,
                    "unknown": True,
                    "message": result.get("message") or "发布请求结果未知，请先对账",
                    "item_id": result.get("item_id"),
                    "item_url": result.get("item_url"),
                    "log_id": log.id,
                }
            publish_success = bool(result.get("success"))
            result_item_id = str(result.get("item_id") or "").strip()

            # 自动续售必须拿到平台商品 ID 才能继续本地迁移和切换监听商品。
            # 平台返回成功但缺少 ID（或返回失败却带有 ID）都无法证明副作用状态，
            # 统一保留为未知结果，禁止后续再次调用发布接口。
            ambiguous_result = bool(publish_request_id) and (
                (publish_success and not result_item_id)
                or (not publish_success and bool(result_item_id))
            )
            if ambiguous_result:
                reconcile_message = (
                    "发布接口返回成功但未返回商品 ID，请先对账"
                    if publish_success
                    else "发布接口返回失败但包含商品 ID，请先对账"
                )
                await fresh_log_svc.update_log(
                    log_id=log.id,
                    status="publishing",
                    item_id=result_item_id or None,
                    error_message=reconcile_message,
                )
                return {
                    "success": False,
                    "unknown": True,
                    "message": reconcile_message,
                    "item_id": result_item_id or None,
                    "log_id": log.id,
                }

            status = "success" if publish_success else "failed"
            await fresh_log_svc.update_log(
                log_id=log.id,
                status=status,
                item_url=result.get("item_url"),
                item_id=result_item_id or None,
                error_message=None if publish_success else result.get("message"),
            )
    except Exception as db_err:
        logger.error(f"更新发布日志失败: {db_err}")
        if publish_request_id:
            # 外部平台结果已返回，但本地日志状态无法确认，自动续售不得把它当作
            # 可安全重试的明确失败，否则可能重复上架。
            return {
                "success": False,
                "unknown": True,
                "message": "发布结果已返回但日志保存失败，请先人工对账",
                "item_id": result.get("item_id"),
                "log_id": log.id,
            }

    if pub_error:
        return {"success": False, "message": f"发布异常: {str(pub_error)}", "log_id": log.id}

    publish_success = bool(result.get("success", False))
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
