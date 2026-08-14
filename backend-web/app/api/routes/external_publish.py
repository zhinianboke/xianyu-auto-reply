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
from app.services.external_account_service import (
    ExternalAccountAccessError,
    ExternalAccountService,
)
from app.services.external_publish_media_service import (
    ExternalPublishMediaError,
    ExternalPublishMediaService,
)
from app.services.publish_execution_service import PublishExecutorService
from common.models.xy_account import XYAccount
from common.schemas.common import ApiResponse


router = APIRouter(
    prefix="/external/publish",
    tags=["公开商品发布"],
    route_class=ExternalApiRoute,
)


class ExternalPublishResponse(ApiResponse):
    """公开商品发布统一响应。"""

    code: int


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


def _text(value: str | None) -> str:
    """规范化可空文本字段。"""
    return (value or "").strip()


def _validate_common_fields(
    secret_key: str | None,
    account_id: str | None,
) -> tuple[str, str, ExternalPublishResponse | None]:
    """校验公开媒体和发布接口共有的身份字段。"""
    normalized_secret = _text(secret_key)
    normalized_account_id = _text(account_id)
    if not normalized_secret:
        return "", "", ExternalPublishResponse(
            success=False,
            message="秘钥不能为空",
            data=None,
            code=40001,
        )
    if len(normalized_secret) > 128:
        return "", "", ExternalPublishResponse(
            success=False,
            message="秘钥长度不能超过128位",
            data=None,
            code=40001,
        )
    if not normalized_account_id:
        return "", "", ExternalPublishResponse(
            success=False,
            message="闲鱼账号ID不能为空",
            data=None,
            code=40002,
        )
    if len(normalized_account_id) > 80:
        return "", "", ExternalPublishResponse(
            success=False,
            message="闲鱼账号ID长度不能超过80位",
            data=None,
            code=40002,
        )
    return normalized_secret, normalized_account_id, None


async def _get_external_account(
    session: AsyncSession,
    secret_key: str,
    account_id: str,
) -> tuple[XYAccount | None, ExternalPublishResponse | None]:
    """获取经秘钥验证后的指定闲鱼账号。"""
    try:
        account = await ExternalAccountService(session).get_enabled_account_by_secret(
            secret_key,
            account_id,
        )
        return account, None
    except ExternalAccountAccessError as exc:
        return None, ExternalPublishResponse(
            success=False,
            message=exc.message,
            data=None,
            code=exc.code,
        )
    except Exception as exc:
        logger.error(f"公开发布账号校验异常: account_id={account_id}, error={exc}")
        return None, ExternalPublishResponse(
            False,
            "账号信息查询失败，请稍后重试",
            None,
            code=50001,
        )


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
            if _text(value.image_media_id):
                item["image"] = media_service.resolve_media(
                    account,
                    _text(value.image_media_id),
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
        "title": _text(payload.title),
        "description": _text(payload.description),
        "price": payload.price,
        "original_price": payload.original_price,
        "images": images,
        "videos": videos,
        "platform_category_id": _text(payload.platform_category_id),
        "platform_category_name": _text(payload.platform_category_name),
        "platform_channel_category_id": _text(payload.platform_channel_category_id),
        "platform_channel_category_name": _text(payload.platform_channel_category_name),
        "platform_leaf_id": _text(payload.platform_leaf_id),
        "platform_tb_category_id": _text(payload.platform_tb_category_id),
        "platform_attributes": [item.model_dump() for item in payload.platform_attributes],
        "quantity": payload.quantity,
        "specifications": specifications,
        "sku_rows": [item.model_dump() for item in payload.sku_rows],
        "address": _text(payload.address),
        "address_expected_text": _text(payload.address_expected_text),
        "shipping_method": payload.shipping_method,
    }


@router.post("/media", response_model=ExternalPublishResponse)
async def upload_external_publish_media(
    secret_key: str | None = Form(default=None),
    account_id: str | None = Form(default=None),
    media_type: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalPublishResponse:
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
    normalized_secret, normalized_account_id, error = _validate_common_fields(secret_key, account_id)
    if error:
        return error
    if not _text(media_type):
        return ExternalPublishResponse(
            success=False,
            message="media_type不能为空",
            data=None,
            code=40007,
        )
    if file is None or not file.filename:
        return ExternalPublishResponse(
            success=False,
            message="请选择要上传的媒体文件",
            data=None,
            code=40007,
        )

    account, error = await _get_external_account(session, normalized_secret, normalized_account_id)
    if error:
        return error
    try:
        data = await ExternalPublishMediaService().save_media(account, _text(media_type), file)
    except ExternalPublishMediaError as exc:
        return ExternalPublishResponse(
            success=False,
            message=str(exc),
            data=None,
            code=40007,
        )
    return ExternalPublishResponse(
        success=True,
        message="媒体上传成功",
        data=data,
        code=200,
    )


@router.post("/single", response_model=ExternalPublishResponse)
async def publish_external_single(
    payload: ExternalPublishSingleRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalPublishResponse:
    """
    使用公开接口上传的媒体和指定账号执行一次闲鱼接口发布。

    Args:
        payload: 商品、分类、属性、规格、媒体和所在地数据。
        session: 数据库会话。
    Returns:
        含商品 ID、商品链接、发布日志和同步结果的统一响应。
    """
    if payload is None:
        return ExternalPublishResponse(
            success=False,
            message="请求参数不能为空",
            data=None,
            code=40008,
        )
    normalized_secret, normalized_account_id, error = _validate_common_fields(
        payload.secret_key,
        payload.account_id,
    )
    if error:
        return error
    if not _text(payload.title):
        return ExternalPublishResponse(
            success=False,
            message="商品标题不能为空",
            data=None,
            code=40008,
        )
    if not _text(payload.description):
        return ExternalPublishResponse(
            success=False,
            message="商品描述不能为空",
            data=None,
            code=40008,
        )
    if payload.price is None:
        return ExternalPublishResponse(
            success=False,
            message="商品售价不能为空",
            data=None,
            code=40008,
        )
    if not _text(payload.address):
        return ExternalPublishResponse(
            success=False,
            message="宝贝所在地不能为空，请传入外部系统已选择的地址关键词",
            data=None,
            code=40008,
        )

    account, error = await _get_external_account(session, normalized_secret, normalized_account_id)
    if error:
        return error
    try:
        item_data = _build_publish_item_data(payload, account)
    except ExternalPublishMediaError as exc:
        return ExternalPublishResponse(
            success=False,
            message=str(exc),
            data=None,
            code=40007,
        )

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
        return ExternalPublishResponse(
            success=False,
            code=40009,
            message="商品发布失败，请稍后重试",
            data=None,
        )
    return ExternalPublishResponse(
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
