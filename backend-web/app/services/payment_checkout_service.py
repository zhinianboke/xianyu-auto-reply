"""余额充值下单、支付回调验签和幂等入账。"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.advertisement_orders import lock_order_advertisement
from app.services.advertisement_payment_service import AdvertisementPaymentService
from app.services.alipay_service import AlipayService
from app.services.payment_config_service import (
    CHANNEL_ALIPAY,
    CHANNEL_ZZCODE,
    PaymentConfigService,
)
from app.services.zzcode_service import TRADE_SUCCESS, ZzcodeOrderResultUnknownError, ZzcodeService
from common.models.fund_flow import FundFlow
from common.models.recharge_order import RechargeOrder
from common.models.user_setting import UserSetting
from common.utils.time_utils import get_beijing_now_naive

logger = logging.getLogger(__name__)
BALANCE_KEY = "balance"


class PaymentCheckoutService:
    """处理余额充值的下单、通知和余额入账。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config = PaymentConfigService(session)

    async def create_recharge_order(self, user_id: int, amount: str, pay_type: str | None = None) -> dict[str, Any]:
        """按管理员启用的渠道创建充值订单，并返回二维码或支付链接。"""
        try:
            parsed = Decimal(amount.strip())
            if not parsed.is_finite() or parsed <= 0:
                return {"success": False, "code": 40001, "message": "充值金额必须大于0", "data": None}
            if parsed.as_tuple().exponent < -2:
                return {"success": False, "code": 40001, "message": "充值金额最多保留两位小数", "data": None}
            if parsed > Decimal("10000"):
                return {"success": False, "code": 40001, "message": "单次充值金额不能超过10000元", "data": None}
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            return {"success": False, "code": 40001, "message": "充值金额格式不正确", "data": None}

        amount_text = f"{parsed:.2f}"
        channel = await self.config.get_channel()
        order_no = AlipayService.generate_order_no()
        if channel == CHANNEL_ZZCODE:
            return await self._create_zzcode_order(user_id, order_no, amount_text, pay_type)
        return await self._create_alipay_order(user_id, order_no, amount_text)

    async def _create_alipay_order(self, user_id: int, order_no: str, amount: str) -> dict[str, Any]:
        """创建支付宝当面付订单；先落库保证极速回调能够查到商户订单。"""
        try:
            alipay = AlipayService(await self.config.get_alipay_config())
        except ValueError as exc:
            logger.exception("支付宝配置错误: order_no=%s exception=%s", order_no, exc)
            return {"success": False, "code": 40001, "message": f"支付宝配置错误：{exc}", "data": None}
        order = RechargeOrder(
            order_no=order_no, user_id=user_id, amount=amount, status="pending",
            channel=CHANNEL_ALIPAY, callback_merchant_id=alipay.config["app_id"],
            callback_verify_key=alipay.config["alipay_public_key"],
        )
        self.session.add(order)
        await self.session.commit()
        result = await alipay.create_f2f_pay({
            "out_trade_no": order_no, "total_amount": amount,
            "subject": f"余额充值 - {order_no}", "body": "用户余额充值", "timeout_express": "30m",
        })
        order = await self._lock_order(order_no)
        if not order:
            return {"success": False, "code": 40001, "message": "支付订单不存在", "data": None}
        if not result or not result.get("success") or not result.get("qr_code"):
            if order.status == "paid":
                return {"success": True, "code": 200, "message": "支付订单已完成", "data": self._payment_data(order)}
            if order.status == "pending":
                order.status = "failed"
                await self.session.commit()
            return {"success": False, "code": 40001, "message": (result or {}).get("error") or "生成支付二维码失败", "data": None}
        order.qr_code = result["qr_code"]
        order.pay_target_kind = "qrcode"
        await self.session.commit()
        return {"success": True, "code": 200, "message": "支付订单创建成功", "data": self._payment_data(order)}

    async def _create_zzcode_order(self, user_id: int, order_no: str, amount: str, requested_type: str | None) -> dict[str, Any]:
        """创建码支付订单；先落库保证极速回调能够查到商户订单。"""
        try:
            pay_type = await self.config.resolve_pay_type(requested_type)
            zzcode = ZzcodeService(await self.config.get_zzcode_config())
        except ValueError as exc:
            return {"success": False, "code": 40001, "message": str(exc), "data": None}
        order = RechargeOrder(
            order_no=order_no, user_id=user_id, amount=amount, status="pending",
            channel=CHANNEL_ZZCODE, pay_type=pay_type,
            callback_merchant_id=str(zzcode.config["pid"]), callback_verify_key=str(zzcode.config["key"]),
        )
        self.session.add(order)
        await self.session.commit()
        try:
            target = await zzcode.create_order(order_no, amount, "用户余额充值", pay_type)
        except ZzcodeOrderResultUnknownError as exc:
            order = await self._lock_order(order_no)
            if order and order.status == "paid":
                return {"success": True, "code": 200, "message": "支付订单已完成", "data": self._payment_data(order)}
            logger.error(
                "码支付充值下单结果未知，保留待支付订单等待回调或人工核查: order_no=%s trade_no=%s exception=%s",
                order_no, order.trade_no if order else None, exc,
            )
            message = "支付已通知但无法确认最终金额，请联系管理员" if order and order.trade_no else str(exc)
            return {"success": False, "code": 40001, "message": message, "data": None}
        except ValueError as exc:
            order = await self._lock_order(order_no)
            if order and order.status == "paid":
                return {"success": True, "code": 200, "message": "支付订单已完成", "data": self._payment_data(order)}
            if order and order.status == "pending":
                # 无法读取下单结果时不能猜测唯一尾数后的最终金额；即使已经
                # 收到成功通知，也保留交易号供人工核查，禁止按初始金额误入账。
                order.status = "failed"
                await self.session.commit()
            if order and order.trade_no:
                return {"success": False, "code": 40001, "message": "支付已通知但无法确认最终金额，请联系管理员", "data": None}
            return {"success": False, "code": 40001, "message": str(exc), "data": None}
        actual_amount = target.get("money") or amount
        order = await self._lock_order(order_no)
        if not order:
            return {"success": False, "code": 40001, "message": "支付订单不存在", "data": None}
        if order.status in {"pending", "failed", "expired"}:
            order.amount = str(actual_amount)
            # 成功下单响应已经返回，此时订单最终应付金额已确定；即使上游未显式返回
            # money，也按本系统提交的金额结算。失败/过期通知可能与下单响应交错到达，
            # 仍需先保存最终金额，避免后续成功通知按初始金额入账。
            order.zzcode_amount_confirmed = True
        elif order.status == "paid" and target.get("money") not in (None, "") and Decimal(order.amount) != Decimal(str(actual_amount)):
            logger.error(
                "码支付充值下单金额与已入账回调金额不一致: order_no=%s order_amount=%s upstream_amount=%s",
                order_no, order.amount, actual_amount,
            )
        self._apply_target(order, target)
        saved_trade_no = str(order.trade_no or "") if order.status != "paid" else ""
        await self.session.commit()
        if saved_trade_no:
            settled = await self._settle_saved_zzcode_recharge(order_no, saved_trade_no)
            if settled:
                return {"success": True, "code": 200, "message": "支付订单已完成", "data": self._payment_data(settled)}
            return {"success": False, "code": 40001, "message": "支付已通知但余额入账失败，请联系管理员", "data": None}
        if order.status in {"failed", "expired"}:
            return {"success": False, "code": 40001, "message": "支付订单已失效，请重新发起充值", "data": None}
        return {"success": True, "code": 200, "message": "支付订单创建成功", "data": self._payment_data(order)}

    async def handle_alipay_notify(self, values: dict[str, Any]) -> bool:
        """验证支付宝回调并按订单类型幂等结算。"""
        order_no = str(values.get("out_trade_no") or "")
        order = await self._get_order_for_verify(order_no)
        if not order:
            logger.error("支付宝通知订单不存在: order_no=%s values=%s", order_no, values)
            return False
        try:
            config = await self.config.get_alipay_config()
            if order.callback_merchant_id and order.callback_verify_key:
                config["app_id"] = order.callback_merchant_id
                config["alipay_public_key"] = order.callback_verify_key
            alipay = AlipayService(config, require_private_key=False)
        except ValueError as exc:
            logger.exception("支付宝通知无法加载配置: order_no=%s exception=%s", order_no, exc)
            return False
        if not alipay.verify_notify(values):
            return False
        trade_status = str(values.get("trade_status") or "")
        if trade_status == "TRADE_CLOSED":
            return await self._mark_payment_failed(order_no, CHANNEL_ALIPAY, "支付宝异步通知", values)
        if not AlipayService.is_trade_success(trade_status):
            return True
        return await self._settle_notify(
            order_no, str(values.get("trade_no") or ""), str(values.get("total_amount") or ""),
            CHANNEL_ALIPAY, "支付宝异步通知", values,
        )

    async def handle_zzcode_notify(self, values: dict[str, str]) -> bool:
        """验证码支付回调并按订单类型幂等结算。"""
        order_no = values.get("out_trade_no", "")
        order = await self._get_order_for_verify(order_no)
        if not order:
            logger.error("码支付通知订单不存在: order_no=%s values=%s", order_no, values)
            return False
        try:
            config = await self.config.get_zzcode_config()
            if order.callback_merchant_id and order.callback_verify_key:
                config["pid"] = order.callback_merchant_id
                config["key"] = order.callback_verify_key
            zzcode = ZzcodeService(config, require_order_config=False)
        except ValueError as exc:
            logger.exception("码支付通知无法加载配置: order_no=%s exception=%s", order_no, exc)
            return False
        if not zzcode.verify_notify(values):
            return False
        trade_status = values.get("trade_status")
        if trade_status in {"TRADE_CLOSED", "TRADE_FAILED", "FAIL"}:
            return await self._mark_payment_failed(order_no, CHANNEL_ZZCODE, "码支付异步通知", values)
        if trade_status != TRADE_SUCCESS:
            return True
        return await self._settle_notify(
            order_no, values.get("trade_no", ""), values.get("money", ""),
            CHANNEL_ZZCODE, "码支付异步通知", values,
        )

    async def _mark_payment_failed(self, order_no: str, channel: str, source: str, values: dict[str, Any]) -> bool:
        """将已验签的关闭通知落为失败状态，避免用户端永久轮询。"""
        await lock_order_advertisement(self.session, order_no)
        order = await self._lock_order(order_no)
        if not order:
            logger.error("%s关闭通知对应订单不存在: order_no=%s values=%s", source, order_no, values)
            return False
        if order.channel != channel:
            logger.error(
                "%s关闭通知渠道与订单不匹配: order_no=%s order_channel=%s values=%s",
                source, order_no, order.channel, values,
            )
            return False
        if order.status == "pending":
            order.status = "failed"
            await self.session.commit()
        return True

    async def _settle_notify(self, order_no: str, trade_no: str, paid_amount: str, channel: str, source: str, values: dict[str, Any]) -> bool:
        """锁定订单、核对渠道及金额，然后按余额充值或广告付款分流。"""
        await lock_order_advertisement(self.session, order_no)
        order = await self._lock_order(order_no)
        if not order:
            logger.error("%s订单不存在: order_no=%s values=%s", source, order_no, values)
            return False
        if order.channel != channel:
            logger.error("%s渠道与订单不匹配: order_no=%s order_channel=%s values=%s", source, order_no, order.channel, values)
            return False
        if channel == CHANNEL_ALIPAY:
            try:
                received_amount = Decimal(paid_amount)
                if not received_amount.is_finite() or received_amount != Decimal(order.amount):
                    raise ValueError("支付金额不匹配")
            except Exception as exc:
                logger.exception("%s金额校验失败: order_no=%s order_amount=%s paid_amount=%s values=%s exception=%s", source, order_no, order.amount, paid_amount, values, exc)
                return False
        if not trade_no:
            logger.error("%s缺少上游交易号: order_no=%s values=%s", source, order_no, values)
            return False
        if order.trade_no and order.trade_no != trade_no:
            logger.error(
                "%s交易号与订单已记录交易号不匹配: order_no=%s order_trade_no=%s trade_no=%s values=%s",
                source, order_no, order.trade_no, trade_no, values,
            )
            return False
        if channel == CHANNEL_ZZCODE and order.status != "paid":
            if not order.zzcode_amount_confirmed and not (
                order.pay_target_kind or order.qr_code or order.pay_url
            ):
                logger.warning(
                    "%s早于码支付下单结果落库，暂存交易号并等待下单请求主动结算: order_no=%s order_amount=%s notify_amount=%s values=%s",
                    source, order_no, order.amount, paid_amount, values,
                )
                if not order.trade_no:
                    order.trade_no = trade_no
                    try:
                        await self.session.commit()
                    except IntegrityError as exc:
                        await self.session.rollback()
                        logger.exception(
                            "%s暂存交易号唯一性冲突: order_no=%s trade_no=%s exception=%s",
                            source, order_no, trade_no, exc,
                        )
                return False
            logger.info(
                "%s已验签，忽略通知金额并按订单金额结算: order_no=%s order_amount=%s notify_amount=%s",
                source, order_no, order.amount, paid_amount,
            )
        if order.order_type == "ad":
            if order.status not in {"pending", "failed", "expired", "paid"}:
                logger.error("%s广告订单状态无效: order_no=%s status=%s values=%s", source, order_no, order.status, values)
                return False
            try:
                await AdvertisementPaymentService(self.session).notify(
                    order, values, source=source,
                    amount_key="money" if channel == CHANNEL_ZZCODE else "total_amount",
                    verify_amount=channel == CHANNEL_ALIPAY,
                )
                return True
            except Exception as exc:
                await self.session.rollback()
                logger.exception("%s广告付款结算失败: order_no=%s values=%s exception=%s", source, order_no, values, exc)
                return False
        if order.order_type != "recharge":
            logger.error("%s订单类型无效: order_no=%s order_type=%s values=%s", source, order_no, order.order_type, values)
            return False
        if order.status == "paid":
            if not order.trade_no:
                order.trade_no = trade_no
                try:
                    await self.session.commit()
                except IntegrityError as exc:
                    await self.session.rollback()
                    logger.exception("%s交易号唯一性冲突: order_no=%s trade_no=%s exception=%s", source, order_no, trade_no, exc)
                    return False
            return True
        if order.status not in {"pending", "failed", "expired"}:
            logger.error("%s订单状态或交易号无效: order_no=%s status=%s trade_no=%s", source, order_no, order.status, trade_no)
            return False
        try:
            # 码支付通知 money 可能仍是原始金额，实际应付金额以下单响应写入的
            # 订单金额为准；支付宝金额已在上方严格核对。
            await self._process_recharge_success(order, trade_no, channel)
            return True
        except (InvalidOperation, ValueError) as exc:
            await self.session.rollback()
            logger.error("%s充值入账失败: order_no=%s trade_no=%s exception=%s", source, order_no, trade_no, exc)
            return False

    async def _settle_saved_zzcode_recharge(self, order_no: str, trade_no: str) -> RechargeOrder | None:
        """下单响应落库后主动结算此前已验签、但早于下单响应到达的码支付通知。"""
        try:
            ok = await self._settle_notify(
                order_no, trade_no, "", CHANNEL_ZZCODE, "码支付下单响应补偿",
                {"out_trade_no": order_no, "trade_no": trade_no},
            )
            if not ok:
                return None
            order = await self._get_order_for_verify(order_no)
            return order if order and order.status == "paid" else None
        except Exception as exc:
            await self.session.rollback()
            logger.exception(
                "码支付下单响应补偿入账异常: order_no=%s trade_no=%s exception=%s",
                order_no, trade_no, exc,
            )
            return None

    async def _process_recharge_success(self, order: RechargeOrder, trade_no: str, channel: str) -> None:
        """锁定余额并原子写入余额、资金流水和支付状态。"""
        balance_setting = (await self.session.execute(select(UserSetting).where(
            UserSetting.user_id == order.user_id, UserSetting.key == BALANCE_KEY,
        ).with_for_update())).scalar_one_or_none()
        try:
            before = Decimal(balance_setting.value or "0") if balance_setting else Decimal("0")
            amount = Decimal(order.amount)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("账户余额或充值订单金额格式异常，请联系管理员") from exc
        if not before.is_finite():
            raise ValueError("账户余额数据异常，请联系管理员")
        if not amount.is_finite() or amount <= 0:
            raise ValueError("充值订单金额异常，请联系管理员")
        after = before + amount
        if balance_setting:
            balance_setting.value = str(after)
        else:
            self.session.add(UserSetting(user_id=order.user_id, key=BALANCE_KEY, value=str(after), description="用户余额"))
        channel_label = "码支付" if channel == CHANNEL_ZZCODE else "支付宝当面付"
        self.session.add(FundFlow(
            user_id=order.user_id, type="income", amount=str(order.amount), balance_before=str(before),
            balance_after=str(after), order_id=order.id,
            description=f"余额充值（{channel_label}）订单号: {order.order_no}",
        ))
        order.status = "paid"
        order.trade_no = trade_no
        order.paid_at = get_beijing_now_naive()
        order_no = order.order_no
        user_id = order.user_id
        order_amount = order.amount
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            logger.exception(
                "充值交易号唯一性冲突: channel=%s order_no=%s trade_no=%s exception=%s",
                channel, order_no, trade_no, exc,
            )
            raise ValueError("支付交易已被其他订单处理") from exc
        logger.info(
            "充值成功: channel=%s user_id=%s order_no=%s amount=%s balance_before=%s balance_after=%s",
            channel, user_id, order_no, order_amount, before, after,
        )

    async def _lock_order(self, order_no: str) -> RechargeOrder | None:
        """按订单号锁定并刷新订单状态。"""
        return (await self.session.execute(select(RechargeOrder).where(
            RechargeOrder.order_no == order_no,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()

    async def _get_order_for_verify(self, order_no: str) -> RechargeOrder | None:
        """在验签前只读查询订单，用订单快照兼容支付配置轮换。"""
        if not order_no:
            return None
        return (await self.session.execute(select(RechargeOrder).where(
            RechargeOrder.order_no == order_no,
        ))).scalar_one_or_none()

    @staticmethod
    def _apply_target(order: RechargeOrder, target: dict[str, str | None]) -> None:
        """将上游支付目标写入订单。"""
        kind = str(target.get("kind") or "")
        value = str(target.get("value") or "")
        order.pay_target_kind = kind
        order.qr_code = value if kind == "qrcode" else None
        order.pay_url = value if kind in {"payurl", "urlscheme"} else None

    @staticmethod
    def _payment_data(order: RechargeOrder) -> dict[str, Any]:
        """序列化前端付款所需字段。"""
        return {
            "order_id": order.id, "order_no": order.order_no, "amount": order.amount,
            "status": order.status,
            "channel": order.channel, "pay_type": order.pay_type,
            "pay_target_kind": order.pay_target_kind, "qr_code": order.qr_code, "pay_url": order.pay_url,
        }
