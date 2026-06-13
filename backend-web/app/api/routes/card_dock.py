"""
分销卡券对接路由

功能：
1. 为前端「分销卡券」页面提供卡券商查询、商品查询、库存查询与提货接口
2. 上游 API 密钥统一由后台从当前用户的个人设置（分销管理-对接卡密秘钥）读取，前端无需传入
3. 所有数据均通过上游卡券系统实时获取

说明：
- 统一返回 {success, code, message, data} 结构，业务错误同样以 HTTP 200 返回
- 需登录用户（活跃用户）方可访问，使用各自配置的对接卡密秘钥
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api import deps
from app.services.card_dock_service import CardDockService
from common.models.user import User

router = APIRouter(prefix="/card-dock", tags=["分销卡券"])

# Rate limiter: {user_id: [timestamps]}
_purchase_rate_limit: dict[int, list[float]] = {}
_PURCHASE_MAX_REQUESTS = 5
_PURCHASE_WINDOW_SECONDS = 60


def _check_purchase_rate_limit(user_id: int) -> bool:
    """Return True if within limit, False if exceeded."""
    now = time.time()
    window_start = now - _PURCHASE_WINDOW_SECONDS
    timestamps = _purchase_rate_limit.setdefault(user_id, [])
    # Prune old entries
    _purchase_rate_limit[user_id] = [t for t in timestamps if t > window_start]
    if len(_purchase_rate_limit[user_id]) >= _PURCHASE_MAX_REQUESTS:
        return False
    _purchase_rate_limit[user_id].append(now)
    return True


class CardPurchaseRequest(BaseModel):
    """提货请求体"""
    source_code: str
    goods_id: int
    sub_id: int
    quantity: int = 1


@router.get("/sources")
async def list_card_sources(
    current_user: User = Depends(deps.get_current_active_user),
    service: CardDockService = Depends(deps.get_card_dock_service),
) -> Dict[str, Any]:
    """获取卡券商下拉列表"""
    return await service.get_sources(current_user.id)


@router.get("/goods")
async def list_card_goods(
    source_code: str = "",
    page: int = 1,
    per_page: int = 15,
    search: str = "",
    current_user: User = Depends(deps.get_current_active_user),
    service: CardDockService = Depends(deps.get_card_dock_service),
) -> Dict[str, Any]:
    """获取卡券货源商品列表"""
    if not source_code.strip():
        return {"success": False, "code": 400, "message": "请先选择卡券商", "data": None}
    return await service.get_goods(current_user.id, source_code.strip(), page=page, per_page=per_page, search=search.strip())


@router.get("/goods/{goods_id}")
async def get_card_goods_detail(
    goods_id: int,
    source_code: str = "",
    current_user: User = Depends(deps.get_current_active_user),
    service: CardDockService = Depends(deps.get_card_dock_service),
) -> Dict[str, Any]:
    """获取商品详情（含使用说明）"""
    if not source_code.strip():
        return {"success": False, "code": 400, "message": "请先选择卡券商", "data": None}
    return await service.get_goods_detail(current_user.id, source_code.strip(), goods_id)


@router.get("/goods/{goods_id}/stock")
async def get_card_goods_stock(
    goods_id: int,
    source_code: str = "",
    current_user: User = Depends(deps.get_current_active_user),
    service: CardDockService = Depends(deps.get_card_dock_service),
) -> Dict[str, Any]:
    """获取商品各规格库存"""
    if not source_code.strip():
        return {"success": False, "code": 400, "message": "请先选择卡券商", "data": None}
    return await service.get_goods_stock(current_user.id, source_code.strip(), goods_id)


@router.post("/purchase")
async def purchase_card(
    payload: CardPurchaseRequest,
    current_user: User = Depends(deps.get_current_active_user),
    service: CardDockService = Depends(deps.get_card_dock_service),
) -> Dict[str, Any]:
    """提货：通过上游卡券系统购买并返回卡密"""
    if not _check_purchase_rate_limit(current_user.id):
        return JSONResponse(
            status_code=429,
            content={"success": False, "code": 429, "message": "请求过于频繁，请稍后再试", "data": None},
        )
    if not payload.source_code.strip():
        return {"success": False, "code": 400, "message": "请先选择卡券商", "data": None}
    if payload.quantity < 1:
        return {"success": False, "code": 400, "message": "购买数量不能小于1", "data": None}
    return await service.purchase(
        current_user.id,
        payload.source_code.strip(),
        payload.goods_id,
        payload.sub_id,
        payload.quantity,
    )


@router.get("/purchase-url")
async def get_card_purchase_url(
    source_code: str = "",
    goods_id: int = 0,
    sub_id: int = 0,
    quantity: int = 1,
    current_user: User = Depends(deps.get_current_active_user),
    service: CardDockService = Depends(deps.get_card_dock_service),
) -> Dict[str, Any]:
    """生成可直接 GET 调用的提货地址（含 api_key），用于前端「复制提货api」"""
    if not source_code.strip():
        return {"success": False, "code": 400, "message": "请先选择卡券商", "data": None}
    if goods_id <= 0 or sub_id <= 0:
        return {"success": False, "code": 400, "message": "商品或规格参数无效", "data": None}
    return await service.get_purchase_url(
        current_user.id,
        source_code.strip(),
        goods_id,
        sub_id,
        max(1, quantity),
    )
