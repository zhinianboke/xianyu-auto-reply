"""广告公开展示、类型字典、管理、申请及付款接口，业务统一交给服务层。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_admin_user, get_current_user, get_db_session
from app.services.advertisement_payment_service import AdvertisementPaymentService
from app.services.advertisement_service import AdvertisementService
from common.models.user import User
from common.schemas.common import ApiResponse

router = APIRouter(tags=["advertisements"])


@router.get("/public", response_model=ApiResponse)
async def get_public_ads(placement: str = "dashboard", user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """按首页或仪表盘位置返回已复核广告。"""
    return await AdvertisementService(db).get_public(placement, user_agent)


@router.get("/types", response_model=ApiResponse)
async def get_ad_types(db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """查询广告类型字典及各类型费用键。"""
    return await AdvertisementService(db).get_types()


@router.get("/prices", response_model=ApiResponse)
async def get_ad_prices(current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """查询四类广告的每月费用。"""
    return await AdvertisementService(db).get_prices()


@router.get("/admin", response_model=ApiResponse)
async def get_all_ads(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: str | None = None, ad_type: str | None = None,
    current_user: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """管理员分页查询广告，支持类型和状态筛选。"""
    return await AdvertisementService(db).list_ads(page, page_size, status=status, ad_type=ad_type)


@router.put("/admin/{ad_id}/approve", response_model=ApiResponse)
async def approve_ad(ad_id: int, current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """管理员复核广告。"""
    return await AdvertisementService(db).approve(ad_id, True)


@router.put("/admin/{ad_id}/reject", response_model=ApiResponse)
async def reject_ad(ad_id: int, current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """管理员取消广告复核。"""
    return await AdvertisementService(db).approve(ad_id, False)


@router.delete("/admin/{ad_id}", response_model=ApiResponse)
async def delete_ad_admin(ad_id: int, current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """管理员软删除广告并保留历史记录。"""
    return await AdvertisementService(db).delete(ad_id)


@router.put("/admin/{ad_id}", response_model=ApiResponse)
async def update_ad_admin(ad_id: int, title: str, ad_type: str, content: str | None = None,
    link: str | None = None, expire_date: str | None = None, image_url: str | None = None, status: str | None = None,
    current_user: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """管理员编辑广告内容、展示类型和到期日。"""
    return await AdvertisementService(db).update_admin(ad_id, title, ad_type, content=content, link=link,
        expire_date=expire_date, image_url=image_url, status=status)


@router.get("", response_model=ApiResponse)
async def get_my_ads(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """分页查询当前用户自己的广告。"""
    return await AdvertisementService(db).list_ads(page, page_size, user_id=current_user.id)


@router.post("", response_model=ApiResponse)
async def create_ad(title: str, ad_type: str, months: int, content: str | None = None,
    link: str | None = None, image_url: str | None = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """按所选类型费用创建当前用户的广告申请。"""
    return await AdvertisementService(db).save_application(current_user.id, title, ad_type, months,
        content=content, link=link, image_url=image_url)


@router.put("/{ad_id}", response_model=ApiResponse)
async def update_my_ad(ad_id: int, title: str, ad_type: str, months: int, content: str | None = None,
    link: str | None = None, image_url: str | None = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """修改当前用户尚未复核的广告申请并重新计算费用。"""
    return await AdvertisementService(db).save_application(current_user.id, title, ad_type, months,
        ad_id=ad_id, content=content, link=link, image_url=image_url)


@router.delete("/{ad_id}", response_model=ApiResponse)
async def delete_my_ad(ad_id: int, current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """软删除当前用户自己的广告。"""
    return await AdvertisementService(db).delete(ad_id, current_user.id)


@router.post("/{ad_id}/pay", response_model=ApiResponse)
async def create_ad_payment(ad_id: int, current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """生成当前用户广告付款二维码并关联支付订单。"""
    return await AdvertisementPaymentService(db).create(ad_id, current_user.id)


@router.post("/{ad_id}/pay/notify", response_model=ApiResponse)
async def ad_payment_notify(ad_id: int, order_no: str, current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)) -> ApiResponse:
    """查询广告付款状态，复用与支付宝回调相同的幂等结算。"""
    return await AdvertisementPaymentService(db).poll(ad_id, order_no, current_user.id)
