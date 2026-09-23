"""
AI 铺货 API 路由

功能：
1. AI 铺货配置管理（分页查询、新增、编辑、软删除、连通性测试、模型列表）
2. AI 铺货任务管理（启动、进度/详情查询、历史列表、取消）

接口规范：
- 统一返回 ApiResponse（success/message/data），业务错误固定返回 HTTP 200
- 所有数据按登录用户隔离，SQL 一律走 service 层
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from app.api.routes.external_api_route import ExternalApiRoute
from app.services.ai_listing_config_service import AiListingConfigService
from app.services.ai_listing_runner import run_ai_listing_task
from app.services.ai_listing_task_service import (
    MAX_ACTIVE_TASKS_PER_USER,
    AiListingTaskService,
    item_to_dict,
    task_to_dict,
)
from common.models.user import User
from common.schemas.ai_listing import (
    AiListingConfigRequest,
    AiListingModelListRequest,
    AiListingTaskCreateRequest,
)
from common.schemas.common import ApiResponse
from common.services.ai_provider_service import fetch_ai_model_list
from common.services.ai_text_client import AiCallError, chat_completion

router = APIRouter(
    prefix="/ai-listing",
    tags=["AI铺货"],
    # 请求校验失败也统一返回 HTTP 200 + 业务错误响应。
    route_class=ExternalApiRoute,
)


def _error_text(exc: Exception, fallback: str) -> str:
    """从异常里取出可展示给用户的中文消息"""
    message = getattr(exc, "message", None) or str(exc)
    return message.strip() or fallback


# ==================== 配置管理 ====================


@router.get("/configs", response_model=ApiResponse)
async def list_configs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    name: Optional[str] = Query(None, max_length=80, description="配置名称模糊搜索"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """分页查询当前用户的 AI 铺货配置（密钥已脱敏）"""
    data = await AiListingConfigService(session).list_configs(
        current_user.id, page=page, page_size=page_size, name=name
    )
    return ApiResponse(success=True, data=data)


@router.post("/configs", response_model=ApiResponse)
async def create_config(
    req: AiListingConfigRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """新增 AI 铺货配置"""
    if not req.text_api_key.strip():
        return ApiResponse(success=False, message="请填写文案接口密钥")
    if req.image_enabled and not req.image_api_key.strip():
        return ApiResponse(success=False, message="启用AI图片生成时请填写图片接口密钥")

    config = await AiListingConfigService(session).create(current_user.id, req.model_dump())
    return ApiResponse(success=True, message="配置已保存", data={"id": config.id})


@router.put("/configs/{config_id}", response_model=ApiResponse)
async def update_config(
    config_id: int,
    req: AiListingConfigRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """编辑 AI 铺货配置（密钥留空表示不修改）"""
    service = AiListingConfigService(session)
    existing = await service.get(config_id, current_user.id)
    if not existing:
        return ApiResponse(success=False, message="配置不存在")
    if req.image_enabled and not (req.image_api_key.strip() or (existing.image_api_key or "").strip()):
        return ApiResponse(success=False, message="启用AI图片生成时请填写图片接口密钥")

    config = await service.update(config_id, current_user.id, req.model_dump())
    if not config:
        return ApiResponse(success=False, message="配置不存在")
    return ApiResponse(success=True, message="配置已更新", data={"id": config.id})


@router.delete("/configs/{config_id}", response_model=ApiResponse)
async def delete_config(
    config_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """删除 AI 铺货配置（软删除，历史任务仍可回查配置名称）"""
    deleted = await AiListingConfigService(session).delete(config_id, current_user.id)
    if not deleted:
        return ApiResponse(success=False, message="配置不存在")
    return ApiResponse(success=True, message="配置已删除")


@router.post("/configs/models", response_model=ApiResponse)
async def list_provider_models(
    req: AiListingModelListRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """拉取服务商可用模型列表（供配置表单的模型下拉使用）

    密钥优先用请求里填的；留空且带 config_id 时复用已保存配置的密钥，
    这样编辑配置时前端不需要回传明文密钥。
    """
    api_key = req.api_key.strip()
    if not api_key and req.config_id:
        config = await AiListingConfigService(session).get(req.config_id, current_user.id)
        if config:
            api_key = (config.text_api_key or "").strip()
    if not api_key:
        return ApiResponse(success=False, message="请先填写接口密钥")

    try:
        models = await fetch_ai_model_list(req.provider_type, req.base_url, api_key)
    except Exception as exc:
        logger.warning(f"【AI铺货】拉取模型列表失败 user={current_user.id}：{exc}")
        return ApiResponse(success=False, message=_error_text(exc, "拉取模型列表失败"))
    return ApiResponse(success=True, data={"models": models})


@router.post("/configs/{config_id}/test", response_model=ApiResponse)
async def test_config(
    config_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """测试文案接口连通性（用已保存的配置发一条最短请求）"""
    config = await AiListingConfigService(session).get(config_id, current_user.id)
    if not config:
        return ApiResponse(success=False, message="配置不存在")

    try:
        reply = await chat_completion(
            base_url=config.text_base_url,
            api_key=config.text_api_key,
            model=config.text_model,
            messages=[{"role": "user", "content": "你好，请只回复：连接成功"}],
            temperature=0,
            max_tokens=64,
        )
    except Exception as exc:
        logger.warning(f"【AI铺货】配置连通性测试失败 config={config_id}：{exc}")
        return ApiResponse(success=False, message=_error_text(exc, "连接失败"))
    return ApiResponse(success=True, message="连接成功", data={"reply": reply[:200]})


# ==================== 任务管理 ====================


def _resolve_task_image_enabled(config: Any, req: AiListingTaskCreateRequest) -> bool:
    """确定本次任务是否生成图片（任务参数可覆盖配置开关，缺配置则视为不启用）"""
    enabled = bool(config.image_enabled) if req.image_enabled is None else bool(req.image_enabled)
    if not enabled:
        return False
    return bool(
        (config.image_base_url or "").strip()
        and (config.image_model or "").strip()
        and (config.image_api_key or "").strip()
    )


@router.post("/tasks", response_model=ApiResponse)
async def create_task(
    req: AiListingTaskCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """启动一个 AI 铺货任务（后台执行，进度落库）"""
    config = await AiListingConfigService(session).get(req.config_id, current_user.id)
    if not config:
        return ApiResponse(success=False, message="AI铺货配置不存在，请先新增配置")

    image_enabled = _resolve_task_image_enabled(config, req)
    if not image_enabled and not req.material_defaults.images:
        return ApiResponse(
            success=False,
            message="未启用AI图片生成时，请至少提供1张兜底图片（素材必须有图片才能发布）",
        )

    task_id = str(uuid.uuid4())
    params: Dict[str, Any] = {
        "price_mode": req.price_mode,
        "price": req.price,
        "price_min": req.price_min,
        "price_max": req.price_max,
        "image_enabled": image_enabled,
        "material_defaults": req.material_defaults.model_dump(),
    }
    task_service = AiListingTaskService(session)
    task = await task_service.create_task(
        owner_id=current_user.id,
        task_id=task_id,
        config=config,
        keyword=req.keyword.strip(),
        total_count=req.count,
        params=params,
        max_active_tasks=MAX_ACTIVE_TASKS_PER_USER,
    )
    if task is None:
        return ApiResponse(
            success=False,
            message=f"最多同时运行 {MAX_ACTIVE_TASKS_PER_USER} 个铺货任务，请等待当前任务结束或先取消",
        )

    background_tasks.add_task(run_ai_listing_task, task_id)
    logger.info(
        f"【AI铺货】已创建任务 task={task_id} user={current_user.id} 条数={req.count} 图片={image_enabled}"
    )
    return ApiResponse(
        success=True,
        message="任务已开始执行",
        data={"task_id": task_id, "total": req.count, "image_enabled": image_enabled},
    )


@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, max_length=20, description="按状态过滤"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """分页查询当前用户的 AI 铺货任务历史"""
    data = await AiListingTaskService(session).list_tasks(
        current_user.id, page=page, page_size=page_size, status=status
    )
    return ApiResponse(success=True, data=data)


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """查询单个任务的进度与明细（供前端轮询）"""
    service = AiListingTaskService(session)
    task = await service.get_task(task_id, current_user.id)
    if not task:
        return ApiResponse(success=False, message="任务不存在")

    items = await service.list_items(task_id)
    data = task_to_dict(task)
    data["items"] = [item_to_dict(item) for item in items]
    return ApiResponse(success=True, data=data)


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """取消任务（执行器会在下一条开始前停止，已生成的素材保留）"""
    canceled = await AiListingTaskService(session).cancel_task(task_id, current_user.id)
    if not canceled:
        return ApiResponse(success=False, message="任务不存在或已结束")
    return ApiResponse(success=True, message="任务已取消")


