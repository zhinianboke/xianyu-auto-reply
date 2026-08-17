"""
公开商品发布接口。

功能：
1. 通过分销秘钥和指定闲鱼账号接收发布媒体，不需要系统登录。
2. 使用公开媒体 ID 组装与单品发布一致的接口发布载荷。
3. 严格限制商品只能发布到秘钥所属且调用方指定的账号。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.routes.external_api_route import ExternalApiRoute
from app.api.routes.external_shared import (
    ExternalApiResponse,
    external_error,
    normalize_text,
    resolve_external_account,
    validate_identity_fields,
)
from app.services.external_publish_media_service import (
    ExternalPublishMediaError,
    ExternalPublishMediaService,
)
from app.services.publish_execution_service import PublishExecutorService
from common.models.xy_account import XYAccount


router = APIRouter(
    prefix="/external/publish",
    tags=["公开商品发布"],
    route_class=ExternalApiRoute,
)


class ExternalPlatformAttributeRequest(BaseModel):
    """公开发布请求中的平台属性。"""

    property_id: str | None = Field(default=None, max_length=64)
    property_name: str | None = Field(default=None, max_length=100)
    value_id: str | None = Field(default=None, max_length=64)
    value_name: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=200)
    properties: str | None = Field(default=None, max_length=500)


class ExternalSpecificationValueRequest(BaseModel):
    """公开发布请求中的规格值。"""

    name: str = Field(..., min_length=1, max_length=100)
    image_media_id: str | None = Field(default=None, max_length=80)


class ExternalSpecificationRequest(BaseModel):
    """公开发布请求中的规格定义。"""

    name: str = Field(..., min_length=1, max_length=100)
    values: list[ExternalSpecificationValueRequest] = Field(default_factory=list, max_length=50)
    support_image: bool = False


class ExternalSkuRowRequest(BaseModel):
    """公开发布请求中的 SKU 价格和库存。"""

    specs: dict[str, str] = Field(default_factory=dict, max_length=4)
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0, le=999999)


class ExternalPublishSingleRequest(BaseModel):
    """公开单品接口发布请求。"""

    secret_key: str | None = None
    account_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1500)
    price: float | None = Field(default=None, gt=0)
    original_price: float | None = Field(default=None, gt=0)
    image_media_ids: list[str] = Field(default_factory=list, min_length=1, max_length=9)
    video_media_ids: list[str] = Field(default_factory=list, max_length=3)
    platform_category_id: str | None = Field(default=None, max_length=64)
    platform_category_name: str | None = Field(default=None, max_length=100)
    platform_channel_category_id: str | None = Field(default=None, max_length=64)
    platform_channel_category_name: str | None = Field(default=None, max_length=100)
    platform_leaf_id: str | None = Field(default=None, max_length=64)
    platform_tb_category_id: str | None = Field(default=None, max_length=64)
    platform_attributes: list[ExternalPlatformAttributeRequest] = Field(default_factory=list, max_length=30)
    quantity: int = Field(default=1, ge=1, le=999999)
    specifications: list[ExternalSpecificationRequest] = Field(default_factory=list, max_length=2)
    sku_rows: list[ExternalSkuRowRequest] = Field(default_factory=list, max_length=200)
    address: str | None = Field(default=None, max_length=200)
    address_expected_text: str | None = Field(default=None, max_length=200)
    shipping_method: str = Field(default="free", pattern="^(free|none)$")


def _build_publish_item_data(
    payload: ExternalPublishSingleRequest,
    account: XYAccount,
) -> dict[str, Any]:
    """
    将公开请求转换为现有单品发布执行服务使用的数据结构。

    Args:
        payload: 公开发布请求。
        account: 已校验归属的闲鱼账号。
    Returns:
        现有单品发布服务所需的商品数据。
    Raises:
        ExternalPublishMediaError: media_id 不存在、类型不符或账号归属不符时抛出。
    """
    media_service = ExternalPublishMediaService()
    images = media_service.resolve_media_list(account, payload.image_media_ids, "image")
    video_paths = media_service.resolve_media_list(account, payload.video_media_ids, "video")
    videos = [
        {
            "path": media_path,
            "name": media_id,
        }
        for media_id, media_path in zip(payload.video_media_ids, video_paths, strict=True)
    ]
    specifications: list[dict[str, Any]] = []
    for specification in payload.specifications:
        values: list[dict[str, str]] = []
        for value in specification.values:
            item: dict[str, str] = {"name": value.name.strip()}
            if normalize_text(value.image_media_id):
                item["image"] = media_service.resolve_media(
                    account,
                    normalize_text(value.image_media_id),
                    "spec_image",
                )
            values.append(item)
        specifications.append(
            {
                "name": specification.name.strip(),
                "support_image": specification.support_image,
                "values": values,
            }
        )

    return {
        "title": normalize_text(payload.title),
        "description": normalize_text(payload.description),
        "price": payload.price,
        "original_price": payload.original_price,
        "images": images,
        "videos": videos,
        "platform_category_id": normalize_text(payload.platform_category_id),
        "platform_category_name": normalize_text(payload.platform_category_name),
        "platform_channel_category_id": normalize_text(payload.platform_channel_category_id),
        "platform_channel_category_name": normalize_text(payload.platform_channel_category_name),
        "platform_leaf_id": normalize_text(payload.platform_leaf_id),
        "platform_tb_category_id": normalize_text(payload.platform_tb_category_id),
        "platform_attributes": [item.model_dump() for item in payload.platform_attributes],
        "quantity": payload.quantity,
        "specifications": specifications,
        "sku_rows": [item.model_dump() for item in payload.sku_rows],
        "address": normalize_text(payload.address),
        "address_expected_text": normalize_text(payload.address_expected_text),
        "shipping_method": payload.shipping_method,
    }


@router.post("/media", response_model=ExternalApiResponse)
async def upload_external_publish_media(
    secret_key: str | None = Form(default=None),
    account_id: str | None = Form(default=None),
    media_type: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """
    上传公开接口发布所需的一份媒体文件。

    Args:
        secret_key: 个人设置-分销管理中的分销秘钥。
        account_id: 用于最终发布的闲鱼账号 ID。
        media_type: image、spec_image 或 video。
        file: 单个媒体文件。
        session: 数据库会话。
    Returns:
        含 media_id 的统一响应，发布时只能引用同账号下的 media_id。
    """
    normalized_secret, normalized_account_id, error = validate_identity_fields(secret_key, account_id)
    if error:
        return error
    if not normalize_text(media_type):
        return external_error(40007, "media_type不能为空")
    if file is None or not file.filename:
        return external_error(40007, "请选择要上传的媒体文件")

    account, error = await resolve_external_account(
        session,
        normalized_secret,
        normalized_account_id,
        "公开发布",
    )
    if error:
        return error
    try:
        data = await ExternalPublishMediaService().save_media(account, normalize_text(media_type), file)
    except ExternalPublishMediaError as exc:
        return external_error(40007, str(exc))
    return ExternalApiResponse(
        success=True,
        message="媒体上传成功",
        data=data,
        code=200,
    )


@router.post("/single", response_model=ExternalApiResponse)
async def publish_external_single(
    payload: ExternalPublishSingleRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """
    使用公开接口上传的媒体和指定账号执行一次闲鱼接口发布。

    Args:
        payload: 商品、分类、属性、规格、媒体和所在地数据。
        session: 数据库会话。
    Returns:
        含商品 ID、商品链接、发布日志和同步结果的统一响应。
    """
    if payload is None:
        return external_error(40008, "请求参数不能为空")
    normalized_secret, normalized_account_id, error = validate_identity_fields(
        payload.secret_key,
        payload.account_id,
    )
    if error:
        return error
    if not normalize_text(payload.title):
        return external_error(40008, "商品标题不能为空")
    if not normalize_text(payload.description):
        return external_error(40008, "商品描述不能为空")
    if payload.price is None:
        return external_error(40008, "商品售价不能为空")
    if not normalize_text(payload.address):
        return external_error(40008, "宝贝所在地不能为空，请传入外部系统已选择的地址关键词")

    account, error = await resolve_external_account(
        session,
        normalized_secret,
        normalized_account_id,
        "公开发布",
    )
    if error:
        return error
    try:
        item_data = _build_publish_item_data(payload, account)
    except ExternalPublishMediaError as exc:
        return external_error(40007, str(exc))

    try:
        result = await PublishExecutorService(session).publish_single(
            user_id=account.owner_id,
            account_id=account.account_id,
            item_data=item_data,
        )
    except Exception as exc:
        logger.error(
            f"公开单品发布执行异常: owner_id={account.owner_id}, "
            f"account_id={account.account_id}, error={exc}"
        )
        return external_error(40009, "商品发布失败，请稍后重试")
    return ExternalApiResponse(
        success=bool(result.get("success")),
        code=200 if result.get("success") else 40009,
        message=result.get("message") or "商品发布失败",
        data={
            "item_url": result.get("item_url"),
            "item_id": result.get("item_id"),
            "log_id": result.get("log_id"),
            "sync_status": result.get("sync_status"),
            "sync_message": result.get("sync_message"),
            "sync_total_count": result.get("sync_total_count"),
            "sync_saved_count": result.get("sync_saved_count"),
        },
    )


__all__ = ["router"]
