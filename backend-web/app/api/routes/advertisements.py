"""
广告管理路由

功能：
1. 广告管理（管理员）：查看所有广告、复核、删除
2. 广告申请（所有用户）：新建、修改、删除自己的广告
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_active_user, get_current_admin_user, get_db_session
from common.models.user import User, UserRole
from common.models.advertisement import Advertisement, AdType, AdStatus
from common.models.system_setting import SystemSetting
from common.models.fund_flow import FundFlow
from common.models.user_setting import UserSetting
from common.schemas.common import ApiResponse
from common.utils.text_utils import escape_xss
from app.services.alipay_service import AlipayService
from app.services.remote_content_service import (
    fetch_remote_public_ads,
    is_remote_fetch_request,
)

from common.utils.time_utils import safe_isoformat
from common.utils.pagination import execute_paginated_with_filters
logger = logging.getLogger(__name__)

# 广告价格在系统设置中的 key 前缀
AD_PRICE_KEY_PREFIX = 'ad_price.'
# 余额在 user_settings 中的 key
BALANCE_KEY = 'balance'

router = APIRouter(tags=["advertisements"])


# ==================== 公开接口（仪表盘展示） ====================

@router.get("/public", response_model=ApiResponse)
async def get_public_ads(
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    """
    获取已复核的广告列表（公开接口，用于仪表盘展示）

    返回内容 = 本地已复核且未过期的广告 + 远程官方服务器的公开广告（与桌面版同源），
    远程广告以 source=remote 标记、ID 取负，避免与本地广告冲突。
    远程拉取失败时静默降级，仅返回本地广告。
    """
    today = date.today()

    # 查询已复核且未过期的本地广告
    query = select(Advertisement).where(
        Advertisement.status == AdStatus.APPROVED,
        (Advertisement.expire_date >= today) | (Advertisement.expire_date.is_(None))
    ).order_by(desc(Advertisement.created_at))

    result = await db.execute(query)
    ads = result.scalars().all()

    # 本地广告按类型分组
    carousel_ads = []
    text_ads = []
    # 本地去重键（标题, 链接），用于过滤远程重复广告
    dedup_keys: set[tuple[str | None, str | None]] = set()

    for ad in ads:
        ad_data = serialize_ad(ad)
        dedup_keys.add((ad.title, ad.link))
        if ad.ad_type == AdType.CAROUSEL:
            carousel_ads.append(ad_data)
        else:
            text_ads.append(ad_data)

    # 合并远程官方广告（失败时返回空，不影响本地展示）；
    # 若请求本身来自服务器间远程拉取，则不再二次拉取，避免递归自调用
    if not is_remote_fetch_request(user_agent):
        remote = await fetch_remote_public_ads(local_dedup_keys=dedup_keys)
        carousel_ads.extend(remote.get("carousel", []))
        text_ads.extend(remote.get("text", []))

    return ApiResponse(
        success=True,
        data={
            "carousel": carousel_ads,
            "text": text_ads,
        }
    )


def serialize_ad(ad: Advertisement) -> dict:
    """序列化广告对象"""
    return {
        "id": ad.id,
        "user_id": ad.user_id,
        "title": ad.title,
        "content": ad.content,
        "link": ad.link,
        "expire_date": safe_isoformat(ad.expire_date),
        "image_url": ad.image_url,
        "ad_type": ad.ad_type.value if ad.ad_type else "text",
        "months": ad.months,
        "total_amount": ad.total_amount,
        "status": ad.status.value if ad.status else "unpaid",
        "source": "local",
        "created_at": safe_isoformat(ad.created_at),
        "updated_at": safe_isoformat(ad.updated_at),
    }


async def _get_ad_price(db: AsyncSession, ad_type: str) -> str | None:
    """从系统设置获取广告单月价格"""
    key = f"{AD_PRICE_KEY_PREFIX}{ad_type}"
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


@router.get("/prices", response_model=ApiResponse)
async def get_ad_prices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取各广告类型的单月价格"""
    prices = {}
    for ad_type in AdType:
        price = await _get_ad_price(db, ad_type.value)
        prices[ad_type.value] = price or "0"
    return ApiResponse(success=True, data=prices)


# ==================== 广告管理（管理员） ====================

@router.get("/admin", response_model=ApiResponse)
async def get_all_ads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    ad_type: str | None = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取所有广告列表（管理员）"""
    filters = []
    if status:
        try:
            filters.append(Advertisement.status == AdStatus(status))
        except ValueError:
            pass
    if ad_type:
        try:
            filters.append(Advertisement.ad_type == AdType(ad_type))
        except ValueError:
            pass

    ads, total = await execute_paginated_with_filters(
        db, Advertisement,
        filters=filters,
        order_by=[desc(Advertisement.created_at)],
        page=page, page_size=page_size,
    )

    return ApiResponse(
        success=True,
        data={
            "items": [serialize_ad(ad) for ad in ads],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.put("/admin/{ad_id}/approve", response_model=ApiResponse)
async def approve_ad(
    ad_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """复核广告（管理员）"""
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    
    if not ad:
        return ApiResponse(success=False, message="广告不存在")
    
    ad.status = AdStatus.APPROVED
    await db.commit()
    
    return ApiResponse(success=True, message="复核成功")


@router.put("/admin/{ad_id}/reject", response_model=ApiResponse)
async def reject_ad(
    ad_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """取消复核（管理员）"""
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    
    if not ad:
        return ApiResponse(success=False, message="广告不存在")
    
    ad.status = AdStatus.PENDING
    await db.commit()
    
    return ApiResponse(success=True, message="已取消复核")


@router.delete("/admin/{ad_id}", response_model=ApiResponse)
async def delete_ad_admin(
    ad_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除广告（管理员）"""
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    
    if not ad:
        return ApiResponse(success=False, message="广告不存在")
    
    await db.delete(ad)
    await db.commit()
    
    return ApiResponse(success=True, message="删除成功")


@router.put("/admin/{ad_id}", response_model=ApiResponse)
async def update_ad_admin(
    ad_id: int,
    title: str,
    ad_type: str,
    content: str | None = None,
    link: str | None = None,
    expire_date: str | None = None,
    image_url: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """修改广告（管理员），对内容进行XSS转义"""
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    
    if not ad:
        return ApiResponse(success=False, message="广告不存在")
    
    # XSS转义
    ad.title = escape_xss(title)
    ad.content = escape_xss(content)
    ad.link = link  # 链接不转义，但前端渲染时需注意
    ad.image_url = image_url
    
    if expire_date:
        try:
            ad.expire_date = date.fromisoformat(expire_date)
        except ValueError:
            return ApiResponse(success=False, message="日期格式错误")
    else:
        ad.expire_date = None
    
    try:
        ad.ad_type = AdType(ad_type)
    except ValueError:
        return ApiResponse(success=False, message="无效的广告类型")
    
    if status:
        try:
            ad.status = AdStatus(status)
        except ValueError:
            pass
    
    await db.commit()
    
    return ApiResponse(success=True, message="修改成功")


# ==================== 广告申请（所有用户） ====================

@router.get("", response_model=ApiResponse)
async def get_my_ads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取我的广告列表"""
    ads, total = await execute_paginated_with_filters(
        db, Advertisement,
        filters=[Advertisement.user_id == current_user.id],
        order_by=[desc(Advertisement.created_at)],
        page=page, page_size=page_size,
    )

    return ApiResponse(
        success=True,
        data={
            "items": [serialize_ad(ad) for ad in ads],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=ApiResponse)
async def create_ad(
    title: str,
    ad_type: str,
    months: int,
    content: str | None = None,
    link: str | None = None,
    image_url: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """新建广告申请，对内容进行XSS转义，根据月数自动计算到期日和费用"""
    try:
        t = AdType(ad_type)
    except ValueError:
        return ApiResponse(success=False, message="无效的广告类型")

    if months <= 0:
        return ApiResponse(success=False, message="月数必须大于0")

    # 从系统设置获取单月价格
    unit_price_str = await _get_ad_price(db, ad_type)
    if not unit_price_str:
        return ApiResponse(success=False, message="该广告类型尚未配置价格，请联系管理员")

    try:
        unit_price = Decimal(unit_price_str)
    except Exception:
        return ApiResponse(success=False, message="广告价格配置异常，请联系管理员")

    total_amount = unit_price * months
    exp_date = date.today() + relativedelta(months=months)

    # XSS转义
    ad = Advertisement(
        user_id=current_user.id,
        title=escape_xss(title),
        content=escape_xss(content),
        link=link,
        expire_date=exp_date,
        image_url=image_url,
        ad_type=t,
        months=months,
        total_amount=str(total_amount),
        status=AdStatus.UNPAID,
    )

    db.add(ad)
    await db.commit()
    await db.refresh(ad)

    return ApiResponse(success=True, message="提交成功", data={"id": ad.id, "total_amount": str(total_amount), "expire_date": exp_date.isoformat()})


@router.put("/{ad_id}", response_model=ApiResponse)
async def update_my_ad(
    ad_id: int,
    title: str,
    ad_type: str,
    months: int,
    content: str | None = None,
    link: str | None = None,
    image_url: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """修改我的广告（已复核的广告禁止修改），对内容进行XSS转义"""
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.user_id == current_user.id
        )
    )
    ad = result.scalar_one_or_none()
    
    if not ad:
        return ApiResponse(success=False, message="广告不存在或无权修改")
    
    # 已复核的广告禁止修改
    if ad.status == AdStatus.APPROVED:
        return ApiResponse(success=False, message="已复核的广告禁止修改")

    if months <= 0:
        return ApiResponse(success=False, message="月数必须大于0")

    try:
        t = AdType(ad_type)
    except ValueError:
        return ApiResponse(success=False, message="无效的广告类型")

    # 从系统设置获取单月价格
    unit_price_str = await _get_ad_price(db, ad_type)
    if not unit_price_str:
        return ApiResponse(success=False, message="该广告类型尚未配置价格，请联系管理员")

    try:
        unit_price = Decimal(unit_price_str)
    except Exception:
        return ApiResponse(success=False, message="广告价格配置异常，请联系管理员")

    total_amount = unit_price * months
    exp_date = date.today() + relativedelta(months=months)

    # XSS转义
    ad.title = escape_xss(title)
    ad.content = escape_xss(content)
    ad.link = link
    ad.image_url = image_url
    ad.ad_type = t
    ad.months = months
    ad.total_amount = str(total_amount)
    ad.expire_date = exp_date
    ad.status = AdStatus.UNPAID  # 修改后重新待付款
    
    await db.commit()
    
    return ApiResponse(success=True, message="修改成功")


@router.delete("/{ad_id}", response_model=ApiResponse)
async def delete_my_ad(
    ad_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除我的广告"""
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.user_id == current_user.id
        )
    )
    ad = result.scalar_one_or_none()
    
    if not ad:
        return ApiResponse(success=False, message="广告不存在或无权删除")
    
    await db.delete(ad)
    await db.commit()
    
    return ApiResponse(success=True, message="删除成功")


# ==================== 广告付款 ====================

@router.post("/{ad_id}/pay", response_model=ApiResponse)
async def create_ad_payment(
    ad_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """创建广告付款订单，生成支付宝二维码"""
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.user_id == current_user.id
        )
    )
    ad = result.scalar_one_or_none()

    if not ad:
        return ApiResponse(success=False, message="广告不存在")

    if ad.status != AdStatus.UNPAID:
        return ApiResponse(success=False, message="该广告当前状态不可付款")

    if not ad.total_amount:
        return ApiResponse(success=False, message="广告费用信息异常")

    amount = ad.total_amount

    # 加载支付宝配置
    try:
        config = await AlipayService.load_config(db)
        alipay = AlipayService(config)
    except ValueError as e:
        logger.error(f"支付宝配置错误: {e}")
        return ApiResponse(success=False, message=f"支付宝配置错误: {e}")

    # 生成订单号
    order_no = AlipayService.generate_order_no()

    order_data = {
        'out_trade_no': order_no,
        'total_amount': amount,
        'subject': f'广告申请付款 - {ad.title}',
        'body': f'广告申请付款 ID:{ad.id}',
        'timeout_express': '30m',
    }
    pay_result = alipay.create_f2f_pay(order_data)

    if not pay_result or not pay_result.get('success'):
        error_msg = pay_result.get('error', '生成支付二维码失败') if pay_result else '生成支付二维码失败'
        return ApiResponse(success=False, message=error_msg)

    # 保存充值订单（复用 recharge_orders 表）
    from common.models.recharge_order import RechargeOrder
    order = RechargeOrder(
        order_no=order_no,
        user_id=current_user.id,
        amount=amount,
        status='pending',
        qr_code=pay_result['qr_code'],
    )
    db.add(order)
    await db.commit()

    return ApiResponse(
        success=True,
        data={
            'order_no': order_no,
            'amount': amount,
            'qr_code': pay_result['qr_code'],
            'ad_id': ad.id,
        }
    )


@router.post("/{ad_id}/pay/notify", response_model=ApiResponse)
async def ad_payment_notify(
    ad_id: int,
    order_no: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """前端轮询确认广告付款状态，如果支付宝已付款则完成广告付款流程"""
    from common.models.recharge_order import RechargeOrder

    # 查询广告
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.user_id == current_user.id
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        return ApiResponse(success=False, message="广告不存在")

    # 已经完成付款
    if ad.status != AdStatus.UNPAID:
        return ApiResponse(success=True, data={"status": ad.status.value})

    # 查询充值订单状态
    order_result = await db.execute(
        select(RechargeOrder).where(
            RechargeOrder.order_no == order_no,
            RechargeOrder.user_id == current_user.id
        )
    )
    order = order_result.scalar_one_or_none()
    if not order:
        return ApiResponse(success=True, data={"status": "pending"})

    if order.status != 'paid':
        return ApiResponse(success=True, data={"status": "pending"})

    # 支付已完成 -> 完成广告付款流程
    amount = Decimal(ad.total_amount or '0')

    # 1. 广告状态变为已复核
    ad.status = AdStatus.APPROVED

    # 2. 查找管理员用户（第一个管理员）用于记录收入流水
    admin_result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN).limit(1)
    )
    admin_user = admin_result.scalar_one_or_none()

    # 3. 管理员收入流水
    if admin_user:
        # 获取管理员余额
        admin_balance_result = await db.execute(
            select(UserSetting).where(
                UserSetting.user_id == admin_user.id,
                UserSetting.key == BALANCE_KEY,
            )
        )
        admin_balance_setting = admin_balance_result.scalar_one_or_none()
        admin_balance_before = Decimal(admin_balance_setting.value or '0') if admin_balance_setting else Decimal('0')
        admin_balance_after = admin_balance_before + amount

        if admin_balance_setting:
            admin_balance_setting.value = str(admin_balance_after)
        else:
            admin_balance_setting = UserSetting(
                user_id=admin_user.id,
                key=BALANCE_KEY,
                value=str(admin_balance_after),
                description='用户余额',
            )
            db.add(admin_balance_setting)

        admin_flow = FundFlow(
            user_id=admin_user.id,
            type='income',
            amount=str(amount),
            balance_before=str(admin_balance_before),
            balance_after=str(admin_balance_after),
            description=f'广告申请收入（广告ID:{ad.id} 标题:{ad.title}）',
        )
        db.add(admin_flow)

    # 4. 广告申请用户支出流水
    user_balance_result = await db.execute(
        select(UserSetting).where(
            UserSetting.user_id == current_user.id,
            UserSetting.key == BALANCE_KEY,
        )
    )
    user_balance_setting = user_balance_result.scalar_one_or_none()
    user_balance_before = Decimal(user_balance_setting.value or '0') if user_balance_setting else Decimal('0')
    user_balance_after = user_balance_before  # 支付宝直接付款，不扣余额

    user_flow = FundFlow(
        user_id=current_user.id,
        type='expense',
        amount=str(amount),
        balance_before=str(user_balance_before),
        balance_after=str(user_balance_after),
        description=f'广告申请（广告ID:{ad.id} 标题:{ad.title}）',
    )
    db.add(user_flow)

    await db.commit()
    logger.info(f"广告付款完成: ad_id={ad.id}, user_id={current_user.id}, amount={amount}")

    return ApiResponse(success=True, data={"status": "approved"})
