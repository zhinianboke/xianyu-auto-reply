"""广告管理、申请、类型字典、费用计算与按展示位置读取的统一服务。"""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.advertisement_db import retry_ad_read
from app.services.advertisement_orders import payment_locked_ids
from app.services.remote_content_service import fetch_remote_public_ads, is_remote_fetch_request
from common.models.advertisement import Advertisement, AdStatus, AdType
from common.models.data_dictionary import XYDataDictionary
from common.models.system_setting import SystemSetting
from common.schemas.common import ApiResponse
from common.services.advertisement_types import AD_TYPE_DICTIONARY, get_placement_types, parse_ad_price
from common.utils.pagination import execute_paginated_with_filters
from common.utils.text_utils import escape_xss
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


class AdvertisementService:
    """广告服务，接收请求会话，不创建数据库连接池。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _prepare_content(title: str, content: str | None, link: str | None, image_url: str | None) -> tuple[str, str | None]:
        """在写库前统一校验转义后的标题、正文及地址长度，避免数据库截断或报错。"""
        if not title.strip():
            raise ValueError("广告标题不能为空")
        safe_title, safe_content = escape_xss(title.strip()), escape_xss(content)
        if len(safe_title) > 200:
            raise ValueError("广告标题过长，转义后不能超过200个字符，请缩短标题或减少特殊字符")
        if safe_content and len(safe_content.encode("utf-8")) > 65535:
            raise ValueError("广告正文过长，请缩短内容")
        if any(value and len(value) > 500 for value in (link, image_url)):
            raise ValueError("广告链接和图片地址不能超过500个字符")
        return safe_title, safe_content

    @retry_ad_read
    async def get_types(self) -> ApiResponse:
        """从数据字典读取四类广告的中文名称及费用键。"""
        rows = (await self.session.execute(select(XYDataDictionary).where(
            XYDataDictionary.dict_type == AD_TYPE_DICTIONARY,
            XYDataDictionary.enabled.is_(True),
            XYDataDictionary.dict_value.in_([item.value for item in AdType]),
        ).order_by(XYDataDictionary.sort_order))).scalars().all()
        if len(rows) != len(AdType):
            return ApiResponse(success=False, code=40001, message="广告类型字典未初始化完整，请联系管理员")
        return ApiResponse(success=True, data=[{
            "value": row.dict_value, "label": row.dict_label, "price_key": f"ad_price.{row.dict_value}",
        } for row in rows])

    async def _labels(self) -> dict[str, str]:
        """批量读取类型中文名称，避免列表逐行查询。"""
        result = await self.session.execute(select(XYDataDictionary.dict_value, XYDataDictionary.dict_label).where(
            XYDataDictionary.dict_type == AD_TYPE_DICTIONARY,
        ))
        return dict(result.all())

    @staticmethod
    def serialize(ad: Advertisement, labels: dict[str, str]) -> dict:
        """返回广告数据和字典中文名称，保持原有接口字段兼容。"""
        return {
            "id": ad.id, "user_id": ad.user_id, "title": ad.title, "content": ad.content,
            "link": ad.link, "expire_date": safe_isoformat(ad.expire_date), "image_url": ad.image_url,
            "ad_type": ad.ad_type.value, "ad_type_label": labels.get(ad.ad_type.value, ad.ad_type.value),
            "months": ad.months, "total_amount": ad.total_amount, "status": ad.status.value,
            "source": "local", "created_at": safe_isoformat(ad.created_at), "updated_at": safe_isoformat(ad.updated_at),
        }

    @retry_ad_read
    async def get_public(self, placement: str, user_agent: str | None) -> ApiResponse:
        """仅查询指定位置已复核、未删除且未过期的广告，再合并相同位置的官方广告。"""
        try:
            carousel_type, text_type = get_placement_types(placement)
        except ValueError as exc:
            return ApiResponse(success=False, code=40001, message=str(exc))
        ads = (await self.session.execute(select(Advertisement).where(
            Advertisement.is_deleted.is_(False), Advertisement.status == AdStatus.APPROVED,
            Advertisement.ad_type.in_((carousel_type, text_type)),
            (Advertisement.expire_date >= get_beijing_now_naive().date()) | Advertisement.expire_date.is_(None),
        ).order_by(desc(Advertisement.created_at)))).scalars().all()
        labels = await self._labels()
        groups: dict[str, list[dict]] = {"carousel": [], "text": []}
        dedup_keys = set()
        for ad in ads:
            group = "carousel" if ad.ad_type == carousel_type else "text"
            groups[group].append(self.serialize(ad, labels))
            dedup_keys.add((ad.title, ad.link))
        if not is_remote_fetch_request(user_agent):
            remote = await fetch_remote_public_ads(local_dedup_keys=dedup_keys, placement=placement)
            for group in groups:
                groups[group].extend(remote.get(group, []))
        logger.info("公开广告查询完成：placement={} carousel={} text={}", placement, len(groups["carousel"]), len(groups["text"]))
        return ApiResponse(success=True, data=groups)

    @retry_ad_read
    async def get_prices(self) -> ApiResponse:
        """一次查询四类单月费用；未配置返回空值，禁止用零价格掩盖缺失配置。"""
        keys = [f"ad_price.{item.value}" for item in AdType]
        result = await self.session.execute(select(SystemSetting.key, SystemSetting.value).where(SystemSetting.key.in_(keys)))
        values = dict(result.all())
        return ApiResponse(success=True, data={item.value: values.get(f"ad_price.{item.value}", "") or "" for item in AdType})

    @retry_ad_read
    async def list_ads(self, page: int, page_size: int, *, user_id: int | None = None, status: str | None = None, ad_type: str | None = None) -> ApiResponse:
        """按管理员筛选或申请用户隔离读取广告列表，使用后端分页。"""
        filters = [Advertisement.is_deleted.is_(False)]
        if user_id is not None:
            filters.append(Advertisement.user_id == user_id)
        try:
            if status:
                filters.append(Advertisement.status == AdStatus(status))
            if ad_type:
                filters.append(Advertisement.ad_type == AdType(ad_type))
        except ValueError:
            return ApiResponse(success=False, code=40001, message="广告筛选类型或状态无效")
        ads, total = await execute_paginated_with_filters(self.session, Advertisement, filters=filters,
            order_by=[desc(Advertisement.created_at)], page=page, page_size=page_size)
        labels = await self._labels()
        items = [self.serialize(ad, labels) for ad in ads]
        if user_id is not None:
            locked = await payment_locked_ids(self.session, [ad.id for ad in ads])
            for item in items:
                item["can_edit"] = item["status"] != AdStatus.APPROVED.value and item["id"] not in locked
        return ApiResponse(success=True, data={"items": items, "total": total, "page": page, "page_size": page_size})

    async def _get_ad(self, ad_id: int, user_id: int | None = None) -> Advertisement | None:
        """锁定待修改广告，普通用户必须匹配申请用户，软删除广告不可再操作。"""
        statement = select(Advertisement).where(Advertisement.id == ad_id, Advertisement.is_deleted.is_(False))
        if user_id is not None:
            statement = statement.where(Advertisement.user_id == user_id)
        return (await self.session.execute(statement.with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()

    async def approve(self, ad_id: int, approved: bool) -> ApiResponse:
        """复核或取消复核广告，不修改类型及费用。"""
        ad = await self._get_ad(ad_id)
        if not ad:
            return ApiResponse(success=False, code=40001, message="广告不存在")
        ad.status = AdStatus.APPROVED if approved else AdStatus.PENDING
        await self.session.commit()
        return ApiResponse(success=True, message="复核成功" if approved else "已取消复核")

    async def delete(self, ad_id: int, user_id: int | None = None) -> ApiResponse:
        """软删除广告，保留广告、支付订单及历史消费数据。"""
        ad = await self._get_ad(ad_id, user_id)
        if not ad:
            return ApiResponse(success=False, code=40001, message="广告不存在或无权删除")
        ad.is_deleted = True
        await self.session.commit()
        logger.info("广告软删除完成：ad_id={} user_id={}", ad_id, user_id)
        return ApiResponse(success=True, message="删除成功")

    async def update_admin(self, ad_id: int, title: str, ad_type: str, *, content: str | None = None, link: str | None = None,
        expire_date: str | None = None, image_url: str | None = None, status: str | None = None) -> ApiResponse:
        """管理员编辑广告，先完成所有校验再修改实体，避免失败留下部分修改。"""
        try:
            selected_type = AdType(ad_type)
            selected_status = AdStatus(status) if status else None
            selected_date = date.fromisoformat(expire_date) if expire_date else None
        except ValueError:
            return ApiResponse(success=False, code=40001, message="广告类型、状态或日期格式无效")
        try:
            safe_title, safe_content = self._prepare_content(title, content, link, image_url)
        except ValueError as exc:
            return ApiResponse(success=False, code=40001, message=str(exc))
        ad = await self._get_ad(ad_id)
        if not ad:
            return ApiResponse(success=False, code=40001, message="广告不存在")
        if selected_status == AdStatus.UNPAID and ad.status != AdStatus.UNPAID and await payment_locked_ids(self.session, [ad.id], lock=True):
            return ApiResponse(success=False, code=40001, message="广告已有支付订单，不能改为待付款")
        ad.title, ad.content = safe_title, safe_content
        ad.link, ad.image_url, ad.ad_type, ad.expire_date = link, image_url, selected_type, selected_date
        if selected_status:
            ad.status = selected_status
        await self.session.commit()
        return ApiResponse(success=True, message="修改成功")

    async def save_application(self, user_id: int, title: str, ad_type: str, months: int, *, ad_id: int | None = None,
        content: str | None = None, link: str | None = None, image_url: str | None = None) -> ApiResponse:
        """创建或编辑当前用户广告申请，按所选类型价格计算总费用。"""
        try:
            selected_type = AdType(ad_type)
        except ValueError:
            return ApiResponse(success=False, code=40001, message="无效的广告类型")
        try:
            safe_title, safe_content = self._prepare_content(title, content, link, image_url)
        except ValueError as exc:
            return ApiResponse(success=False, code=40001, message=str(exc))
        if not 1 <= months <= 120:
            return ApiResponse(success=False, code=40001, message="购买月数必须为1至120个月")
        value = (await self.session.execute(select(SystemSetting.value).where(
            SystemSetting.key == f"ad_price.{selected_type.value}",
        ))).scalar_one_or_none()
        if not value or not value.strip():
            return ApiResponse(success=False, code=40001, message="该广告类型尚未配置价格，请联系管理员")
        try:
            price = parse_ad_price(value)
        except ValueError:
            return ApiResponse(success=False, code=40001, message="广告价格配置异常，请联系管理员")
        if price is None:
            return ApiResponse(success=False, code=40001, message="该广告类型尚未配置价格，请联系管理员")
        ad = await self._get_ad(ad_id, user_id) if ad_id is not None else Advertisement(user_id=user_id)
        if not ad:
            return ApiResponse(success=False, code=40001, message="广告不存在或无权修改")
        if ad_id is not None and ad.status == AdStatus.APPROVED:
            return ApiResponse(success=False, code=40001, message="已复核的广告禁止修改")
        if ad_id is not None and await payment_locked_ids(self.session, [ad.id], lock=True):
            return ApiResponse(success=False, code=40001, message="已生成支付订单的广告不能修改，请新建申请，避免付款信息不一致")
        ad.title, ad.content = safe_title, safe_content
        ad.link, ad.image_url, ad.ad_type = link, image_url, selected_type
        ad.months, ad.total_amount = months, f"{price * months:.2f}"
        ad.expire_date = get_beijing_now_naive().date() + relativedelta(months=months)
        ad.status = AdStatus.UNPAID
        self.session.add(ad)
        await self.session.commit()
        await self.session.refresh(ad)
        logger.info("广告申请保存完成：ad_id={} user_id={} type={} amount={}", ad.id, user_id, ad_type, ad.total_amount)
        return ApiResponse(success=True, message="修改成功" if ad_id else "提交成功", data={
            "id": ad.id, "total_amount": ad.total_amount, "expire_date": ad.expire_date.isoformat(),
        })
