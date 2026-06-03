"""
账号管理API路由

功能：
1. 账号列表查询
2. 账号创建、更新、删除
3. 账号状态管理（启用/禁用）
4. 账号配置更新（备注、自动确认、暂停时长）
5. 自动启动/停止WebSocket任务
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, UploadFile, File, Form, status
from sqlalchemy import func, select, text

from app.api import deps
from common.models.user import User
from common.models.xy_account import XYAccount
from common.utils.time_utils import safe_isoformat
from common.schemas.account import (
    AccountAutoConfirmUpdate,
    AccountAutoPolishUpdate,
    AccountBatchIdsUpdate,
    AccountBatchStatusUpdate,
    AccountAutoRedFlowerUpdate,
    AccountAiReplyBlockOrderedUsersUpdate,
    AccountConfirmBeforeSendUpdate,
    AccountCookieUpdate,
    AccountCreate,
    AccountDeliveryDisabledUpdate,
    AccountDetail,
    AccountOption,
    AccountLoginInfoUpdate,
    AccountMessageExpireTimeUpdate,
    AccountPauseDurationUpdate,
    AccountRemarkUpdate,
    AccountScheduledRedeliveryUpdate,
    AccountScheduledRateUpdate,
    AccountSendBeforeConfirmUpdate,
    AccountStatusUpdate,
    DeliveryBlockRulesUpdate,
)
from common.schemas.common import ApiResponse
from common.services.ai_provider_service import read_ai_enabled
from common.utils.auth_scope import resolve_owner_scope
from common.utils.xianyu_utils import close_account_notice
from app.services.account_service import AccountService
from app.services.auto_reply_stats_service import AutoReplyStatsService
from app.services.dashboard_stats_service import DashboardStatsService

router = APIRouter(tags=["cookies"])


@router.get("", response_model=list[str])
async def list_cookies(
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> list[str]:
    """Return the legacy list of cookie/account ids for the current user.
    管理员返回所有账号，普通用户返回自己的账号。
    """
    owner_id, _ = resolve_owner_scope(current_user)
    return await account_service.list_account_ids(owner_id)


def _status_to_enabled(status: str | None) -> bool:
    if not status:
        return True
    normalized = status.strip().lower()
    return normalized not in {"inactive", "disabled", "suspended", "deleted"}


def _normalize_delivery_excluded_items(raw: object) -> list[str]:
    """归一化禁止发货排除商品列表，兼容 JSON 字段返回的 None / list / 字符串

    - None / 空 -> []
    - list[Any] -> 逐项 str().strip()，过滤空白
    - str -> 尝试按 JSON 解析（部分驱动可能返回字符串）
    其余非法类型一律返回 []。
    """
    if not raw:
        return []
    candidate = raw
    if isinstance(candidate, str):
        try:
            import json as _json
            candidate = _json.loads(candidate)
        except Exception:
            return []
    if not isinstance(candidate, list):
        return []
    result: list[str] = []
    for item in candidate:
        if item is None:
            continue
        text_item = str(item).strip()
        if text_item:
            result.append(text_item)
    return result


def _normalize_batch_account_ids(account_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(account_id.strip() for account_id in account_ids if account_id and account_id.strip()))


async def _get_batch_account_map(
    current_user: User,
    account_ids: list[str],
    account_service: AccountService,
) -> tuple[list[str], dict[str, XYAccount]]:
    normalized_account_ids = _normalize_batch_account_ids(account_ids)
    owner_id, _ = resolve_owner_scope(current_user)
    accounts = await account_service.get_accounts_for_user(owner_id, normalized_account_ids)
    return normalized_account_ids, {account.account_id: account for account in accounts}


def _build_batch_operation_response(
    action_text: str,
    success_ids: list[str],
    failed_items: list[dict[str, str]],
) -> ApiResponse:
    success_count = len(success_ids)
    failed_count = len(failed_items)
    if failed_count > 0:
        return ApiResponse(
            success=False,
            message=f"批量{action_text}完成，成功 {success_count} 个，失败 {failed_count} 个",
            data={
                "success_count": success_count,
                "failed_count": failed_count,
                "success_ids": success_ids,
                "failed_items": failed_items,
            },
        )

    return ApiResponse(
        success=True,
        message=f"批量{action_text}成功，共处理 {success_count} 个账号",
        data={
            "success_count": success_count,
            "failed_count": failed_count,
            "success_ids": success_ids,
            "failed_items": failed_items,
        },
    )


@router.get("/options", response_model=list[AccountOption])
async def list_cookie_options(
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> list[AccountOption]:
    """返回账号下拉选项，避免非账号管理页面查询完整详情。"""
    owner_id, _ = resolve_owner_scope(current_user)
    options = await account_service.list_account_options(owner_id)
    return [AccountOption(**item) for item in options]


@router.get("/details", response_model=list[AccountDetail])
async def list_cookie_details(
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session = Depends(deps.get_db_session),
) -> list[AccountDetail]:
    """Return legacy-compatible cookie details payload.
    管理员返回所有账号，普通用户返回自己的账号。
    """
    from sqlalchemy import text
    owner_id, _ = resolve_owner_scope(current_user)
    accounts = await account_service.list_accounts(owner_id)
    
    # 获取所有账号的消息过滤规则数量
    account_ids = [acc.account_id for acc in accounts]
    filter_counts = {}
    if account_ids:
        placeholders = ", ".join([f":acc_{i}" for i in range(len(account_ids))])
        params = {f"acc_{i}": acc_id for i, acc_id in enumerate(account_ids)}
        sql = text(f"""
            SELECT account_id, COUNT(*) as count 
            FROM xy_message_filters 
            WHERE account_id IN ({placeholders})
            GROUP BY account_id
        """)
        result = await session.execute(sql, params)
        for row in result.fetchall():
            filter_counts[row.account_id] = row.count
    
    details: list[AccountDetail] = []
    for account in accounts:
        details.append(
            AccountDetail(
                pk=account.id,  # 数据库主键
                id=account.account_id,
                value=account.cookie or "",
                enabled=_status_to_enabled(account.status),
                auto_confirm=bool(account.auto_confirm),
                scheduled_redelivery=bool(account.scheduled_redelivery),
                scheduled_rate=bool(account.scheduled_rate),
                auto_polish=bool(account.auto_polish),
                confirm_before_send=bool(account.confirm_before_send),
                send_before_confirm=bool(account.send_before_confirm),
                auto_red_flower=bool(account.auto_red_flower),
                ai_reply_block_ordered_users=bool(account.ai_reply_block_ordered_users),
                delivery_disabled=bool(account.delivery_disabled),
                delivery_disabled_reason=account.delivery_disabled_reason or "",
                auto_close_order=bool(account.auto_close_order),
                delivery_only_card_after_close=bool(account.delivery_only_card_after_close),
                delivery_disabled_excluded_item_ids=_normalize_delivery_excluded_items(
                    account.delivery_disabled_excluded_items
                ),
                remark=account.remark or "",
                pause_duration=account.pause_duration if account.pause_duration is not None else 10,
                message_expire_time=account.message_expire_time if account.message_expire_time is not None else 3600,
                username=account.username or "",
                login_password=account.login_password or "",
                show_browser=bool(account.show_browser),
                disable_reason=account.disable_reason or "",
                filter_count=filter_counts.get(account.account_id, 0),
            )
        )
    return details


@router.get("/details/paginated")
async def list_cookie_details_paginated(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(default=None, description="状态筛选：active/inactive"),
    ai_reply: bool | None = Query(default=None, description="AI回复开关筛选"),
    scheduled_redelivery: bool | None = Query(default=None, description="定时补发货筛选"),
    scheduled_rate: bool | None = Query(default=None, description="定时补评价筛选"),
    auto_polish: bool | None = Query(default=None, description="商品擦亮筛选"),
    auto_confirm: bool | None = Query(default=None, description="自动确认收货筛选"),
    has_password: bool | None = Query(default=None, description="是否配置密码筛选"),
    disable_reason: str | None = Query(default=None, max_length=255, description="禁用原因模糊搜索关键词"),
    account_id: str | None = Query(default=None, max_length=255, description="账号ID模糊搜索关键词"),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session = Depends(deps.get_db_session),
):
    """获取账号详情列表（分页），支持多条件筛选
    
    管理员返回所有账号，普通用户返回自己的账号。
    
    筛选条件：
    - status: 状态（active=启用, inactive=禁用）
    - ai_reply: AI回复开关（true/false）
    - scheduled_redelivery: 定时补发货（true/false）
    - scheduled_rate: 定时补评价（true/false）
    - auto_polish: 商品擦亮（true/false）
    - auto_confirm: 自动确认收货（true/false）
    - has_password: 是否配置密码（true/false）
    - disable_reason: 禁用原因关键词（LIKE 模糊搜索）
    - account_id: 账号ID关键词（LIKE 模糊搜索）
    """
    owner_id, _ = resolve_owner_scope(current_user)
    accounts, total = await account_service.list_accounts_paginated(
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        status=status,
        ai_reply=ai_reply,
        scheduled_redelivery=scheduled_redelivery,
        scheduled_rate=scheduled_rate,
        auto_polish=auto_polish,
        auto_confirm=auto_confirm,
        has_password=has_password,
        disable_reason=disable_reason,
        account_id=account_id,
    )
    
    # 获取所有账号的消息过滤规则数量
    account_ids = [acc.account_id for acc in accounts]
    account_pks = [acc.id for acc in accounts]
    filter_counts = {}
    keyword_counts = {}
    today_reply_counts = {}
    if account_ids:
        placeholders = ", ".join([f":acc_{i}" for i in range(len(account_ids))])
        params = {f"acc_{i}": acc_id for i, acc_id in enumerate(account_ids)}
        sql = text(f"""
            SELECT account_id, COUNT(*) as count 
            FROM xy_message_filters 
            WHERE account_id IN ({placeholders})
            GROUP BY account_id
        """)
        result = await session.execute(sql, params)
        for row in result.fetchall():
            filter_counts[row.account_id] = row.count

    if account_pks:
        pk_placeholders = ", ".join([f":pk_{i}" for i in range(len(account_pks))])
        pk_params = {f"pk_{i}": acc_pk for i, acc_pk in enumerate(account_pks)}

        keyword_sql = text(f"""
            SELECT account_id, COUNT(*) as count
            FROM xy_keyword_rules
            WHERE account_id IN ({pk_placeholders}) AND is_active = 1
            GROUP BY account_id
        """)
        keyword_result = await session.execute(keyword_sql, pk_params)
        for row in keyword_result.fetchall():
            keyword_counts[row.account_id] = row.count

    if account_ids:
        today_reply_counts = await AutoReplyStatsService(session).get_today_success_reply_counts_by_account(account_ids)

    details = []
    for account in accounts:
        ai_settings = (account.metadata_json or {}).get("ai_reply_settings") or {}
        details.append({
            "pk": account.id,  # 数据库主键
            "id": account.account_id,
            "value": account.cookie or "",
            "enabled": _status_to_enabled(account.status),
            "auto_confirm": bool(account.auto_confirm),
            "scheduled_redelivery": bool(account.scheduled_redelivery),
            "scheduled_rate": bool(account.scheduled_rate),
            "auto_polish": bool(account.auto_polish),
            "confirm_before_send": bool(account.confirm_before_send),
            "send_before_confirm": bool(account.send_before_confirm),
            "auto_red_flower": bool(account.auto_red_flower),
            "ai_reply_block_ordered_users": bool(account.ai_reply_block_ordered_users),
            "delivery_disabled": bool(account.delivery_disabled),
            "delivery_disabled_reason": account.delivery_disabled_reason or "",
            "auto_close_order": bool(account.auto_close_order),
            "delivery_only_card_after_close": bool(account.delivery_only_card_after_close),
            "delivery_disabled_excluded_item_ids": _normalize_delivery_excluded_items(
                account.delivery_disabled_excluded_items
            ),
            "remark": account.remark or "",
            "pause_duration": account.pause_duration if account.pause_duration is not None else 10,
            "message_expire_time": account.message_expire_time if account.message_expire_time is not None else 3600,
            "username": account.username or "",
            "login_password": account.login_password or "",
            "show_browser": bool(account.show_browser),
            "disable_reason": account.disable_reason or "",
            "filter_count": filter_counts.get(account.account_id, 0),
            "today_reply_count": today_reply_counts.get(account.account_id, 0),
            "keyword_count": keyword_counts.get(account.id, 0),
            "ai_enabled": read_ai_enabled(ai_settings),
            "created_at": safe_isoformat(account.created_at),
            "updated_at": safe_isoformat(account.updated_at),
        })
    
    return {
        "success": True,
        "data": details,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


async def _get_account_or_404(
    current_user: User,
    account_id: str,
    account_service: AccountService,
) -> XYAccount:
    """
    获取账号，如果不存在或无权限则抛出404
    
    权限规则：
    - 管理员可以访问所有账号
    - 普通用户只能访问自己的账号
    """
    from loguru import logger

    owner_id, is_admin = resolve_owner_scope(current_user)
    # 管理员可以访问所有账号
    if is_admin:
        logger.info(f"管理员 {current_user.username} 访问账号 {account_id}，owner_id=None")
    else:
        logger.info(f"普通用户 {current_user.username} (ID:{current_user.id}) 访问账号 {account_id}，owner_id={owner_id}")
    
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        logger.warning(f"账号 {account_id} 不存在或用户 {current_user.username} 无权限访问")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在或无权限访问")
    
    logger.info(f"成功获取账号 {account_id}，所有者ID: {account.owner_id}")
    return account


async def _update_account_status_and_task(
    account: XYAccount,
    enabled: bool,
    account_service: AccountService,
) -> tuple[bool, str | None]:
    current_enabled = _status_to_enabled(account.status)
    if current_enabled == enabled:
        return True, None

    from app.services.websocket_client import websocket_client

    original_disable_reason = account.disable_reason
    await account_service.update_status(
        account, enabled, disable_reason="手动禁用" if not enabled else None
    )

    if enabled:
        task_result = await websocket_client.start_account(account.account_id, account.cookie or "", account.owner_id)
    else:
        task_result = await websocket_client.stop_account(account.account_id)

    task_success = True
    task_message = None
    if isinstance(task_result, dict):
        task_success = bool(task_result.get("success", True))
        task_message = task_result.get("message")

    if not task_success:
        await account_service.update_status(account, current_enabled, original_disable_reason)
        return False, task_message or ("账号任务启动失败" if enabled else "账号任务停止失败")

    return True, None


@router.get("/delivery-block-rules/available", response_model=ApiResponse)
async def get_available_delivery_block_rules(
    current_user: User = Depends(deps.get_current_active_user),
) -> ApiResponse:
    """获取所有可用的禁止发货规则类型（前端展示用）"""
    from common.services.delivery_block_rule_meta import get_all_rule_metadata
    metadata = get_all_rule_metadata()
    return ApiResponse(success=True, message="获取成功", data=metadata)


@router.post("", response_model=ApiResponse)
async def create_account(
    payload: AccountCreate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    try:
        account = await account_service.create_account(current_user.id, payload.id, payload.value)
        
        # 启动WebSocket任务（通过HTTP调用WebSocket服务）
        from app.services.websocket_client import websocket_client
        task_result = await websocket_client.start_account(account.account_id, account.cookie or "", account.owner_id)
        if isinstance(task_result, dict) and not task_result.get("success", True):
            return ApiResponse(success=False, message=task_result.get("message") or "账号已添加，但启动任务失败")
        
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    except Exception as exc:
        return ApiResponse(success=False, message=f"添加账号失败: {str(exc)}")
    return ApiResponse(success=True, message="账号已添加")


@router.put("/{account_id}", response_model=ApiResponse)
async def update_account_cookie(
    account_id: str,
    payload: AccountCookieUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_cookie(account, payload.value)
    
    # 更新Cookie并重启WebSocket任务（通过HTTP调用WebSocket服务）
    from app.services.websocket_client import websocket_client
    await websocket_client.restart_account(account_id)
    
    return ApiResponse(success=True, message="Cookie 已更新")


@router.put("/{account_id}/status", response_model=ApiResponse)
async def update_account_status(
    account_id: str,
    payload: AccountStatusUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account = await _get_account_or_404(current_user, account_id, account_service)
    success, error_message = await _update_account_status_and_task(account, payload.enabled, account_service)
    if not success:
        return ApiResponse(success=False, message=error_message or "账号状态更新失败")
    return ApiResponse(success=True, message="账号状态已更新")


@router.put("/status/batch", response_model=ApiResponse)
async def update_accounts_status_batch(
    payload: AccountBatchStatusUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account_ids, account_map = await _get_batch_account_map(current_user, payload.account_ids, account_service)
    if not account_ids:
        return ApiResponse(
            success=False,
            message="请选择至少一个账号",
            data={
                "success_count": 0,
                "failed_count": 0,
                "success_ids": [],
                "failed_items": [],
            },
        )

    success_ids: list[str] = []
    failed_items: list[dict[str, str]] = []

    for account_id in account_ids:
        account = account_map.get(account_id)
        if not account:
            failed_items.append({"account_id": account_id, "message": "账号不存在或无权限访问"})
            continue

        success, error_message = await _update_account_status_and_task(account, payload.enabled, account_service)
        if success:
            success_ids.append(account_id)
        else:
            failed_items.append({"account_id": account_id, "message": error_message or "账号状态更新失败"})

    return _build_batch_operation_response("启动" if payload.enabled else "禁用", success_ids, failed_items)


@router.put("/close-notice/batch", response_model=ApiResponse)
async def close_accounts_notice_batch(
    payload: AccountBatchIdsUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account_ids, account_map = await _get_batch_account_map(current_user, payload.account_ids, account_service)
    if not account_ids:
        return ApiResponse(
            success=False,
            message="请选择至少一个账号",
            data={
                "success_count": 0,
                "failed_count": 0,
                "success_ids": [],
                "failed_items": [],
            },
        )

    success_ids: list[str] = []
    failed_items: list[dict[str, str]] = []

    for account_id in account_ids:
        account = account_map.get(account_id)
        if not account:
            failed_items.append({"account_id": account_id, "message": "账号不存在或无权限访问"})
            continue

        success, error_message = await close_account_notice(account.account_id, account.cookie or "", "账号管理关闭通知")
        if success:
            success_ids.append(account_id)
        else:
            failed_items.append({"account_id": account_id, "message": error_message or "关闭通知失败"})

    return _build_batch_operation_response("关闭通知", success_ids, failed_items)


@router.put("/clear-token-cache/batch", response_model=ApiResponse)
async def clear_token_cache_batch(
    payload: AccountBatchIdsUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session=Depends(deps.get_db_session),
) -> ApiResponse:
    """批量清除账号Token缓存并自动禁用再启用（重启）

    流程：
    1. 根据账号unb删除xy_token_cache中对应缓存记录
    2. 禁用账号（停止websocket任务）
    3. 重新启用账号（重新获取token并启动websocket任务）
    """
    import asyncio as _asyncio
    from loguru import logger as _logger

    account_ids, account_map = await _get_batch_account_map(current_user, payload.account_ids, account_service)
    if not account_ids:
        return ApiResponse(
            success=False,
            message="请选择至少一个账号",
            data={"success_count": 0, "failed_count": 0, "success_ids": [], "failed_items": []},
        )

    success_ids: list[str] = []
    failed_items: list[dict[str, str]] = []

    for account_id in account_ids:
        account = account_map.get(account_id)
        if not account:
            failed_items.append({"account_id": account_id, "message": "账号不存在或无权限访问"})
            continue

        unb = account.unb or ""
        if not unb:
            # unb 字段为空时，尝试从 cookie 中解析
            try:
                from common.utils.xianyu_utils import trans_cookies
                cookie_dict = trans_cookies(account.cookie or "")
                unb = cookie_dict.get("unb", "")
            except Exception:
                pass
        if not unb:
            failed_items.append({"account_id": account_id, "message": "账号缺少unb信息，无法清除缓存"})
            continue

        try:
            # 1. 清除Token缓存（websocket侧user_id=unb，chat侧user_id=chat_unb）
            await session.execute(
                text("DELETE FROM xy_token_cache WHERE user_id IN (:uid1, :uid2)"),
                {"uid1": unb, "uid2": f"chat_{unb}"},
            )
            await session.commit()
            _logger.info(f"[清除Token缓存] 账号 {account_id} 的Token缓存已清除 (unb={unb})")

            # 2. 禁用账号
            disable_ok, disable_err = await _update_account_status_and_task(account, False, account_service)
            if not disable_ok:
                failed_items.append({"account_id": account_id, "message": f"禁用失败: {disable_err}"})
                continue

            # 短暂等待确保websocket任务完全停止
            await _asyncio.sleep(1)

            # 3. 重新启用账号
            enable_ok, enable_err = await _update_account_status_and_task(account, True, account_service)
            if not enable_ok:
                failed_items.append({"account_id": account_id, "message": f"重新启用失败: {enable_err}"})
                continue

            success_ids.append(account_id)
        except Exception as exc:
            _logger.error(f"[清除Token缓存] 账号 {account_id} 处理异常: {exc}")
            failed_items.append({"account_id": account_id, "message": f"处理异常: {str(exc)}"})

    return _build_batch_operation_response("清除Token缓存并重启", success_ids, failed_items)


@router.put("/{account_id}/remark", response_model=ApiResponse)
async def update_account_remark(
    account_id: str,
    payload: AccountRemarkUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_remark(account, payload.remark)
    return ApiResponse(success=True, message="备注已更新")


@router.put("/{account_id}/auto-confirm", response_model=ApiResponse)
async def update_account_auto_confirm(
    account_id: str,
    payload: AccountAutoConfirmUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_auto_confirm(account, payload.auto_confirm)
    return ApiResponse(success=True, message="自动确认设置已更新")


@router.put("/{account_id}/pause-duration", response_model=ApiResponse)
async def update_account_pause_duration(
    account_id: str,
    payload: AccountPauseDurationUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_pause_duration(account, payload.pause_duration)
    return ApiResponse(success=True, message="暂停时长已更新")


@router.put("/{account_id}/message-expire-time", response_model=ApiResponse)
async def update_account_message_expire_time(
    account_id: str,
    payload: AccountMessageExpireTimeUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新相同消息等待时间"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_message_expire_time(account, payload.message_expire_time)
    return ApiResponse(success=True, message="相同消息等待时间已更新")


@router.put("/{account_id}/login-info", response_model=ApiResponse)
async def update_account_login_info(
    account_id: str,
    payload: AccountLoginInfoUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新账号登录信息（用户名、密码、是否显示浏览器）"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_login_info(
        account,
        username=payload.username,
        login_password=payload.login_password,
        show_browser=payload.show_browser,
    )
    return ApiResponse(success=True, message="登录信息已更新")


@router.put("/{account_id}/scheduled-redelivery", response_model=ApiResponse)
async def update_account_scheduled_redelivery(
    account_id: str,
    payload: AccountScheduledRedeliveryUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新定时补发货开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_scheduled_redelivery(account, payload.scheduled_redelivery)
    return ApiResponse(success=True, message="定时补发货设置已更新")


@router.put("/{account_id}/scheduled-rate", response_model=ApiResponse)
async def update_account_scheduled_rate(
    account_id: str,
    payload: AccountScheduledRateUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新定时补评价开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_scheduled_rate(account, payload.scheduled_rate)
    return ApiResponse(success=True, message="定时补评价设置已更新")


@router.put("/{account_id}/auto-polish", response_model=ApiResponse)
async def update_account_auto_polish(
    account_id: str,
    payload: AccountAutoPolishUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新商品自动擦亮开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_auto_polish(account, payload.auto_polish)
    return ApiResponse(success=True, message="商品自动擦亮设置已更新")


@router.put("/{account_id}/confirm-before-send", response_model=ApiResponse)
async def update_account_confirm_before_send(
    account_id: str,
    payload: AccountConfirmBeforeSendUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新发货成功再发卡券开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_confirm_before_send(account, payload.confirm_before_send)
    return ApiResponse(success=True, message="发货成功再发卡券设置已更新")


@router.put("/{account_id}/send-before-confirm", response_model=ApiResponse)
async def update_account_send_before_confirm(
    account_id: str,
    payload: AccountSendBeforeConfirmUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新卡券发送成功再确认发货开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_send_before_confirm(account, payload.send_before_confirm)
    return ApiResponse(success=True, message="卡券发送成功再确认发货设置已更新")


@router.put("/{account_id}/auto-red-flower", response_model=ApiResponse)
async def update_account_auto_red_flower(
    account_id: str,
    payload: AccountAutoRedFlowerUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新自动求小红花开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_auto_red_flower(account, payload.auto_red_flower)
    return ApiResponse(success=True, message="自动求小红花设置已更新")


@router.put("/{account_id}/ai-reply-block-ordered-users", response_model=ApiResponse)
async def update_account_ai_reply_block_ordered_users(
    account_id: str,
    payload: AccountAiReplyBlockOrderedUsersUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新已下单用户禁止AI回复开关"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_ai_reply_block_ordered_users(account, payload.ai_reply_block_ordered_users)
    return ApiResponse(success=True, message="已下单用户禁止AI回复设置已更新")


@router.put("/{account_id}/delivery-disabled", response_model=ApiResponse)
async def update_account_delivery_disabled(
    account_id: str,
    payload: AccountDeliveryDisabledUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """更新禁止发货设置（旧接口，保留向后兼容）

    内部会将旧格式转换为规则引擎格式写入 xy_delivery_block_rules 表。
    """
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_delivery_disabled(
        account,
        delivery_disabled=payload.delivery_disabled,
        delivery_disabled_reason=payload.delivery_disabled_reason,
        auto_close_order=payload.auto_close_order,
        delivery_only_card_after_close=payload.delivery_only_card_after_close,
        excluded_item_ids=payload.excluded_item_ids or [],
    )
    return ApiResponse(success=True, message="禁止发货设置已更新")


@router.get("/{account_id}/delivery-block-rules", response_model=ApiResponse)
async def get_delivery_block_rules(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """获取账号的禁止发货规则列表"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    rules = await account_service.get_delivery_block_rules(account.account_id)
    return ApiResponse(success=True, message="获取成功", data=rules)


@router.put("/{account_id}/delivery-block-rules", response_model=ApiResponse)
async def update_delivery_block_rules(
    account_id: str,
    payload: DeliveryBlockRulesUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """批量更新账号的禁止发货规则配置"""
    account = await _get_account_or_404(current_user, account_id, account_service)
    await account_service.update_delivery_block_rules(account.account_id, payload.rules)
    return ApiResponse(success=True, message="禁止发货规则已更新")


@router.delete("/{account_id}", response_model=ApiResponse)
async def delete_account(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    account = await _get_account_or_404(current_user, account_id, account_service)
    
    # 先停止WebSocket任务（通过HTTP调用WebSocket服务）
    from app.services.websocket_client import websocket_client
    await websocket_client.stop_account(account_id)
    
    await account_service.delete_account(account)
    return ApiResponse(success=True, message="账号已删除")


@router.get("/stats", response_model=ApiResponse)
async def get_account_stats(
    current_user: User = Depends(deps.get_current_active_user),
    session = Depends(deps.get_db_session),
) -> ApiResponse:
    """获取账号统计数据（包含关键词总数）
    
    返回：
    - total_accounts: 总账号数
    - active_accounts: 启用账号数
    - total_keywords: 总关键词数
    - total_orders: 总订单数
    """
    owner_id, _ = resolve_owner_scope(current_user)
    stats = await DashboardStatsService(session).get_account_dashboard_stats(
        current_user_id=current_user.id,
        account_scope_owner_id=owner_id,
        reply_scope_owner_id=current_user.id,
    )

    return ApiResponse(
        success=True,
        message="获取统计数据成功",
        data=stats,
    )


@router.get("/stats/order-trend", response_model=ApiResponse)
async def get_order_amount_trend(
    current_user: User = Depends(deps.get_current_active_user),
    session = Depends(deps.get_db_session),
) -> ApiResponse:
    """获取近30天每日订单金额趋势

    - 普通用户：汇总该用户所有账号的订单金额
    - 管理员：汇总所有用户的所有账号订单金额
    - 排除已关闭/已取消的订单
    """
    owner_id, _ = resolve_owner_scope(current_user)
    trend_data = await DashboardStatsService(session).get_order_amount_trend(owner_id=owner_id, days=30)

    return ApiResponse(success=True, message="获取订单金额趋势成功", data={"trend": trend_data})


@router.post("/export")
async def export_accounts(
    request: dict = Body(default={}),
    current_user: User = Depends(deps.get_current_active_user),
    session=Depends(deps.get_db_session),
) -> Response:
    """导出账号数据为Excel文件

    支持两种模式：
    - 勾选导出：传入 account_ids 列表
    - 筛选导出：不传 account_ids，按筛选条件导出

    请求体：
    {
        "account_ids": ["id1", "id2"],  // 可选，勾选的账号ID
        "status": "active",             // 可选，状态筛选
        "account_id": "关键词",          // 可选，账号ID模糊搜索
        "has_password": true             // 可选，是否配置密码
    }
    """
    from app.services.account_export_service import AccountExportService

    owner_id, _ = resolve_owner_scope(current_user)
    export_service = AccountExportService(session)

    account_ids = request.get("account_ids")
    # 构建筛选条件
    filters = None
    if not account_ids:
        filters = {}
        status_filter = request.get("status")
        account_id_filter = request.get("account_id")
        has_password = request.get("has_password")
        if status_filter:
            filters["status"] = status_filter
        if account_id_filter:
            filters["account_id"] = account_id_filter
        if has_password is not None:
            filters["has_password"] = has_password

    try:
        output = await export_service.export_accounts(
            owner_id=owner_id,
            account_ids=account_ids,
            filters=filters,
        )
    except Exception as exc:
        from loguru import logger
        logger.error(f"导出账号数据失败: {exc}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(exc)}")

    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=accounts_export.xlsx"},
    )


@router.post("/import")
async def import_accounts(
    file: UploadFile = File(..., description="Excel文件"),
    enable_all: bool = Form(default=False, description="是否全部启用"),
    current_user: User = Depends(deps.get_current_active_user),
    session=Depends(deps.get_db_session),
):
    """导入账号数据（从Excel文件）

    支持两种模式：
    - enable_all=false：按Excel中的状态导入（启用的启用，禁用的仅入库）
    - enable_all=true：所有账号强制启用并启动WebSocket任务
    """
    from app.services.account_import_service import AccountImportService

    if not file.filename or not file.filename.endswith(".xlsx"):
        return ApiResponse(success=False, message="请上传 .xlsx 格式的Excel文件")

    try:
        content = await file.read()
    except Exception as exc:
        return ApiResponse(success=False, message=f"读取文件失败: {str(exc)}")

    import_service = AccountImportService(session, current_user.id)
    result = await import_service.import_accounts(content, enable_all=enable_all)
    return result


@router.post("/renew-login")
async def renew_account_login(
    account_ids: list[str],
    current_user: User = Depends(deps.get_current_active_user),
) -> ApiResponse:
    """批量账号续期（调用 silentHasLogin.do + setLoginSettings.do 续期Cookie）

    通过共通服务同时调用两个续期接口，将返回的 Set-Cookie 增量合并到账号现有 cookie 中。

    Args:
        account_ids: 账号ID列表（account_id 字符串，支持批量）
    """
    from common.db.session import async_session_maker
    from common.services.cookie_renew_api_service import cookie_renew_api_service
    from sqlalchemy import select

    owner_id, is_admin = resolve_owner_scope(current_user)

    results = []
    success_count = 0
    failed_count = 0

    async with async_session_maker() as session:
        for account_id in account_ids:
            try:
                # 获取账号信息（通过 account_id 字符串）
                stmt = select(XYAccount).where(XYAccount.account_id == account_id)
                if owner_id is not None:
                    stmt = stmt.where(XYAccount.owner_id == owner_id)
                result = await session.execute(stmt)
                account = result.scalars().first()

                if not account:
                    results.append({"account_id": account_id, "success": False, "message": "账号不存在"})
                    failed_count += 1
                    continue

                cookies_str = account.cookie or ""
                if not cookies_str.strip():
                    results.append({"account_id": account_id, "success": False, "message": "账号Cookie为空"})
                    failed_count += 1
                    continue

                # 调用共通服务执行接口续期
                renew_result = await cookie_renew_api_service.renew(cookies_str, account_id)

                # 不管续期是否成功，只要有Cookie字段更新就先写入数据库
                if renew_result.updated_cookie_names and renew_result.new_cookies_str != cookies_str:
                    account.cookie = renew_result.new_cookies_str
                    await session.commit()

                if not renew_result.success:
                    results.append({
                        "account_id": account_id,
                        "account_name": account.account_id,
                        "success": False,
                        "message": renew_result.api_message or "续期接口未返回有效Cookie",
                    })
                    failed_count += 1
                    continue

                # 续期成功，自动启用账号
                if account.status != "active":
                    account.status = "active"
                    account.disable_reason = None
                    await session.commit()

                # 通知 WebSocket 服务启动/重启账号任务
                try:
                    from app.services.websocket_client import websocket_client
                    await websocket_client.start_account(account.account_id, renew_result.new_cookies_str or cookies_str, account.owner_id)
                except Exception as ws_e:
                    from loguru import logger
                    logger.warning(f"账号 {account.account_id} 续期成功但启动WebSocket任务失败: {ws_e}")

                if renew_result.updated_cookie_names:
                    results.append({
                        "account_id": account_id,
                        "account_name": account.account_id,
                        "success": True,
                        "message": f"续期成功，更新了 {len(renew_result.updated_cookie_names)} 个字段：{', '.join(renew_result.updated_cookie_names)}",
                    })
                else:
                    results.append({
                        "account_id": account_id,
                        "account_name": account.account_id,
                        "success": True,
                        "message": "续期成功，Cookie无变化",
                    })
                success_count += 1

            except Exception as e:
                await session.rollback()
                results.append({
                    "account_id": account_id,
                    "success": False,
                    "message": f"续期异常: {str(e)}",
                })
                failed_count += 1

    return ApiResponse(
        success=True,
        message=f"批量续期完成：成功 {success_count} 个，失败 {failed_count} 个",
        data={"results": results, "success_count": success_count, "failed_count": failed_count},
    )
