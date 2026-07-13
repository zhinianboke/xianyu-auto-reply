"""卡券管理路由"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
from app.services.card_service import CardService
from app.services.selectable_card_service import SelectableCardService

router = APIRouter(tags=["cards"])

# 卡券图片上传目录 - 使用统一的静态文件根目录（兼容Docker共享卷）
from app.core.paths import STATIC_ROOT
CARD_UPLOAD_DIR = STATIC_ROOT / "uploads" / "cards"
CARD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class CardCreate(BaseModel):
    item_id: Optional[str] = None  # 关联商品ID
    name: str
    type: str  # 'api' | 'text' | 'data' | 'image'
    description: Optional[str] = None
    enabled: Optional[bool] = True
    delay_seconds: Optional[int] = 0
    price: Optional[str] = None  # 对接价格
    is_dockable: Optional[bool] = False  # 是否可对接
    fee_payer: Optional[str] = None  # 手续费支付方式：distributor/dealer
    min_price: Optional[str] = None  # 最低售价
    dock_visibility: Optional[str] = None  # 对接可见性：public/dealer_only
    is_multi_spec: Optional[bool] = False
    spec_name: Optional[str] = None
    spec_value: Optional[str] = None
    api_config: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None
    data_content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None  # 多图片URL列表，最多3张


class CardUpdate(BaseModel):
    item_id: Optional[str] = None  # 关联商品ID
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    delay_seconds: Optional[int] = None
    price: Optional[str] = None  # 对接价格
    is_dockable: Optional[bool] = None  # 是否可对接
    fee_payer: Optional[str] = None  # 手续费支付方式：distributor/dealer
    min_price: Optional[str] = None  # 最低售价
    dock_visibility: Optional[str] = None  # 对接可见性：public/dealer_only
    is_multi_spec: Optional[bool] = None
    spec_name: Optional[str] = None
    spec_value: Optional[str] = None
    api_config: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None
    data_content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None  # 多图片URL列表，最多3张


class BatchDeleteRequest(BaseModel):
    ids: List[int]


class BatchSaveCardRequest(BaseModel):
    """批量保存卡券请求"""
    item_ids: List[str]
    name: str
    type: str
    description: Optional[str] = None
    enabled: Optional[bool] = True
    delay_seconds: Optional[int] = 0
    price: Optional[str] = None  # 对接价格
    is_dockable: Optional[bool] = False  # 是否可对接
    fee_payer: Optional[str] = None  # 手续费支付方式：distributor/dealer
    min_price: Optional[str] = None  # 最低售价
    dock_visibility: Optional[str] = None  # 对接可见性：public/dealer_only
    is_multi_spec: Optional[bool] = False
    spec_name: Optional[str] = None
    spec_value: Optional[str] = None
    api_config: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None
    data_content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None  # 多图片URL列表，最多3张


class BatchClearItemRelationsRequest(BaseModel):
    """批量清空商品的卡券关联关系"""
    item_ids: List[str]


class BatchBindRequest(BaseModel):
    """批量绑定卡券到商品（多对多关联表方式）"""
    card_ids: List[int]
    item_ids: List[str]


class UpdateCardItemsRequest(BaseModel):
    """更新卡券关联的商品列表"""
    item_ids: List[str]


class CardRelationItem(BaseModel):
    """单条卡券关联信息"""
    card_id: int
    source: str = "own"  # own/dock_l1/dock_l2
    dock_record_id: Optional[int] = None

class UpdateItemCardsRequest(BaseModel):
    """更新商品关联的卡券列表"""
    card_items: List[CardRelationItem]


async def get_card_service(session: AsyncSession = Depends(deps.get_db_session)) -> CardService:
    return CardService(session)


def _validate_card_payload(data: Any, *, validate_fee_payer: bool = True) -> Optional[str]:
    """校验卡券请求负载的公共逻辑。

    被 create_card / update_card / batch_save_card 三处共用，避免多处重复
    书写多规格、图片数量、手续费支付方式三块同样的校验代码。

    Args:
        data: ``CardCreate`` / ``CardUpdate`` / ``BatchSaveCardRequest`` 实例，
            需拥有 ``is_multi_spec`` / ``spec_name`` / ``spec_value`` /
            ``image_urls`` / ``is_dockable`` / ``fee_payer`` 这些字段。
        validate_fee_payer: 是否对 ``is_dockable`` 与 ``fee_payer`` 执行校验。
            默认开启；批量保存接口历史上不做该校验，由调用方传 ``False``
            以保持原有行为，避免意外重收紧。

    Returns:
        首个不通过项的中文错误消息，可直接作为 HTTPException ``detail`` 或
        ApiResponse ``message``；全部通过返回 ``None``。
    """
    if data.is_multi_spec:
        if not data.spec_name or not data.spec_value:
            return "多规格卡券必须提供规格名称和规格值"

    if data.image_urls and len(data.image_urls) > 3:
        return "最多只能上传3张图片"

    if validate_fee_payer:
        if data.is_dockable and not data.fee_payer:
            return "勾选可对接时，手续费支付方式必选"
        if data.fee_payer and data.fee_payer not in ('distributor', 'dealer'):
            return "手续费支付方式无效"

    return None


@router.get("")
async def get_cards(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=9999, description="每页数量"),
    search: str = Query(default="", description="搜索关键词（名称或描述）"),
    card_type: str = Query(default="", alias="type", description="卡券类型过滤"),
    lite: bool = Query(default=False, description="轻量模式：仅返回列表所需字段，剔除卡密/文本等大字段"),
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """获取卡券列表（分页），管理员可查看所有卡券"""
    user_id, _ = resolve_owner_scope(current_user)
    result = await card_service.get_cards_paginated(
        user_id=user_id,
        page=page,
        page_size=page_size,
        search=search,
        card_type=card_type,
        lite=lite,
    )
    return result


@router.get("/item/{item_id}")
async def get_cards_by_item(
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """获取指定商品的卡券列表，管理员可查看所有"""
    user_id, _ = resolve_owner_scope(current_user)
    cards = await card_service.get_cards_by_item_id(user_id, item_id)
    return cards


@router.get("/selectable")
async def get_selectable_cards(
    item_id: str = Query(..., description="商品ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页数量"),
    search: str = Query(default="", description="搜索关键词（名称/类型/ID/对接名称）"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """商品关联卡券选择弹窗：合并分页获取可选卡券（自有 + 对接），管理员可查看所有

    注意：本路由必须定义在 `GET /{card_id}` 之前，否则 "selectable" 会被
    当作 card_id 解析。
    """
    user_id, _ = resolve_owner_scope(current_user)
    service = SelectableCardService(session)
    return await service.get_selectable_cards_paginated(
        item_id=item_id,
        user_id=user_id,
        page=page,
        page_size=page_size,
        search=search,
    )


@router.get("/selectable/all")
async def get_all_selectable_cards(
    search: str = Query(default="", description="搜索关键词（名称/类型/ID/对接名称）"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """商品关联卡券选择弹窗：获取全部匹配的可选卡券轻量项（供「全选筛选结果」）"""
    user_id, _ = resolve_owner_scope(current_user)
    service = SelectableCardService(session)
    items = await service.get_all_selectable_card_keys(user_id=user_id, search=search)
    return {"list": items, "total": len(items)}


@router.post("")
async def create_card(
    card_data: CardCreate,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """创建新卡券"""
    # 多规格 / 图片数量 / 手续费支付方式 校验（与 update_card 共用同一 helper）
    err = _validate_card_payload(card_data)
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        card_id = await card_service.create_card(
            user_id=current_user.id,
            item_id=card_data.item_id,
            name=card_data.name,
            card_type=card_data.type,
            api_config=card_data.api_config,
            text_content=card_data.text_content,
            data_content=card_data.data_content,
            image_url=card_data.image_url,
            image_urls=card_data.image_urls,
            description=card_data.description,
            enabled=card_data.enabled or True,
            delay_seconds=card_data.delay_seconds or 0,
            price=card_data.price,
            is_dockable=card_data.is_dockable or False,
            fee_payer=card_data.fee_payer if card_data.is_dockable else None,
            min_price=card_data.min_price if card_data.is_dockable else None,
            dock_visibility=card_data.dock_visibility if card_data.is_dockable else None,
            is_multi_spec=card_data.is_multi_spec or False,
            spec_name=card_data.spec_name if card_data.is_multi_spec else None,
            spec_value=card_data.spec_value if card_data.is_multi_spec else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"id": card_id, "message": "卡券创建成功"}


@router.get("/{card_id}")
async def get_card(
    card_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """获取单个卡券详情，管理员可查看所有"""
    user_id, _ = resolve_owner_scope(current_user)
    card = await card_service.get_card_by_id(card_id, user_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡券不存在")
    return card


@router.put("/{card_id}")
async def update_card(
    card_id: int,
    card_data: CardUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """更新卡券"""
    # 多规格 / 图片数量 / 手续费支付方式 校验（与 create_card 共用同一 helper）
    err = _validate_card_payload(card_data)
    if err:
        raise HTTPException(status_code=400, detail=err)

    update_data = card_data.model_dump(exclude_unset=True)
    # type字段保持不变，模型字段就是type
    
    try:
        success = await card_service.update_card(card_id, current_user.id, **update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if success:
        return {"message": "卡券更新成功"}
    raise HTTPException(status_code=404, detail="卡券不存在")


@router.delete("/{card_id}")
async def delete_card(
    card_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """删除卡券"""
    success = await card_service.delete_card(card_id, current_user.id)
    if success:
        return {"message": "卡券删除成功"}
    raise HTTPException(status_code=404, detail="卡券不存在")


@router.post("/upload-image")
async def upload_card_image(
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    """上传卡券图片

    支持上传单张图片，返回图片URL
    """
    try:
        _, filename, _ = await save_uploaded_image(
            image,
            CARD_UPLOAD_DIR,
            filename_prefix=str(current_user.id),
        )
    except ImageUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    # 返回相对URL路径
    image_url = f"/static/uploads/cards/{filename}"
    return {"success": True, "image_url": image_url}


@router.post("/batch-delete")
async def batch_delete_cards(
    request: BatchDeleteRequest,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """批量删除卡券"""
    success_count = await card_service.batch_delete_cards(request.ids, current_user.id)
    
    return ApiResponse(
        success=True,
        message=f"成功删除 {success_count} 张卡券",
        data={
            "success_count": success_count,
            "total_count": len(request.ids),
        },
    )


@router.get("/{card_id}/items")
async def get_card_items(
    card_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """获取卡券关联的商品ID列表"""
    item_ids = await card_service.get_card_item_ids(card_id)
    return ApiResponse(success=True, data={"item_ids": item_ids})


@router.put("/{card_id}/items")
async def update_card_items(
    card_id: int,
    request: UpdateCardItemsRequest,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """更新卡券关联的商品列表（先删旧关联再插新关联）"""
    result = await card_service.update_card_item_relations(
        card_id=card_id,
        user_id=current_user.id,
        item_ids=request.item_ids,
    )
    return ApiResponse(
        success=True,
        message=f"关联更新成功（新增 {result['added']} 个，删除 {result['removed']} 个）",
        data=result,
    )


@router.post("/batch-bind")
async def batch_bind_cards(
    request: BatchBindRequest,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """批量绑定卡券到商品（通过关联表，不再复制卡券）"""
    if not request.card_ids:
        return ApiResponse(success=False, message="请至少选择一个卡券")
    if not request.item_ids:
        return ApiResponse(success=False, message="请至少选择一个商品")

    result = await card_service.batch_bind_cards_to_items(
        user_id=current_user.id,
        card_ids=request.card_ids,
        item_ids=request.item_ids,
    )

    return ApiResponse(
        success=True,
        message=f"批量绑定完成（成功 {result['success_count']} 个，失败 {result['fail_count']} 个）",
        data=result,
    )


@router.post("/batch-save")
async def batch_save_card(
    request: BatchSaveCardRequest,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """批量保存卡券到多个商品（创建一个卡券并通过关联表绑定到多个商品）"""
    if not request.item_ids:
        return ApiResponse(success=False, message="请至少选择一个商品")

    # 多规格 / 图片数量 校验（与 create_card / update_card 共用 helper；
    # 本接口历史上不做 fee_payer 校验，传 validate_fee_payer=False 保持原有行为）
    err = _validate_card_payload(request, validate_fee_payer=False)
    if err:
        return ApiResponse(success=False, message=err)

    try:
        result = await card_service.batch_save_and_bind(
            user_id=current_user.id,
            item_ids=request.item_ids,
            name=request.name,
            card_type=request.type,
            api_config=request.api_config,
            text_content=request.text_content,
            data_content=request.data_content,
            image_url=request.image_url,
            image_urls=request.image_urls,
            description=request.description,
            enabled=request.enabled or True,
            delay_seconds=request.delay_seconds or 0,
            price=request.price,
            is_dockable=request.is_dockable or False,
            fee_payer=request.fee_payer if request.is_dockable else None,
            min_price=request.min_price if request.is_dockable else None,
            dock_visibility=request.dock_visibility if request.is_dockable else None,
            is_multi_spec=request.is_multi_spec or False,
            spec_name=request.spec_name if request.is_multi_spec else None,
            spec_value=request.spec_value if request.is_multi_spec else None,
        )
        
        return ApiResponse(
            success=True,
            message=f"卡券创建成功，已绑定到 {result['bind_count']} 个商品",
            data=result,
        )
    except ValueError as e:
        return ApiResponse(success=False, message=str(e))


@router.delete("/relation/{card_id}/{item_id}")
async def delete_card_item_relation(
    card_id: int,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """删除指定卡券与指定商品的关联关系"""
    success = await card_service.delete_card_item_relation(card_id, item_id)
    if success:
        return ApiResponse(success=True, message="已删除关联关系")
    return ApiResponse(success=False, message="未找到该关联关系")


@router.put("/item/{item_id}/cards")
async def update_item_cards(
    item_id: str,
    request: UpdateItemCardsRequest,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """更新商品关联的卡券列表（先删旧关联再插新关联）"""
    # 转换为内部格式
    card_relations = [
        {"card_id": item.card_id, "source": item.source, "dock_record_id": item.dock_record_id}
        for item in request.card_items
    ]
    result = await card_service.update_item_card_relations(
        item_id=item_id,
        user_id=current_user.id,
        card_relations=card_relations,
    )
    return ApiResponse(
        success=True,
        message=f"已更新关联卡券（新增 {result['added']}，移除 {result['removed']}）",
        data=result,
    )


@router.post("/batch-clear-item-relations")
async def batch_clear_item_relations(
    request: BatchClearItemRelationsRequest,
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """批量清空商品的卡券关联关系（不删除卡券本身）"""
    if not request.item_ids:
        return ApiResponse(success=False, message="请至少选择一个商品")

    removed = await card_service.batch_clear_item_relations(request.item_ids)
    return ApiResponse(
        success=True,
        message=f"已清空 {len(request.item_ids)} 个商品的卡券关联（共删除 {removed} 条关联记录）",
        data={"removed": removed},
    )
