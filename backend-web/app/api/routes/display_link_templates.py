"""通用展示入口模板 - 管理接口（用户级）

- GET    /display-link-templates                     列表（按 id 升序）
- POST   /display-link-templates                     新建
- PUT    /display-link-templates/{template_id}       部分更新（type 变更时按新类型重校验并清空不适用字段）
- DELETE /display-link-templates/{template_id}       删除
- POST   /display-link-templates/upload-image        模板图片上传

存储：xy_display_link_templates（按登录用户 id 隔离）

模板归属固定取当前登录用户 id：管理员同样存到自身 user_id 下。
这里不能用 resolve_owner_scope —— 它对管理员返回 owner_id=None，会导致新建写入 NULL（NOT NULL 报错）
且列表/更新/删除全部查不到数据；提货页是按商品 order.owner_id 读取默认模板的，
所以管理员（生产环境唯一用户）创建的模板必须落在自己的 user_id 上才能被读到。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.paths import STATIC_ROOT
from app.services.display_link_service import (
    template_row_to_entry,
    validate_display_link_entry,
)
from common.models.display_link_template import DisplayLinkTemplate
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
from pydantic import BaseModel

router = APIRouter(prefix="/display-link-templates", tags=["通用展示入口"])

TEMPLATE_UPLOAD_DIR = STATIC_ROOT / "uploads" / "display_links"


class TemplateSaveRequest(BaseModel):
    """新建/更新通用展示入口模板（PUT 为部分更新语义）"""

    name: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    is_default: Optional[bool] = None


def _apply_entry_to_row(row: DisplayLinkTemplate, entry: dict) -> None:
    """把校验后的条目写回模型行；先清空三类字段避免类型切换残留。"""
    row.name = entry["name"]
    row.type = entry["type"]
    row.url = entry.get("url")
    row.note = entry.get("note")
    row.title = entry.get("title")
    row.content = entry.get("content")


@router.get("", response_model=ApiResponse)
async def list_templates(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id = current_user.id
    stmt = select(DisplayLinkTemplate).where(DisplayLinkTemplate.user_id == owner_id).order_by(DisplayLinkTemplate.id)
    rows = (await session.execute(stmt)).scalars().all()
    return ApiResponse(
        success=True,
        message="获取通用展示入口成功",
        data={
            "templates": [
                {**template_row_to_entry(r), "id": r.id, "is_default": bool(r.is_default)}
                for r in rows
            ]
        },
    )


@router.post("", response_model=ApiResponse)
async def create_template(
    payload: TemplateSaveRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id = current_user.id
    ok, message, entry = validate_display_link_entry(payload.model_dump(exclude_none=True))
    if not ok:
        return ApiResponse(success=False, message=message, data=None)
    row = DisplayLinkTemplate(user_id=owner_id, is_default=bool(payload.is_default))
    _apply_entry_to_row(row, entry)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ApiResponse(
        success=True,
        message="创建成功",
        data={**template_row_to_entry(row), "id": row.id, "is_default": bool(row.is_default)},
    )


@router.put("/{template_id}", response_model=ApiResponse)
async def update_template(
    template_id: int,
    payload: TemplateSaveRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id = current_user.id
    row = (
        await session.execute(
            select(DisplayLinkTemplate).where(
                DisplayLinkTemplate.id == template_id,
                DisplayLinkTemplate.user_id == owner_id,
            )
        )
    ).scalars().first()
    if not row:
        return ApiResponse(success=False, message="模板不存在", data=None)

    provided = payload.model_dump(exclude_none=True)
    # 合并现有值后整体校验：保证「部分更新」也不会产生非法组合
    merged = {
        "name": provided.get("name", row.name),
        "type": provided.get("type", row.type),
        "url": provided.get("url", row.url),
        "note": provided.get("note", row.note),
        "title": provided.get("title", row.title),
        "content": provided.get("content", row.content),
    }
    ok, message, entry = validate_display_link_entry(merged)
    if not ok:
        return ApiResponse(success=False, message=message, data=None)
    _apply_entry_to_row(row, entry)
    if "is_default" in provided:
        row.is_default = bool(provided["is_default"])
    await session.commit()
    await session.refresh(row)
    return ApiResponse(
        success=True,
        message="更新成功",
        data={**template_row_to_entry(row), "id": row.id, "is_default": bool(row.is_default)},
    )


@router.delete("/{template_id}", response_model=ApiResponse)
async def delete_template(
    template_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id = current_user.id
    row = (
        await session.execute(
            select(DisplayLinkTemplate).where(
                DisplayLinkTemplate.id == template_id,
                DisplayLinkTemplate.user_id == owner_id,
            )
        )
    ).scalars().first()
    if not row:
        return ApiResponse(success=False, message="模板不存在", data=None)
    await session.delete(row)
    await session.commit()
    return ApiResponse(success=True, message="删除成功", data=None)


@router.post("/upload-image")
async def upload_template_image(
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    """上传通用展示入口图片，返回可访问的静态资源 URL"""
    try:
        _, filename, _ = await save_uploaded_image(
            image,
            TEMPLATE_UPLOAD_DIR,
            filename_prefix="tpl",
            short_uuid=True,
        )
    except ImageUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"success": True, "image_url": f"/static/uploads/display_links/{filename}"}
