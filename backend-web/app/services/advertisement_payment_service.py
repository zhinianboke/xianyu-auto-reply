"""四类广告统一付款及结算服务，支付宝回调与浏览器轮询共享幂等结算。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.advertisement_orders import find_payment_order, lock_order_advertisement, payment_expired
from app.services.alipay_service import AlipayService
from app.services.payment_config_service import CHANNEL_ALIPAY, CHANNEL_ZZCODE, PaymentConfigService
from app.services.zzcode_service import ZzcodeOrderResultUnknownError, ZzcodeService
from common.models.advertisement import Advertisement, AdStatus
from common.models.fund_flow import FundFlow
from common.models.recharge_order import RechargeOrder
from common.models.user import User, UserRole
from common.models.user_setting import UserSetting
from common.schemas.common import ApiResponse
from common.utils.payment_amount import normalize_zzcode_amount
from common.utils.time_utils import get_beijing_now_naive


class AdvertisementPaymentService:
    """接收请求或回调会话，广告支付不改变申请用户余额。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, ad_id: int, user_id: int, pay_type: str | None = None) -> ApiResponse:
        """按当前支付渠道生成广告付款目标，并保存广告与订单的明确关联。"""
        ad = (await self.session.execute(select(Advertisement).where(
            Advertisement.id == ad_id, Advertisement.user_id == user_id, Advertisement.is_deleted.is_(False),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not ad:
            return ApiResponse(success=False, code=40001, message="广告不存在")
        paid = await find_payment_order(self.session, ad.id, user_id, "paid")
        if paid:
            if paid.ad_settled_at:
                return ApiResponse(
                    success=True, message="支付订单已完成",
                    data=self._serialize_payment(paid, ad.id),
                )
            return ApiResponse(success=False, code=40001, message="该广告已有已支付订单，请刷新列表或联系管理员")
        if ad.status != AdStatus.UNPAID:
            return ApiResponse(success=False, code=40001, message="该广告当前状态不可付款")
        try:
            amount = Decimal(ad.total_amount or "0")
            if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
                raise ValueError("广告费用信息异常")
        except (InvalidOperation, ValueError):
            return ApiResponse(success=False, code=40001, message="广告费用信息异常")
        amount_text = f"{amount:.2f}"
        if not isinstance(ad.months, int) or not 1 <= ad.months <= 120:
            return ApiResponse(success=False, code=40001, message="广告购买月数异常，请联系管理员")
        pending = await find_payment_order(self.session, ad.id, user_id, "pending")
        if pending and not payment_expired(pending):
            try:
                pending_amount = Decimal(
                    normalize_zzcode_amount(pending.amount)
                    if pending.channel == CHANNEL_ZZCODE else pending.amount
                )
                valid_pending = (
                    pending_amount.is_finite() and pending_amount > 0
                    and (pending.channel == CHANNEL_ZZCODE or pending_amount == amount)
                    and bool(pending.qr_code or pending.pay_url)
                )
            except (InvalidOperation, TypeError, ValueError):
                valid_pending = False
            if not valid_pending:
                return ApiResponse(success=False, code=40001, message="已有支付订单信息异常，请联系管理员")
            await self.session.commit()
            return ApiResponse(success=True, data=self._serialize_payment(pending, ad.id))
        config_service = PaymentConfigService(self.session)
        channel = await config_service.get_channel()
        order_no = AlipayService.generate_order_no()
        saved_zzcode_trade_no = ""
        if channel == CHANNEL_ZZCODE:
            try:
                resolved_type = await config_service.resolve_pay_type(pay_type)
                zzcode = ZzcodeService(await config_service.get_zzcode_config())
            except ValueError as exc:
                return ApiResponse(success=False, code=40001, message=str(exc))
            order = RechargeOrder(order_no=order_no, user_id=user_id, amount=amount_text, order_type="ad",
                channel=channel, pay_type=resolved_type, ad_id=ad.id, status="pending",
                callback_merchant_id=str(zzcode.config["pid"]), callback_verify_key=str(zzcode.config["key"]),
                created_at=get_beijing_now_naive())
            self.session.add(order)
            await self.session.commit()
            try:
                target = await zzcode.create_order(order_no, amount_text, f"广告申请付款 - {ad.title}", resolved_type)
            except ZzcodeOrderResultUnknownError as exc:
                await lock_order_advertisement(self.session, order_no, user_id=user_id, fallback_ad_id=ad.id)
                locked_order = (await self.session.execute(select(RechargeOrder).where(
                    RechargeOrder.order_no == order_no,
                ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
                if locked_order and locked_order.status == "paid" and locked_order.ad_settled_at:
                    return ApiResponse(success=True, message="支付订单已完成", data=self._serialize_payment(locked_order, ad.id))
                logger.error(
                    "码支付广告下单结果未知，保留待支付订单等待回调或人工核查：ad_id={} order_no={} trade_no={} exception={}",
                    ad.id, order_no, locked_order.trade_no if locked_order else None, exc,
                )
                message = "支付已通知但无法确认最终金额，请联系管理员" if locked_order and locked_order.trade_no else str(exc)
                return ApiResponse(success=False, code=40001, message=message)
            except ValueError as exc:
                await lock_order_advertisement(self.session, order_no, user_id=user_id, fallback_ad_id=ad.id)
                locked_order = (await self.session.execute(select(RechargeOrder).where(
                    RechargeOrder.order_no == order_no,
                ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
                if locked_order and locked_order.status == "paid" and locked_order.ad_settled_at:
                    return ApiResponse(success=True, message="支付订单已完成", data=self._serialize_payment(locked_order, ad.id))
                if locked_order and locked_order.status == "pending":
                    # 无法读取下单结果时不能猜测唯一尾数后的最终金额；已收到
                    # 成功通知也只保留交易号，禁止按广告原始费用误结算。
                    locked_order.status = "failed"
                    await self.session.commit()
                if locked_order and locked_order.trade_no:
                    return ApiResponse(success=False, code=40001, message="支付已通知但无法确认最终金额，请联系管理员")
                return ApiResponse(success=False, code=40001, message=str(exc))
            await lock_order_advertisement(self.session, order_no, user_id=user_id, fallback_ad_id=ad.id)
            order = (await self.session.execute(select(RechargeOrder).where(
                RechargeOrder.order_no == order_no,
            ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if not order:
                return ApiResponse(success=False, code=40001, message="支付订单不存在")
            # 下单成功响应是唯一尾数最终金额的来源。失败/过期通知可能先于响应到达，
            # 即使尚未暂存成功交易号，也必须保存最终金额供后续成功通知结算。
            can_confirm_amount = order.status in {"pending", "failed", "expired"}
            if target.get("money") not in (None, ""):
                actual_amount = str(target["money"])
                if can_confirm_amount:
                    order.amount = actual_amount
                elif order.status == "paid" and Decimal(order.amount) != Decimal(actual_amount):
                    logger.error(
                        "码支付广告下单金额与已结算回调金额不一致：ad_id={} order_no={} order_amount={} upstream_amount={}",
                        ad.id, order_no, order.amount, actual_amount,
                    )
            if can_confirm_amount:
                # 成功下单响应已经返回，最终应付金额以上游 money 为准；未返回
                # money 时保留提交金额，回调通知不得再用自身 money 覆盖。
                order.zzcode_amount_confirmed = True
            self._apply_target(order, target)
            if can_confirm_amount and order.trade_no:
                saved_zzcode_trade_no = str(order.trade_no)
        else:
            try:
                alipay = AlipayService(await config_service.get_alipay_config())
            except ValueError as exc:
                logger.opt(exception=exc).error("广告付款支付宝配置错误：ad_id={}", ad_id)
                return ApiResponse(success=False, code=40001, message=f"支付宝配置错误：{exc}")
            order = RechargeOrder(order_no=order_no, user_id=user_id, amount=amount_text, order_type="ad",
                channel=CHANNEL_ALIPAY, ad_id=ad.id, status="pending",
                callback_merchant_id=alipay.config["app_id"], callback_verify_key=alipay.config["alipay_public_key"],
                created_at=get_beijing_now_naive())
            self.session.add(order)
            await self.session.commit()
            result = await alipay.create_f2f_pay({
                "out_trade_no": order_no, "total_amount": amount_text, "subject": f"广告申请付款 - {ad.title}",
                "body": f"广告申请付款 ID:{ad.id}", "timeout_express": "30m",
            })
            order = (await self.session.execute(select(RechargeOrder).where(
                RechargeOrder.order_no == order_no,
            ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if not order:
                return ApiResponse(success=False, code=40001, message="支付订单不存在")
            if not result or not result.get("success") or not result.get("qr_code"):
                if order.status == "paid" and order.ad_settled_at:
                    return ApiResponse(success=True, message="支付订单已完成", data=self._serialize_payment(order, ad.id))
                if order.status == "pending":
                    order.status = "failed"
                    await self.session.commit()
                return ApiResponse(success=False, code=40001, message=(result or {}).get("error") or "生成支付二维码失败")
            order.qr_code = result["qr_code"]
            order.pay_target_kind = "qrcode"
        await self.session.commit()
        if saved_zzcode_trade_no:
            return await self._settle_saved_zzcode_notify(
                order_no, saved_zzcode_trade_no, user_id, ad.id,
            )
        if channel == CHANNEL_ZZCODE and order.status in {"failed", "expired"}:
            return ApiResponse(success=False, code=40001, message="支付订单已失效，请重新生成支付订单")
        logger.info("广告付款订单创建成功：ad_id={} type={} channel={} order_no={} amount={}", ad.id, ad.ad_type.value, channel, order_no, order.amount)
        return ApiResponse(success=True, data=self._serialize_payment(order, ad.id))

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
        configured_amount = Decimal(ad.total_amount or "0")
        if not amount.is_finite() or amount <= 0:
            raise ValueError("广告支付订单金额无效，请联系管理员")
        if order.channel != CHANNEL_ZZCODE and amount != configured_amount:
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
        if not isinstance(ad.months, int) or not 1 <= ad.months <= 120:
            raise ValueError("广告购买月数异常，请联系管理员")
        if ad.status == AdStatus.UNPAID and not ad.is_deleted:
            ad.status = AdStatus.APPROVED
            ad.expire_date = get_beijing_now_naive().date() + relativedelta(months=ad.months)
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
                return ApiResponse(success=True, data={"status": "pending", "amount": order.amount})
            await self.settle(order, ad_id)
            await self.session.commit()
            return ApiResponse(success=True, data={"status": ad.status.value, "paid": True, "amount": order.amount})
        except (ValueError, InvalidOperation) as exc:
            await self.session.rollback()
            logger.opt(exception=exc).error("广告付款查询失败：ad_id={} order_no={} user_id={}", ad_id, order_no, user_id)
            return ApiResponse(success=False, code=40001, message=str(exc))

    async def notify(self, order: RechargeOrder, notify_data: dict, *, source: str = "支付宝异步通知",
        amount_key: str = "total_amount", verify_amount: bool = True) -> None:
        """校验实际支付金额并提交广告结算；失败由回调入口回滚并通知上游重试。

        Args:
            order: 已锁定的广告支付订单。
            notify_data: 已验签的支付渠道回调数据。
            source: 回调来源说明，用于异常日志及错误信息。
            amount_key: 回调数据中的实付金额字段名。
            verify_amount: 是否要求实付金额严格等于订单金额，支付宝使用此模式。
        Returns:
            无返回值；结算成功后提交订单、管理员余额和资金流水。
        """
        if verify_amount:
            paid_amount = Decimal(str(notify_data.get(amount_key, '')))
            if not paid_amount.is_finite() or paid_amount != Decimal(order.amount):
                raise ValueError(f'{source}金额与广告订单金额不一致')
        trade_no = str(notify_data.get('trade_no') or '')
        if not trade_no:
            raise ValueError(f'{source}缺少上游交易号')
        if order.trade_no and order.trade_no != trade_no:
            raise ValueError(f'{source}交易号与已支付广告订单不一致')
        if not order.trade_no:
            order.trade_no = trade_no
        if order.status != 'paid':
            order.status = 'paid'
            order.paid_at = get_beijing_now_naive()
        await self.settle(order)
        await self.session.commit()

    async def _settle_saved_zzcode_notify(
        self, order_no: str, trade_no: str, user_id: int, ad_id: int,
    ) -> ApiResponse:
        """下单响应落库后结算此前已验签、但早于下单响应到达的广告付款通知。"""
        try:
            await lock_order_advertisement(
                self.session, order_no, user_id=user_id, fallback_ad_id=ad_id,
            )
            order = (await self.session.execute(select(RechargeOrder).where(
                RechargeOrder.order_no == order_no,
                RechargeOrder.user_id == user_id,
                RechargeOrder.order_type == "ad",
                RechargeOrder.ad_id == ad_id,
            ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if not order:
                raise ValueError("广告支付订单不存在")
            if order.channel != CHANNEL_ZZCODE:
                raise ValueError("广告支付订单渠道不匹配")
            if order.trade_no != trade_no:
                raise ValueError("广告支付订单交易号不匹配")
            if order.status == "paid" and order.ad_settled_at:
                return ApiResponse(success=True, message="支付订单已完成", data=self._serialize_payment(order, ad_id))
            if order.status not in {"pending", "failed", "expired"}:
                raise ValueError("广告支付订单状态异常")
            order.status = "paid"
            order.paid_at = get_beijing_now_naive()
            await self.settle(order, ad_id)
            await self.session.commit()
            return ApiResponse(success=True, message="支付订单已完成", data=self._serialize_payment(order, ad_id))
        except (ValueError, InvalidOperation) as exc:
            await self.session.rollback()
            logger.opt(exception=exc).error(
                "码支付广告下单响应补偿结算失败：ad_id={} order_no={}", ad_id, order_no,
            )
            return ApiResponse(success=False, code=40001, message=str(exc))
        except Exception as exc:
            await self.session.rollback()
            logger.opt(exception=exc).error(
                "码支付广告下单响应补偿结算异常：ad_id={} order_no={}", ad_id, order_no,
            )
            return ApiResponse(success=False, code=40001, message="支付已通知但广告结算失败，请联系管理员")

    @staticmethod
    def _apply_target(order: RechargeOrder, target: dict[str, str | None]) -> None:
        """将码支付返回的支付目标写入订单。"""
        kind = str(target.get("kind") or "")
        value = str(target.get("value") or "")
        order.pay_target_kind = kind
        order.qr_code = value if kind == "qrcode" else None
        order.pay_url = value if kind in {"payurl", "urlscheme"} else None

    @staticmethod
    def _serialize_payment(order: RechargeOrder, ad_id: int) -> dict:
        """返回广告付款弹窗所需数据。"""
        return {
            "order_no": order.order_no, "amount": order.amount, "ad_id": ad_id,
            "paid": order.status == "paid",
            "channel": order.channel, "pay_type": order.pay_type,
            "pay_target_kind": order.pay_target_kind, "qr_code": order.qr_code, "pay_url": order.pay_url,
        }
