"""四类广告统一付款及结算服务，支付宝回调与浏览器轮询共享幂等结算。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.alipay_service import AlipayService
from app.services.advertisement_orders import find_payment_order, lock_order_advertisement, payment_expired
from common.models.advertisement import Advertisement, AdStatus
from common.models.fund_flow import FundFlow
from common.models.recharge_order import RechargeOrder
from common.models.user import User, UserRole
from common.models.user_setting import UserSetting
from common.schemas.common import ApiResponse
from common.utils.time_utils import get_beijing_now_naive


class AdvertisementPaymentService:
    """接收请求或回调会话，广告支付不改变申请用户余额。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, ad_id: int, user_id: int) -> ApiResponse:
        """生成当前用户广告的支付宝二维码，保存广告与支付订单的明确关联。"""
        ad = (await self.session.execute(select(Advertisement).where(
            Advertisement.id == ad_id, Advertisement.user_id == user_id, Advertisement.is_deleted.is_(False),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not ad:
            return ApiResponse(success=False, code=40001, message="广告不存在")
        if ad.status != AdStatus.UNPAID:
            return ApiResponse(success=False, code=40001, message="该广告当前状态不可付款")
        try:
            amount = Decimal(ad.total_amount or "0")
            if not amount.is_finite() or amount <= 0:
                raise ValueError("广告费用信息异常")
        except (InvalidOperation, ValueError):
            return ApiResponse(success=False, code=40001, message="广告费用信息异常")
        if await find_payment_order(self.session, ad.id, user_id, "paid"):
            return ApiResponse(success=False, code=40001, message="该广告已有已支付订单，请刷新列表或联系管理员")
        pending = await find_payment_order(self.session, ad.id, user_id, "pending")
        if pending and not payment_expired(pending):
            try:
                pending_amount = Decimal(pending.amount)
                valid_pending = pending_amount.is_finite() and pending_amount == amount and bool(pending.qr_code)
            except InvalidOperation:
                valid_pending = False
            if not valid_pending:
                return ApiResponse(success=False, code=40001, message="已有支付订单信息异常，请联系管理员")
            await self.session.commit()
            return ApiResponse(success=True, data={"order_no": pending.order_no, "amount": pending.amount,
                "qr_code": pending.qr_code, "ad_id": ad.id})
        try:
            alipay = AlipayService(await AlipayService.load_config(self.session))
        except ValueError as exc:
            logger.opt(exception=exc).error("广告付款支付宝配置错误：ad_id={}", ad_id)
            return ApiResponse(success=False, code=40001, message=f"支付宝配置错误：{exc}")
        order_no = AlipayService.generate_order_no()
        result = alipay.create_f2f_pay({
            "out_trade_no": order_no, "total_amount": str(amount), "subject": f"广告申请付款 - {ad.title}",
            "body": f"广告申请付款 ID:{ad.id}", "timeout_express": "30m",
        })
        if not result or not result.get("success") or not result.get("qr_code"):
            return ApiResponse(success=False, code=40001, message=(result or {}).get("error") or "生成支付二维码失败")
        self.session.add(RechargeOrder(order_no=order_no, user_id=user_id, amount=str(amount), order_type="ad",
            ad_id=ad.id, status="pending", qr_code=result["qr_code"], created_at=get_beijing_now_naive()))
        await self.session.commit()
        logger.info("广告付款订单创建成功：ad_id={} type={} order_no={} amount={}", ad.id, ad.ad_type.value, order_no, amount)
        return ApiResponse(success=True, data={"order_no": order_no, "amount": str(amount), "qr_code": result["qr_code"], "ad_id": ad.id})

    async def settle(self, order: RechargeOrder, ad_id: int | None = None) -> bool:
        """结算已支付订单；调用方先锁广告再锁订单，随后锁管理员，成功后由调用方提交事务。"""
        if order.order_type != "ad" or order.status != "paid":
            raise ValueError("订单不是已支付的广告订单")
        target_id = order.ad_id if order.ad_id is not None else ad_id
        if target_id is None:
            # 历史未关联订单仍由原轮询入口提供广告ID，不猜测归属或改写历史广告。
            return False
        if ad_id is not None and order.ad_id is not None and order.ad_id != ad_id:
            raise ValueError("支付订单与广告不匹配")
        ad = (await self.session.execute(select(Advertisement).where(
            Advertisement.id == target_id, Advertisement.user_id == order.user_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not ad:
            raise ValueError("支付订单对应的广告不存在")
        if order.ad_settled_at:
            return True
        amount = Decimal(order.amount)
        if not amount.is_finite() or amount <= 0 or amount != Decimal(ad.total_amount or "0"):
            raise ValueError("支付金额与当前广告费用不匹配，请联系管理员")
        # 仅历史未关联订单保留旧状态判定，避免再次增加旧版本已记账的收入。
        # 新订单以自身结算标记幂等，每笔真实付款必须记录收入，复核状态不能代替付款事实。
        if order.ad_id is None and ad.status != AdStatus.UNPAID:
            order.ad_id = ad.id
            order.ad_settled_at = get_beijing_now_naive()
            logger.info("广告已生效，跳过重复结算：ad_id={} order_no={}", ad.id, order.order_no)
            return True
        admin = (await self.session.execute(select(User).where(User.role == UserRole.ADMIN)
            .order_by(User.id).limit(1).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not admin:
            raise ValueError("管理员账户不存在，广告付款结算失败")
        setting = (await self.session.execute(select(UserSetting).where(
            UserSetting.user_id == admin.id, UserSetting.key == "balance",
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        before = Decimal(setting.value or "0") if setting else Decimal("0")
        if not before.is_finite():
            raise ValueError("管理员余额数据异常，广告付款结算失败，请联系管理员")
        after = before + amount
        if setting:
            setting.value = str(after)
        else:
            self.session.add(UserSetting(user_id=admin.id, key="balance", value=str(after), description="用户余额"))
        self.session.add(FundFlow(user_id=admin.id, type="income", amount=str(amount), balance_before=str(before),
            balance_after=str(after), order_id=order.id, description=f"广告申请收入（广告ID:{ad.id} 标题:{ad.title}）"))
        if ad.status == AdStatus.UNPAID and not ad.is_deleted:
            ad.status = AdStatus.APPROVED
        order.ad_id, order.ad_settled_at = ad.id, get_beijing_now_naive()
        logger.info("广告付款结算完成：ad_id={} type={} order_no={} amount={}", ad.id, ad.ad_type.value, order.order_no, amount)
        return True

    async def poll(self, ad_id: int, order_no: str, user_id: int) -> ApiResponse:
        """查询当前用户付款状态，已支付时复用统一结算；拒绝跨广告、充值订单及重复消费。"""
        try:
            await lock_order_advertisement(self.session, order_no, user_id=user_id, fallback_ad_id=ad_id)
            order = (await self.session.execute(select(RechargeOrder).where(
                RechargeOrder.order_no == order_no, RechargeOrder.user_id == user_id,
            ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if not order:
                return ApiResponse(success=False, code=40001, message="支付订单不存在或无权查询")
            if order.order_type != "ad" or (order.ad_id is not None and order.ad_id != ad_id):
                return ApiResponse(success=False, code=40001, message="支付订单与广告不匹配")
            ad = (await self.session.execute(select(Advertisement).where(
                Advertisement.id == ad_id, Advertisement.user_id == user_id,
                Advertisement.is_deleted.is_(False),
            ))).scalar_one_or_none()
            if not ad:
                return ApiResponse(success=False, code=40001, message="广告不存在")
            if order.status != "paid":
                if order.status in ("expired", "failed") or payment_expired(order):
                    return ApiResponse(success=False, code=40001, message="支付订单已失效，请重新生成支付二维码；如已付款请联系管理员")
                if order.status != "pending":
                    return ApiResponse(success=False, code=40001, message="支付订单状态异常，请联系管理员")
                return ApiResponse(success=True, data={"status": "pending"})
            await self.settle(order, ad_id)
            await self.session.commit()
            return ApiResponse(success=True, data={"status": ad.status.value, "paid": True})
        except (ValueError, InvalidOperation) as exc:
            await self.session.rollback()
            logger.opt(exception=exc).error("广告付款查询失败：ad_id={} order_no={} user_id={}", ad_id, order_no, user_id)
            return ApiResponse(success=False, code=40001, message=str(exc))

    async def notify(self, order: RechargeOrder, notify_data: dict) -> None:
        """校验支付宝实际支付金额并提交广告结算；失败由回调入口回滚并返回失败供支付宝重试。"""
        paid_amount = Decimal(str(notify_data.get('total_amount', '')))
        if not paid_amount.is_finite() or paid_amount != Decimal(order.amount):
            raise ValueError('支付宝回调金额与广告订单金额不一致')
        if order.status != 'paid':
            order.status = 'paid'
            order.trade_no = notify_data.get('trade_no', '')
            order.paid_at = get_beijing_now_naive()
        await self.settle(order)
        await self.session.commit()
