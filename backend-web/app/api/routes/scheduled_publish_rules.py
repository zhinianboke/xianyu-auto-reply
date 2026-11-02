"""
商品定时发布规则接口。

功能：
1. 新建规则；
2. 修改规则；
3. 按规则名称分页查询；
4. 查询新建规则所需的账号和素材选项；
5. 分页查询规则的发布记录和触发记录；
6. 单条或批量软删除触发记录。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from app.services.scheduled_publish_rule_service import (
    ScheduledPublishRuleService,
    ScheduledPublishRuleValidationError,
)
from app.services.scheduled_publish_record_service import (
    ScheduledPublishRecordService,
)
from common.models.user import User
from common.schemas.common import ApiResponse


router = APIRouter(prefix="/product-publish/scheduled-rules", tags=["商品定时发布"])


class ScheduledPublishRuleCreateRequest(BaseModel):
    """新建定时发布规则请求。"""

    rule_name: str = Field(..., min_length=1, max_length=120)
    account_ids: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        ...,
        min_length=1,
        max_length=5000,
    )
    material_ids: list[Annotated[int, Field(gt=0)]] = Field(
        ...,
        min_length=1,
        max_length=2000,
    )
    trigger_start_time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    trigger_end_time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    interval_min_minutes: int = Field(..., ge=1, le=43200)
    interval_max_minutes: int = Field(..., ge=1, le=43200)


class ScheduledPublishTriggerDeleteRequest(BaseModel):
    """单条或批量删除定时发布触发记录请求。"""

    ids: list[Annotated[int, Field(gt=0)]] = Field(..., min_length=1, max_length=500)


@router.get("/options", response_model=ApiResponse)
async def list_scheduled_publish_options(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """查询当前用户的新建规则可选账号和素材。"""
    data = await ScheduledPublishRuleService(session).list_options(current_user.id)
    return ApiResponse(success=True, message="选项查询成功", data=data)


@router.get("", response_model=ApiResponse)
async def list_scheduled_publish_rules(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    keyword: str | None = Query(None, max_length=120, description="规则名称关键词"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """分页查询当前用户的定时发布规则。"""
    data = await ScheduledPublishRuleService(session).list_rules(
        owner_id=current_user.id,
        page=page,
        page_size=page_size,
        keyword=keyword,
    )
    return ApiResponse(success=True, message="定时发布规则查询成功", data=data)


@router.post("", response_model=ApiResponse)
async def create_scheduled_publish_rule(
    request: ScheduledPublishRuleCreateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """保存当前用户的新定时发布规则。"""
    try:
        rule = await ScheduledPublishRuleService(session).create(
            current_user.id,
            request.model_dump(),
        )
    except ScheduledPublishRuleValidationError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc), data=None)
    return ApiResponse(
        success=True,
        message="定时发布规则创建成功",
        data={"id": rule.id},
    )


@router.put("/{rule_id}", response_model=ApiResponse)
async def update_scheduled_publish_rule(
    rule_id: int,
    request: ScheduledPublishRuleCreateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """修改当前用户的定时发布规则。"""
    try:
        rule = await ScheduledPublishRuleService(session).update(
            current_user.id,
            rule_id,
            request.model_dump(),
        )
    except ScheduledPublishRuleValidationError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc), data=None)
    return ApiResponse(
        success=True,
        message="定时发布规则修改成功",
        data={"id": rule.id},
    )


@router.get("/{rule_id}/publish-records", response_model=ApiResponse)
async def list_scheduled_publish_records(
    rule_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """分页查询指定规则的发布记录。"""
    try:
        data = await ScheduledPublishRecordService(session).list_publish_records(
            current_user.id, rule_id, page, page_size
        )
    except ScheduledPublishRuleValidationError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc), data=None)
    return ApiResponse(success=True, message="定时发布记录查询成功", data=data)


@router.get("/{rule_id}/trigger-records", response_model=ApiResponse)
async def list_scheduled_publish_trigger_records(
    rule_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """分页查询指定规则的触发记录。"""
    try:
        data = await ScheduledPublishRecordService(session).list_trigger_records(
            current_user.id, rule_id, page, page_size
        )
    except ScheduledPublishRuleValidationError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc), data=None)
    return ApiResponse(success=True, message="定时发布触发记录查询成功", data=data)


@router.post("/{rule_id}/trigger-records/batch-delete", response_model=ApiResponse)
async def delete_scheduled_publish_trigger_records(
    rule_id: int,
    request: ScheduledPublishTriggerDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """单条或批量软删除指定规则的触发记录。"""
    try:
        data = await ScheduledPublishRecordService(session).delete_trigger_records(
            current_user.id,
            rule_id,
            request.ids,
        )
    except ScheduledPublishRuleValidationError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc), data=None)
    return ApiResponse(
        success=True,
        message=f"成功删除 {data['success_count']} 条触发记录",
        data=data,
    )
