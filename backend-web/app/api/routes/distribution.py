"""
分销管理 API 路由

提供货源管理（可对接卡券浏览）、对接记录管理和二级分销功能
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import get_settings
from common.models.dock_record import DockRecord
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from common.utils.security import generate_secret_key as _generate_secret_key
from app.services.card_service import CardService
from app.services.dock_record_service import DockRecordService
from app.services.fund_flow_service import FundFlowService
from app.services.pickup_service import PickupService

from common.utils.time_utils import safe_isoformat
router = APIRouter(tags=["分销管理"])


async def get_card_service(session: AsyncSession = Depends(deps.get_db_session)) -> CardService:
    """获取卡券服务实例"""
    return CardService(session)


async def get_dock_record_service(session: AsyncSession = Depends(deps.get_db_session)) -> DockRecordService:
    """获取对接记录服务实例"""
    return DockRecordService(session)


async def get_fund_flow_service(session: AsyncSession = Depends(deps.get_db_session)) -> FundFlowService:
    """获取资金流水服务实例"""
    return FundFlowService(session)


# ========== Pydantic 模型 ==========

class DockRecordCreate(BaseModel):
    """创建对接记录请求"""
    card_id: int  # 来源卡券ID
    dock_name: str  # 对接名称
    markup_amount: Optional[str] = None  # 加价金额
    remark: Optional[str] = None  # 备注


class DockRecordUpdate(BaseModel):
    """更新对接记录请求"""
    dock_name: Optional[str] = None  # 对接名称
    markup_amount: Optional[str] = None  # 加价金额
    remark: Optional[str] = None  # 备注
    status: Optional[bool] = None  # 对接状态
    disable_reason: Optional[str] = None  # 禁用原因


class SubDockRecordCreate(BaseModel):
    """创建二级对接记录请求"""
    parent_dock_id: int  # 上级对接记录ID
    dock_name: str  # 对接名称
    markup_amount: Optional[str] = None  # 加价金额
    remark: Optional[str] = None  # 备注


class ToggleSubDockRequest(BaseModel):
    """开放/关闭下级对接请求"""
    allow: bool  # 是否允许下级对接
    sub_dock_price: Optional[str] = None  # 给下级的对接价格
    sub_dock_visibility: Optional[str] = None  # 下级对接可见性：public/dealer_only


class CascadeStatusUpdate(BaseModel):
    """级联状态更新请求"""
    status: bool  # 启用/禁用状态
    disable_reason: Optional[str] = None  # 禁用原因


# ========== 货源管理 ==========

@router.get("/supply")
async def get_supply_cards(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: str = Query(default="", description="搜索关键词（名称或描述）"),
    card_type: str = Query(default="", alias="type", description="卡券类型过滤"),
    current_user: User = Depends(deps.get_current_active_user),
    card_service: CardService = Depends(get_card_service),
):
    """获取所有可对接卡券列表（货源管理）"""
    _, is_admin = resolve_owner_scope(current_user)
    result = await card_service.get_dockable_cards_paginated(
        current_user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
        card_type=card_type,
        is_admin=is_admin,
    )
    return result


# ========== 对接记录管理 ==========

@router.post("/dock-records", response_model=ApiResponse)
async def create_dock_record(
    data: DockRecordCreate,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """创建对接记录"""
    record_id = await service.create_dock_record(
        user_id=current_user.id,
        card_id=data.card_id,
        dock_name=data.dock_name,
        markup_amount=data.markup_amount,
        remark=data.remark,
    )
    return ApiResponse(success=True, message="对接成功", data={"id": record_id})


@router.put("/dock-records/{record_id}", response_model=ApiResponse)
async def update_dock_record(
    record_id: int,
    data: DockRecordUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """更新对接记录"""
    _, is_admin = resolve_owner_scope(current_user)
    update_data = data.model_dump(exclude_unset=True)
    success = await service.update_dock_record(record_id, current_user.id, is_admin=is_admin, **update_data)
    if not success:
        return ApiResponse(success=False, message="对接记录不存在或无权限")
    return ApiResponse(success=True, message="更新成功")


@router.put("/dock-records/{record_id}/owner-update", response_model=ApiResponse)
async def update_dock_record_by_owner(
    record_id: int,
    data: DockRecordUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """分销主更新对接记录（仅限状态和禁用原因）"""
    update_data = data.model_dump(exclude_unset=True)
    success = await service.update_dock_record_by_owner(record_id, current_user.id, **update_data)
    if not success:
        return ApiResponse(success=False, message="对接记录不存在或无权限")
    return ApiResponse(success=True, message="更新成功")


@router.delete("/dock-records/{record_id}", response_model=ApiResponse)
async def delete_dock_record(
    record_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """删除对接记录"""
    _, is_admin = resolve_owner_scope(current_user)
    success = await service.delete_dock_record(record_id, current_user.id, is_admin=is_admin)
    if not success:
        return ApiResponse(success=False, message="对接记录不存在或无权限")
    return ApiResponse(success=True, message="删除成功")


@router.get("/dock-records")
async def get_dock_records(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=9999, description="每页数量"),
    search: str = Query(default="", description="搜索关键词（对接名称）"),
    status: Optional[bool] = Query(default=None, description="启用状态筛选：true=已启用，false=已停用"),
    level: Optional[int] = Query(default=None, ge=1, le=2, description="分销层级筛选：1=一级，2=二级"),
    allow_sub_dock: Optional[bool] = Query(default=None, description="是否开放下级对接筛选：true=已开放，false=未开放"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
):
    """获取对接记录列表，管理员可查看所有，支持状态、层级、开放对接筛选"""
    user_id, _ = resolve_owner_scope(current_user)
    result = await service.get_dock_records_paginated(
        user_id=user_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        level=level,
        allow_sub_dock=allow_sub_dock,
    )
    return result


# ========== 提货地址 ==========

@router.get("/dock-records/{record_id}/pickup-url", response_model=ApiResponse)
async def get_pickup_url(
    record_id: int,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """获取对接记录的提货地址（免认证GET链接）

    返回一个拼接了用户提货秘钥和对接记录ID的URL，外部系统GET访问即可提货。
    秘钥为空时自动生成。地址优先使用站点对外域名（前端地址），否则使用当前请求来源。

    权限：记录归属人可获取；管理员可获取任意用户的对接记录提货地址。
    注意：提货校验以"对接记录归属人"的秘钥为准，因此管理员代为获取时，
    使用并按需生成该记录归属人的提货秘钥，保证生成的链接可正常提货。
    """
    # 校验对接记录归属（管理员不限制归属）
    _, is_admin = resolve_owner_scope(current_user)
    record = await session.get(DockRecord, record_id)
    if not record:
        return ApiResponse(success=False, message="对接记录不存在")
    if not is_admin and record.user_id != current_user.id:
        return ApiResponse(success=False, message="无权操作该对接记录")

    # 提货秘钥归属于"对接记录归属人"：本人操作即当前用户；管理员代为操作时取记录归属人
    if record.user_id == current_user.id:
        key_owner = current_user
    else:
        key_owner = await session.get(User, record.user_id)
        if not key_owner:
            return ApiResponse(success=False, message="对接记录归属用户不存在")

    # 获取或生成提货秘钥
    if not key_owner.secret_key:
        for _ in range(10):
            key = _generate_secret_key()
            key_owner.secret_key = key
            try:
                await session.commit()
                break
            except Exception:
                await session.rollback()
                key_owner.secret_key = None
                continue
        else:
            return ApiResponse(success=False, message="生成提货秘钥失败，请重试")

    # 计算站点基础地址：优先用配置的前端对外地址，否则用当前请求来源（避免写死localhost）
    settings = get_settings()
    base = (settings.frontend_public_url or '').strip().rstrip('/')
    if not base:
        base = str(request.base_url).rstrip('/')

    pickup_url = f"{base}/api/v1/distribution/pickup?key={key_owner.secret_key}&dock_id={record_id}"
    return ApiResponse(success=True, message="获取成功", data={"pickup_url": pickup_url})


@router.get("/pickup", response_class=PlainTextResponse)
async def pickup(
    key: str = Query(default="", description="用户提货秘钥"),
    dock_id: int = Query(default=0, description="对接记录ID"),
    session: AsyncSession = Depends(deps.get_db_session),
) -> PlainTextResponse:
    """提货接口（免认证，纯文本返回）

    通过 提货秘钥 + 对接记录ID 触发一次提货：
    参照自动发货逻辑取卡券内容，按对接记录的对接价格扣费并分润结算。
    成功返回卡券内容文本，失败返回错误提示文本（HTTP 200）。
    """
    service = PickupService(session)
    result = await service.pickup(key.strip(), dock_id)
    return PlainTextResponse(content=result.content, status_code=200)


# ========== 分销商管理 ==========

@router.get("/dealers")
async def get_dealers(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: str = Query(default="", description="搜索关键词（用户名）"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
):
    """获取对接了当前用户卡券的分销商列表"""
    result = await service.get_dealers_paginated(
        owner_user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
    )
    return result


@router.get("/dealers/{dealer_user_id}/details")
async def get_dealer_details(
    dealer_user_id: int,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
):
    """获取某个分销商对接当前用户卡券的明细"""
    result = await service.get_dealer_dock_details(
        owner_user_id=current_user.id,
        dealer_user_id=dealer_user_id,
        page=page,
        page_size=page_size,
    )
    return result


# ========== 二级分销 ==========

@router.get("/sub-supply")
async def get_sub_supply_records(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: str = Query(default="", description="搜索关键词"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
):
    """获取可对接的一级分销商记录列表（二级分销货源广场）"""
    result = await service.get_dockable_sub_records_paginated(
        current_user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
    )
    return result


@router.post("/sub-dock-records", response_model=ApiResponse)
async def create_sub_dock_record(
    data: SubDockRecordCreate,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """创建二级对接记录"""
    result = await service.create_sub_dock_record(
        user_id=current_user.id,
        parent_dock_id=data.parent_dock_id,
        dock_name=data.dock_name,
        markup_amount=data.markup_amount,
        remark=data.remark,
    )
    if not result["success"]:
        return ApiResponse(success=False, message=result["message"])
    return ApiResponse(success=True, message=result["message"], data={"id": result["id"]})


@router.put("/dock-records/{record_id}/toggle-sub-dock", response_model=ApiResponse)
async def toggle_sub_dock(
    record_id: int,
    data: ToggleSubDockRequest,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """开放/关闭下级对接（一级分销商可操作自己的对接记录，管理员可操作任意记录）"""
    _, is_admin = resolve_owner_scope(current_user)
    success = await service.toggle_allow_sub_dock(record_id, current_user.id, data.allow, data.sub_dock_price, data.sub_dock_visibility, is_admin=is_admin)
    if not success:
        return ApiResponse(success=False, message="对接记录不存在或无权限（仅一级分销商可操作）")
    action = "开放" if data.allow else "关闭"
    return ApiResponse(success=True, message=f"{action}下级对接成功")


@router.put("/dock-records/{record_id}/cascade-status", response_model=ApiResponse)
async def cascade_update_status(
    record_id: int,
    data: CascadeStatusUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """更新对接记录状态（带级联禁用下级，卡券拥有者操作）"""
    result = await service.update_dock_record_status_with_cascade(
        record_id=record_id,
        owner_user_id=current_user.id,
        status=data.status,
        disable_reason=data.disable_reason,
    )
    if not result["success"]:
        return ApiResponse(success=False, message=result["message"])
    msg = result["message"]
    if result["cascade_count"] > 0:
        msg += f"，级联禁用了 {result['cascade_count']} 条下级对接记录"
    return ApiResponse(success=True, message=msg, data={"cascade_count": result["cascade_count"]})


@router.get("/sub-dealers")
async def get_sub_dealers(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: str = Query(default="", description="搜索关键词（用户名）"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
):
    """获取当前一级分销商的下级分销商列表"""
    result = await service.get_sub_dealers_paginated(
        source_user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
    )
    return result


@router.put("/sub-dealers/{record_id}/disable", response_model=ApiResponse)
async def disable_sub_dealer(
    record_id: int,
    disable_reason: Optional[str] = Query(default=None, description="禁用原因"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
) -> ApiResponse:
    """一级分销商禁用下级分销商的对接记录"""
    success = await service.disable_sub_dealer_record(
        record_id=record_id,
        source_user_id=current_user.id,
        disable_reason=disable_reason,
    )
    if not success:
        return ApiResponse(success=False, message="对接记录不存在或无权限")
    return ApiResponse(success=True, message="禁用成功")


@router.get("/sub-dealers/{dealer_user_id}/details")
async def get_sub_dealer_details(
    dealer_user_id: int,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(deps.get_current_active_user),
    service: DockRecordService = Depends(get_dock_record_service),
):
    """获取某个下级分销商对接当前一级分销商的明细"""
    result = await service.get_sub_dealer_dock_details(
        source_user_id=current_user.id,
        dealer_user_id=dealer_user_id,
        page=page,
        page_size=page_size,
    )
    return result


# ========== 资金流水 ==========

@router.get("/fund-flows")
async def get_fund_flows(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    flow_type: str = Query(default="", alias="type", description="流水类型：income/expense"),
    current_user: User = Depends(deps.get_current_active_user),
    service: FundFlowService = Depends(get_fund_flow_service),
):
    """获取资金流水列表，管理员可查看所有"""
    user_id, _ = resolve_owner_scope(current_user)
    result = await service.get_fund_flows_paginated(
        user_id=user_id,
        flow_type=flow_type,
        page=page,
        page_size=page_size,
    )
    return result


# ========== 货源管理（对接码绑定） ==========

class DockCodeBindRequest(BaseModel):
    """绑定对接码请求"""
    dock_code: str  # 对接码


@router.get("/source-bindings")
async def get_source_bindings(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取当前用户已绑定的货源列表"""
    from sqlalchemy import select
    from common.models.dock_code_binding import DockCodeBinding
    from common.models.user import User as UserModel

    stmt = (
        select(DockCodeBinding, UserModel.username)
        .join(UserModel, UserModel.id == DockCodeBinding.target_user_id)
        .where(DockCodeBinding.user_id == current_user.id)
        .order_by(DockCodeBinding.created_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    data = []
    for binding, username in rows:
        data.append({
            "id": binding.id,
            "dock_code": binding.dock_code,
            "target_user_id": binding.target_user_id,
            "target_username": username,
            "created_at": safe_isoformat(binding.created_at),
        })
    return ApiResponse(success=True, data=data)


@router.post("/source-bindings", response_model=ApiResponse)
async def bind_dock_code(
    data: DockCodeBindRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """通过对接码绑定货源供应商"""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from common.models.dock_code_binding import DockCodeBinding
    from common.models.user import User as UserModel

    code = data.dock_code.strip().upper()
    if not code:
        return ApiResponse(success=False, message="对接码不能为空")

    # 查找对接码对应的用户
    stmt = select(UserModel).where(UserModel.dock_code == code)
    result = await session.execute(stmt)
    target_user = result.scalar_one_or_none()
    if not target_user:
        return ApiResponse(success=False, message="对接码无效，未找到对应的供应商")

    if target_user.id == current_user.id:
        return ApiResponse(success=False, message="不能绑定自己的对接码")

    # 检查是否已绑定
    check_stmt = select(DockCodeBinding).where(
        DockCodeBinding.user_id == current_user.id,
        DockCodeBinding.target_user_id == target_user.id,
    )
    existing = await session.execute(check_stmt)
    if existing.scalar_one_or_none():
        return ApiResponse(success=False, message="已绑定该供应商的对接码")

    # 创建绑定
    binding = DockCodeBinding(
        user_id=current_user.id,
        dock_code=code,
        target_user_id=target_user.id,
    )
    session.add(binding)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return ApiResponse(success=False, message="绑定失败，可能已绑定该供应商")

    return ApiResponse(success=True, message=f"已成功绑定供应商 {target_user.username}")


@router.delete("/source-bindings/{binding_id}", response_model=ApiResponse)
async def unbind_dock_code(
    binding_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """解绑货源供应商，同时删除相关的一级和二级对接记录"""
    from sqlalchemy import select, delete as sql_delete
    from common.models.dock_code_binding import DockCodeBinding
    from common.models.dock_record import DockRecord
    from common.models.card import Card

    # 确认归属
    stmt = select(DockCodeBinding).where(
        DockCodeBinding.id == binding_id,
        DockCodeBinding.user_id == current_user.id,
    )
    result = await session.execute(stmt)
    binding = result.scalar_one_or_none()
    if not binding:
        return ApiResponse(success=False, message="绑定记录不存在")

    target_user_id = binding.target_user_id

    # 查出当前用户对接该供应商卡券的所有一级对接记录ID
    level1_ids_stmt = (
        select(DockRecord.id)
        .join(Card, Card.id == DockRecord.card_id)
        .where(
            DockRecord.user_id == current_user.id,
            DockRecord.level == 1,
            Card.user_id == target_user_id,
        )
    )
    level1_result = await session.execute(level1_ids_stmt)
    level1_ids = [row[0] for row in level1_result.all()]

    if level1_ids:
        # 先删除这些一级记录下的所有二级对接记录
        await session.execute(
            sql_delete(DockRecord).where(DockRecord.parent_dock_id.in_(level1_ids))
        )
        # 再删除一级对接记录
        await session.execute(
            sql_delete(DockRecord).where(DockRecord.id.in_(level1_ids))
        )

    # 删除绑定记录
    await session.delete(binding)
    await session.commit()
    return ApiResponse(success=True, message="已解绑，相关对接记录已清除")


# ========== 对接我的（供应商视角） ==========

@router.get("/bound-to-me")
async def get_bound_to_me(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取所有绑定了当前用户对接码的分销商列表"""
    from sqlalchemy import select, func
    from common.models.dock_code_binding import DockCodeBinding
    from common.models.user import User as UserModel
    from common.models.dock_record import DockRecord
    from common.models.card import Card

    stmt = (
        select(DockCodeBinding, UserModel.username)
        .join(UserModel, UserModel.id == DockCodeBinding.user_id)
        .where(DockCodeBinding.target_user_id == current_user.id)
        .order_by(DockCodeBinding.created_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    data = []
    for binding, username in rows:
        # 统计该分销商对接了当前供应商多少卡券
        count_stmt = (
            select(func.count(DockRecord.id))
            .join(Card, Card.id == DockRecord.card_id)
            .where(
                DockRecord.user_id == binding.user_id,
                DockRecord.level == 1,
                Card.user_id == current_user.id,
            )
        )
        count_result = await session.execute(count_stmt)
        dock_count = count_result.scalar() or 0

        data.append({
            "id": binding.id,
            "user_id": binding.user_id,
            "username": username,
            "dock_code": binding.dock_code,
            "dock_count": dock_count,
            "created_at": safe_isoformat(binding.created_at),
        })
    return ApiResponse(success=True, data=data)


# ========== 代理订单 ==========


async def _paginate_agent_orders(
    session: AsyncSession,
    base_where,
    page: int,
    page_size: int,
    *,
    extra_select=(),
    extra_joins=(),
):
    """代理订单分页查询的通用逻辑。

    功能：
    1. 基于 ``base_where`` 统计 AgentOrder 总数并计算总页数
    2. 关联 DockRecord / Card 取出 dock_name 与 card_name
    3. 调用方可通过 ``extra_select`` / ``extra_joins`` 追加更多字段与 join

    参数：
    - ``session`` : 异步数据库会话
    - ``base_where`` : 基础 where 条件列表（is_admin / user_id / upstream_user_id / status）
    - ``page`` / ``page_size`` : 分页参数
    - ``extra_select`` : 额外要在 SELECT 中查询的列表达式，按顺序追加
    - ``extra_joins`` : 形如 ``[(target, on_clause), ...]`` 的额外外连接

    返回：
    - ``rows`` : 每行结构为 ``(AgentOrder, dock_name, card_name, *extra_select)``
    - ``total`` : 满足 where 的总数
    - ``total_pages`` : 总页数
    """
    from sqlalchemy import select, func
    from common.models.agent_order import AgentOrder
    from common.models.dock_record import DockRecord
    from common.models.card import Card

    count_stmt = select(func.count(AgentOrder.id))
    if base_where:
        count_stmt = count_stmt.where(*base_where)
    total = (await session.execute(count_stmt)).scalar() or 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    select_columns = [AgentOrder, DockRecord.dock_name, Card.name.label("card_name"), *extra_select]
    stmt = (
        select(*select_columns)
        .outerjoin(DockRecord, DockRecord.id == AgentOrder.dock_record_id)
        .outerjoin(Card, Card.id == AgentOrder.card_id)
    )
    for target, on_clause in extra_joins:
        stmt = stmt.outerjoin(target, on_clause)
    if base_where:
        stmt = stmt.where(*base_where)
    stmt = (
        stmt.order_by(AgentOrder.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    return rows, total, total_pages


def _serialize_agent_order_common(
    order,
    dock_name,
    card_name,
    *,
    extra_after_owner: dict | None = None,
    extra_at_end: dict | None = None,
) -> dict:
    """两个代理订单接口共用的字段序列化。

    为保持与原版返回 JSON 完全一致的字段顺序：
    - 通用前缀（id 到 owner_user_id）写在前面
    - ``extra_after_owner`` 紧跟 owner_user_id 之后（用于 upstream 的 dealer / upstream 信息）
    - 通用后缀（delivery_content / buyer_id / status / source / created_at）
    - ``extra_at_end`` 写在最末尾（用于 my 的 user_id / user_name）
    """
    item: dict = {
        "id": order.id,
        "order_no": order.order_no,
        "item_id": order.item_id,
        "card_id": order.card_id,
        "card_name": card_name,
        "dock_record_id": order.dock_record_id,
        "dock_name": dock_name,
        "dock_level": order.dock_level,
        "sale_price": order.sale_price,
        "dock_price": order.dock_price,
        "card_price": order.card_price or '0',
        "level2_cost": order.level2_cost or '0',
        "profit": order.profit,
        "fee_amount": order.fee_amount or '0',
        "fee_payer": order.fee_payer,
        "owner_user_id": order.owner_user_id,
    }
    if extra_after_owner:
        item.update(extra_after_owner)
    item["delivery_content"] = order.delivery_content
    item["buyer_id"] = order.buyer_id
    item["status"] = order.status
    item["source"] = _resolve_agent_order_source(order.order_no)
    item["created_at"] = safe_isoformat(order.created_at)
    if extra_at_end:
        item.update(extra_at_end)
    return item


def _resolve_agent_order_source(order_no: str | None) -> str:
    """根据订单号判断代理订单来源

    提货接口使用 PICKUP 前缀的虚拟订单号，其余为闲鱼订单发货产生。

    Returns:
        'pickup'-提货，'order'-闲鱼订单
    """
    if order_no and str(order_no).startswith('PICKUP'):
        return 'pickup'
    return 'order'


def _build_agent_orders_response(data, total: int, page: int, page_size: int, total_pages: int) -> dict:
    """两个代理订单接口共用的响应包装。"""
    return {
        "success": True,
        "data": {
            "list": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }


@router.get("/agent-orders/my")
async def get_my_agent_orders(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str = Query(default="", description="状态筛选：delivered/settled/failed"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取我的代理订单（我作为分销商发出的订单）
    管理员返回所有订单，普通用户返回自己的订单
    """
    from common.models.agent_order import AgentOrder
    from common.models.user import User as UserModel

    # 管理员查看全部，普通用户只看自己
    _, is_admin = resolve_owner_scope(current_user)
    base_where = []
    if not is_admin:
        base_where.append(AgentOrder.user_id == current_user.id)
    if status:
        base_where.append(AgentOrder.status == status)

    rows, total, total_pages = await _paginate_agent_orders(
        session,
        base_where,
        page,
        page_size,
        extra_select=[UserModel.username.label("user_name")],
        extra_joins=[(UserModel, UserModel.id == AgentOrder.user_id)],
    )

    data = []
    for order, dock_name, card_name, user_name in rows:
        item = _serialize_agent_order_common(
            order,
            dock_name,
            card_name,
            extra_at_end={"user_id": order.user_id, "user_name": user_name},
        )
        data.append(item)

    return _build_agent_orders_response(data, total, page, page_size, total_pages)


@router.get("/agent-orders/upstream")
async def get_upstream_agent_orders(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str = Query(default="", description="状态筛选：delivered/settled/failed"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取代理我的订单（别人使用我的卡券发货产生的订单）
    管理员返回所有订单，普通用户返回自己作为上游的订单
    """
    from common.models.agent_order import AgentOrder
    from common.models.user import User as UserModel

    # 管理员查看全部，普通用户只看自己作为上游的
    _, is_admin = resolve_owner_scope(current_user)
    base_where = []
    if not is_admin:
        base_where.append(AgentOrder.upstream_user_id == current_user.id)
    if status:
        base_where.append(AgentOrder.status == status)

    # 关联用户表两次：分销商(dealer) 和上游用户(upstream)
    DealerUser = UserModel.__table__.alias("dealer_user")
    UpstreamUser = UserModel.__table__.alias("upstream_user")

    rows, total, total_pages = await _paginate_agent_orders(
        session,
        base_where,
        page,
        page_size,
        extra_select=[
            DealerUser.c.username.label("dealer_name"),
            UpstreamUser.c.username.label("upstream_name"),
        ],
        extra_joins=[
            (DealerUser, DealerUser.c.id == AgentOrder.user_id),
            (UpstreamUser, UpstreamUser.c.id == AgentOrder.upstream_user_id),
        ],
    )

    data = []
    for order, dock_name, card_name, dealer_name, upstream_name in rows:
        item = _serialize_agent_order_common(
            order,
            dock_name,
            card_name,
            extra_after_owner={
                "dealer_user_id": order.user_id,
                "dealer_name": dealer_name,
                "upstream_user_id": order.upstream_user_id,
                "upstream_name": upstream_name,
            },
        )
        data.append(item)

    return _build_agent_orders_response(data, total, page, page_size, total_pages)


@router.get("/agent-orders/detail/{order_id}")
async def get_agent_order_detail(
    order_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取代理订单明细
    管理员可查看任意订单，普通用户只能查看与自己相关的订单
    """
    from sqlalchemy import select
    from common.models.agent_order import AgentOrder
    from common.models.dock_record import DockRecord
    from common.models.card import Card
    from common.models.user import User as UserModel

    DealerUser = UserModel.__table__.alias("dealer_user")
    UpstreamUser = UserModel.__table__.alias("upstream_user")
    OwnerUser = UserModel.__table__.alias("owner_user")
    stmt = (
        select(
            AgentOrder,
            DockRecord.dock_name,
            Card.name.label("card_name"),
            DealerUser.c.username.label("dealer_name"),
            UpstreamUser.c.username.label("upstream_name"),
            OwnerUser.c.username.label("owner_name"),
        )
        .outerjoin(DockRecord, DockRecord.id == AgentOrder.dock_record_id)
        .outerjoin(Card, Card.id == AgentOrder.card_id)
        .outerjoin(DealerUser, DealerUser.c.id == AgentOrder.user_id)
        .outerjoin(UpstreamUser, UpstreamUser.c.id == AgentOrder.upstream_user_id)
        .outerjoin(OwnerUser, OwnerUser.c.id == AgentOrder.owner_user_id)
        .where(AgentOrder.id == order_id)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if not row:
        return {"success": False, "message": "订单不存在"}

    order, dock_name, card_name, dealer_name, upstream_name, owner_name = row

    # 权限校验
    _, is_admin = resolve_owner_scope(current_user)
    if not is_admin:
        related = (
            order.user_id == current_user.id
            or order.upstream_user_id == current_user.id
            or order.owner_user_id == current_user.id
        )
        if not related:
            return {"success": False, "message": "无权查看该订单"}

    return {
        "success": True,
        "data": {
            "id": order.id,
            "order_no": order.order_no,
            "item_id": order.item_id,
            "card_id": order.card_id,
            "card_name": card_name,
            "dock_record_id": order.dock_record_id,
            "dock_name": dock_name,
            "dock_level": order.dock_level,
            "sale_price": order.sale_price,
            "dock_price": order.dock_price,
            "card_price": order.card_price or "0",
            "level2_cost": order.level2_cost or "0",
            "profit": order.profit,
            "fee_amount": order.fee_amount or "0",
            "fee_payer": order.fee_payer,
            "owner_user_id": order.owner_user_id,
            "owner_name": owner_name,
            "delivery_content": order.delivery_content,
            "buyer_id": order.buyer_id,
            "user_id": order.user_id,
            "dealer_name": dealer_name,
            "upstream_user_id": order.upstream_user_id,
            "upstream_name": upstream_name,
            "status": order.status,
            "settle_remark": order.settle_remark,
            "source": _resolve_agent_order_source(order.order_no),
            "created_at": safe_isoformat(order.created_at),
            "updated_at": safe_isoformat(order.updated_at),
        },
    }


@router.delete("/bound-to-me/{binding_id}", response_model=ApiResponse)
async def remove_bound_user(
    binding_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """删除绑定了当前用户对接码的分销商，同时级联删除对接记录"""
    from sqlalchemy import select, delete as sql_delete
    from common.models.dock_code_binding import DockCodeBinding
    from common.models.dock_record import DockRecord
    from common.models.card import Card

    # 确认归属：必须是绑定到当前用户的记录
    stmt = select(DockCodeBinding).where(
        DockCodeBinding.id == binding_id,
        DockCodeBinding.target_user_id == current_user.id,
    )
    result = await session.execute(stmt)
    binding = result.scalar_one_or_none()
    if not binding:
        return ApiResponse(success=False, message="记录不存在")

    distributor_user_id = binding.user_id

    # 查出该分销商对接当前供应商卡券的所有一级对接记录ID
    level1_ids_stmt = (
        select(DockRecord.id)
        .join(Card, Card.id == DockRecord.card_id)
        .where(
            DockRecord.user_id == distributor_user_id,
            DockRecord.level == 1,
            Card.user_id == current_user.id,
        )
    )
    level1_result = await session.execute(level1_ids_stmt)
    level1_ids = [row[0] for row in level1_result.all()]

    if level1_ids:
        # 先删除二级对接记录
        await session.execute(
            sql_delete(DockRecord).where(DockRecord.parent_dock_id.in_(level1_ids))
        )
        # 再删除一级对接记录
        await session.execute(
            sql_delete(DockRecord).where(DockRecord.id.in_(level1_ids))
        )

    # 删除绑定记录
    await session.delete(binding)
    await session.commit()
    return ApiResponse(success=True, message="已删除，相关对接记录已清除")
