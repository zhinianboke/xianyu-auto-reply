"""
淘宝联盟 - 选品广场API路由

功能：
1. 选品广场商品搜索（调用淘宝开放平台官方API）
2. 商品详情查询（多图、类目、是否包邮等）
3. 使用当前用户淘宝账号的AppKey/AppSecret鉴权
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models import User

router = APIRouter()


@router.get("/product-search")
async def search_products(
    keyword: str = Query(default="", description="搜索关键词"),
    page: int = Query(default=1, ge=1, description="页码，从1开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    sort: str = Query(default="default", description="排序方式"),
    material_id: int = Query(default=0, description="物料ID，0表示不限"),
    cat: str = Query(default="", description="商品类目ID，多个用逗号分隔"),
    has_coupon: bool | None = Query(default=None, description="是否有优惠券"),
    need_free_shipment: bool | None = Query(default=None, description="是否包邮"),
    is_tmall: bool | None = Query(default=None, description="是否天猫商品"),
    start_tk_rate: int | None = Query(default=None, ge=0, description="最低佣金率（基点，如1350表示13.5%）"),
    end_tk_rate: int | None = Query(default=None, ge=0, description="最高佣金率（基点）"),
    start_price: float | None = Query(default=None, ge=0, description="最低价格（元）"),
    end_price: float | None = Query(default=None, ge=0, description="最高价格（元）"),
    account_id: int | None = Query(default=None, description="指定账号ID"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    选品广场商品搜索

    调用淘宝开放平台 taobao.tbk.dg.material.optional.upgrade 接口
    使用当前用户淘宝账号的AppKey/AppSecret鉴权
    """
    from app.services.taobao_alliance_service import search_products as do_search

    # 淘宝API要求关键词和类目至少填一个
    if not keyword.strip() and not cat.strip():
        return {"success": False, "message": "请输入搜索关键词或选择商品类目"}

    result = await do_search(
        keyword=keyword.strip(),
        page=page,
        page_size=page_size,
        sort=sort,
        material_id=material_id,
        cat=cat.strip(),
        has_coupon=has_coupon,
        need_free_shipment=need_free_shipment,
        is_tmall=is_tmall,
        start_tk_rate=start_tk_rate,
        end_tk_rate=end_tk_rate,
        start_price=start_price,
        end_price=end_price,
        session=session,
        user_id=current_user.id,
        account_id=account_id,
    )
    return result


@router.get("/product-detail")
async def product_detail(
    item_id: str = Query(description="商品ID"),
    account_id: int | None = Query(default=None, description="指定账号ID"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    商品详情查询

    调用淘宝开放平台 taobao.tbk.item.info.get 接口
    返回商品多张图片、叶子类目、是否包邮等详情信息
    """
    from app.services.taobao_alliance_detail import get_product_detail

    result = await get_product_detail(
        item_id=item_id.strip(),
        session=session,
        user_id=current_user.id,
        account_id=account_id,
    )
    return result


@router.get("/create-tpwd")
async def create_tpwd_api(
    url: str = Query(description="推广链接（click_url 或 coupon_share_url）"),
    text: str = Query(default="", description="口令弹框内容（商品标题）"),
    logo: str = Query(default="", description="口令弹框logo图片URL"),
    account_id: int | None = Query(default=None, description="指定账号ID"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    淘口令生成

    调用淘宝开放平台 taobao.tbk.tpwd.create 接口
    将推广链接转为淘口令（如 ￥xxx￥），方便用户分享到手机端
    """
    from app.services.taobao_alliance_detail import create_tpwd

    if not url.strip():
        return {"success": False, "message": "推广链接不能为空"}

    result = await create_tpwd(
        text=text.strip() or "好物推荐",
        url=url.strip(),
        logo=logo.strip(),
        session=session,
        user_id=current_user.id,
        account_id=account_id,
    )
    return result
