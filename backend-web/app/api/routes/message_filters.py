"""
消息过滤规则管理路由

功能：
- 获取账号下所有消息过滤规则
- 新增消息过滤规则
- 修改消息过滤规则
- 删除消息过滤规则
- 启用/禁用消息过滤规则
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from app.services.account_service import AccountService

router = APIRouter(tags=["message-filters"])
VALID_FILTER_TYPES = {"skip_reply", "skip_notify"}


class MessageFilterCreate(BaseModel):
    """创建消息过滤规则请求"""
    account_id: str
    keyword: str
    filter_types: List[str]  # 支持多选: ['skip_reply', 'skip_notify']


class MessageFilterBatchCreate(BaseModel):
    account_ids: List[str]
    keyword: str
    filter_types: List[str]


class MessageFilterUpdate(BaseModel):
    """更新消息过滤规则请求"""
    keyword: Optional[str] = None
    filter_type: Optional[str] = None
    enabled: Optional[bool] = None


class MessageFilterResponse(BaseModel):
    """消息过滤规则响应"""
    id: int
    account_id: str
    keyword: str
    filter_type: str
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _normalize_string_list(values: List[str]) -> List[str]:
    normalized_values: List[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized_value = value.strip()
        if not normalized_value or normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def _build_failed_message(failed_items: List[dict]) -> str:
    previews = [
        f"{item['account_id']}-{item['filter_type']}({item['message']})"
        for item in failed_items[:5]
    ]
    if len(failed_items) > 5:
        previews.append(f"其余{len(failed_items) - 5}条略")
    return "；".join(previews)


async def _create_message_filter_records(
    session: AsyncSession,
    account_ids: List[str],
    keyword: str,
    filter_types: List[str],
) -> ApiResponse:
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return ApiResponse(success=False, message="关键词不能为空")

    normalized_account_ids = _normalize_string_list(account_ids)
    if not normalized_account_ids:
        return ApiResponse(success=False, message="请选择至少一个账号")

    normalized_filter_types = _normalize_string_list(filter_types)
    if not normalized_filter_types:
        return ApiResponse(success=False, message="请选择至少一种过滤类型")

    invalid_filter_types = [filter_type for filter_type in normalized_filter_types if filter_type not in VALID_FILTER_TYPES]
    if invalid_filter_types:
        return ApiResponse(
            success=False,
            message=f"无效的过滤类型: {', '.join(invalid_filter_types)}",
        )

    exists_sql = text("""
        SELECT id
        FROM xy_message_filters
        WHERE account_id = :account_id
          AND keyword = :keyword
          AND filter_type = :filter_type
        LIMIT 1
    """)
    insert_sql = text("""
        INSERT INTO xy_message_filters (account_id, keyword, filter_type, enabled)
        VALUES (:account_id, :keyword, :filter_type, 1)
    """)
    last_insert_sql = text("SELECT LAST_INSERT_ID() as id")
    created_ids: List[int] = []
    failed_items: List[dict] = []

    for account_id in normalized_account_ids:
        for filter_type in normalized_filter_types:
            try:
                exists_result = await session.execute(
                    exists_sql,
                    {
                        "account_id": account_id,
                        "keyword": normalized_keyword,
                        "filter_type": filter_type,
                    },
                )
                exists_row = exists_result.fetchone()
                if exists_row is not None:
                    failed_items.append(
                        {
                            "account_id": account_id,
                            "filter_type": filter_type,
                            "message": "已存在",
                        }
                    )
                    continue

                await session.execute(
                    insert_sql,
                    {
                        "account_id": account_id,
                        "keyword": normalized_keyword,
                        "filter_type": filter_type,
                    },
                )
                await session.commit()
                result = await session.execute(last_insert_sql)
                row = result.fetchone()
                if row is not None:
                    created_ids.append(row.id)
            except Exception as exc:
                await session.rollback()
                error_message = "已存在" if "Duplicate entry" in str(exc) else str(exc)
                failed_items.append(
                    {
                        "account_id": account_id,
                        "filter_type": filter_type,
                        "message": error_message,
                    }
                )

    created_count = len(created_ids)
    failed_count = len(failed_items)
    if created_count == 0:
        failed_message = _build_failed_message(failed_items) if failed_items else "未创建任何规则"
        return ApiResponse(
            success=False,
            message=f"创建失败：{failed_message}",
            data={
                "created_ids": [],
                "created_count": 0,
                "failed_count": failed_count,
                "failed_items": failed_items,
            },
        )

    message = f"成功创建 {created_count} 条规则"
    if failed_count:
        message += f"，{failed_count} 条失败：{_build_failed_message(failed_items)}"

    return ApiResponse(
        success=True,
        message=message,
        data={
            "created_ids": created_ids,
            "created_count": created_count,
            "failed_count": failed_count,
            "failed_items": failed_items,
        },
    )


@router.get("", response_model=ApiResponse)
async def get_message_filters(
    account_id: Optional[str] = None,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """获取消息过滤规则列表，支持按账号筛选，管理员可查看所有"""
    # 获取用户所有账号（管理员获取所有账号）
    owner_id, is_admin = resolve_owner_scope(current_user)
    account_ids = await account_service.list_account_ids(owner_id)
    
    if not account_ids:
        return ApiResponse(success=True, message="获取成功", data=[])
    
    # 如果指定了账号，验证权限
    if account_id:
        if not is_admin and account_id not in account_ids:
            raise HTTPException(status_code=404, detail="账号不存在")
        account_ids = [account_id]
    
    # 查询过滤规则
    placeholders = ", ".join([f":acc_{i}" for i in range(len(account_ids))])
    params = {f"acc_{i}": acc_id for i, acc_id in enumerate(account_ids)}
    
    sql = text(f"""
        SELECT id, account_id, keyword, filter_type, enabled, 
               DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') as created_at,
               DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s') as updated_at
        FROM xy_message_filters 
        WHERE account_id IN ({placeholders})
        ORDER BY created_at DESC
    """)
    
    result = await session.execute(sql, params)
    rows = result.fetchall()
    
    data = [
        {
            "id": row.id,
            "account_id": row.account_id,
            "keyword": row.keyword,
            "filter_type": row.filter_type,
            "enabled": bool(row.enabled),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]
    
    return ApiResponse(success=True, message="获取成功", data=data)


@router.post("", response_model=ApiResponse)
async def create_message_filter(
    filter_data: MessageFilterCreate,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """创建消息过滤规则，支持多选filter_type生成多条记录"""
    owner_id, _ = resolve_owner_scope(current_user)

    account_id = filter_data.account_id.strip()
    if not account_id:
        return ApiResponse(success=False, message="账号不能为空")

    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在或无权操作")

    return await _create_message_filter_records(
        session=session,
        account_ids=[account_id],
        keyword=filter_data.keyword,
        filter_types=filter_data.filter_types,
    )


@router.post("/batch-create", response_model=ApiResponse)
async def create_message_filters_batch(
    filter_data: MessageFilterBatchCreate,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    owner_id, _ = resolve_owner_scope(current_user)
    requested_account_ids = _normalize_string_list(filter_data.account_ids)
    if not requested_account_ids:
        return ApiResponse(success=False, message="请至少选择一个账号")

    accounts = await account_service.get_accounts_for_user(owner_id, requested_account_ids)
    authorized_account_ids = {account.account_id for account in accounts}
    invalid_account_ids = [account_id for account_id in requested_account_ids if account_id not in authorized_account_ids]
    if invalid_account_ids:
        return ApiResponse(
            success=False,
            message=f"以下账号不存在或无权操作: {', '.join(invalid_account_ids)}",
        )

    return await _create_message_filter_records(
        session=session,
        account_ids=requested_account_ids,
        keyword=filter_data.keyword,
        filter_types=filter_data.filter_types,
    )


@router.put("/{filter_id}", response_model=ApiResponse)
async def update_message_filter(
    filter_id: int,
    filter_data: MessageFilterUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """更新消息过滤规则"""
    # 查询规则是否存在
    result = await session.execute(
        text("SELECT * FROM xy_message_filters WHERE id = :id"),
        {"id": filter_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, row.account_id)
    if not account:
        raise HTTPException(status_code=403, detail="无权操作此规则")
    
    # 构建更新语句
    updates = []
    params = {"id": filter_id}
    
    if filter_data.keyword is not None:
        if not filter_data.keyword.strip():
            raise HTTPException(status_code=400, detail="关键词不能为空")
        updates.append("keyword = :keyword")
        params["keyword"] = filter_data.keyword.strip()
    
    if filter_data.filter_type is not None:
        if filter_data.filter_type not in ["skip_reply", "skip_notify"]:
            raise HTTPException(status_code=400, detail="无效的过滤类型")
        updates.append("filter_type = :filter_type")
        params["filter_type"] = filter_data.filter_type
    
    if filter_data.enabled is not None:
        updates.append("enabled = :enabled")
        params["enabled"] = 1 if filter_data.enabled else 0
    
    if not updates:
        return ApiResponse(success=True, message="无需更新")

    try:
        sql = text(f"UPDATE xy_message_filters SET {', '.join(updates)} WHERE id = :id")
        await session.execute(sql, params)
        await session.commit()
        return ApiResponse(success=True, message="更新成功")
    except Exception as e:
        await session.rollback()
        if "Duplicate entry" in str(e):
            return ApiResponse(success=False, message="该账号下已存在相同的关键词和过滤类型组合")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    ids: List[int]


@router.delete("/{filter_id}", response_model=ApiResponse)
async def delete_message_filter(
    filter_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """删除消息过滤规则"""
    # 查询规则是否存在
    result = await session.execute(
        text("SELECT * FROM xy_message_filters WHERE id = :id"),
        {"id": filter_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, row.account_id)
    if not account:
        raise HTTPException(status_code=403, detail="无权操作此规则")
    
    await session.execute(
        text("DELETE FROM xy_message_filters WHERE id = :id"),
        {"id": filter_id}
    )
    await session.commit()
    
    return ApiResponse(success=True, message="删除成功")


@router.post("/batch-delete", response_model=ApiResponse)
async def batch_delete_message_filters(
    request: BatchDeleteRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """批量删除消息过滤规则"""
    if not request.ids:
        return ApiResponse(success=False, message="请选择要删除的规则")
    
    # 获取用户所有账号
    user_account_ids = set(await account_service.list_account_ids(current_user.id))
    
    # 查询要删除的规则
    placeholders = ", ".join([f":id_{i}" for i in range(len(request.ids))])
    params = {f"id_{i}": id for i, id in enumerate(request.ids)}
    
    result = await session.execute(
        text(f"SELECT id, account_id FROM xy_message_filters WHERE id IN ({placeholders})"),
        params
    )
    rows = result.fetchall()
    
    # 验证权限，只删除用户有权限的规则
    valid_ids = [row.id for row in rows if row.account_id in user_account_ids]
    
    if not valid_ids:
        return ApiResponse(success=False, message="没有可删除的规则")
    
    # 执行删除
    delete_placeholders = ", ".join([f":del_{i}" for i in range(len(valid_ids))])
    delete_params = {f"del_{i}": id for i, id in enumerate(valid_ids)}
    
    await session.execute(
        text(f"DELETE FROM xy_message_filters WHERE id IN ({delete_placeholders})"),
        delete_params
    )
    await session.commit()
    
    return ApiResponse(
        success=True,
        message=f"成功删除 {len(valid_ids)} 条规则",
        data={"deleted_count": len(valid_ids)},
    )


@router.put("/{filter_id}/toggle", response_model=ApiResponse)
async def toggle_message_filter(
    filter_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """切换消息过滤规则启用状态"""
    # 查询规则是否存在
    result = await session.execute(
        text("SELECT * FROM xy_message_filters WHERE id = :id"),
        {"id": filter_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, row.account_id)
    if not account:
        raise HTTPException(status_code=403, detail="无权操作此规则")
    
    new_enabled = 0 if row.enabled else 1
    await session.execute(
        text("UPDATE xy_message_filters SET enabled = :enabled WHERE id = :id"),
        {"id": filter_id, "enabled": new_enabled}
    )
    await session.commit()
    
    return ApiResponse(
        success=True,
        message="已启用" if new_enabled else "已禁用",
        data={"enabled": bool(new_enabled)},
    )
