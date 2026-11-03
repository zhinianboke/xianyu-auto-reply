"""支付渠道配置、数据字典选项与码支付子方式校验。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.data_dictionary import XYDataDictionary
from common.models.system_setting import SystemSetting

CHANNEL_ALIPAY = "alipay"
CHANNEL_ZZCODE = "zzcode"
VALID_CHANNELS = {CHANNEL_ALIPAY, CHANNEL_ZZCODE}
PAYMENT_CHANNEL_DICT = "payment_channel"
ZZCODE_PAY_TYPE_DICT = "zzcode_pay_type"
ZZCODE_PAY_TYPES = ("alipay", "wxpay", "qqpay")
VALID_ZZCODE_PAY_TYPES = set(ZZCODE_PAY_TYPES)

PAYMENT_SETTING_DEFAULTS: dict[str, tuple[str, str]] = {
    "payment.channel": (CHANNEL_ALIPAY, "当前启用的支付渠道"),
    "alipay.app_id": ("", "支付宝应用ID"),
    "alipay.private_key": ("", "支付宝应用私钥"),
    "alipay.alipay_public_key": ("", "支付宝公钥"),
    "alipay.gateway_url": ("https://openapi.alipay.com/gateway.do", "支付宝网关地址"),
    "alipay.notify_url": ("", "支付宝异步通知地址"),
    "zzcode.pid": ("", "码支付商户ID"),
    "zzcode.key": ("", "码支付商户密钥"),
    "zzcode.gateway": ("", "码支付请求网关地址"),
    "zzcode.notify_url": ("", "码支付异步通知地址"),
    "zzcode.return_url": ("", "码支付页面跳转地址"),
    "zzcode.pay_types": (CHANNEL_ALIPAY, "码支付开启的支付方式"),
}


def normalize_pay_types(raw_value: object) -> list[str]:
    """将逗号分隔或列表形式的码支付方式规整为标准顺序的合法值。"""
    values = raw_value if isinstance(raw_value, (list, tuple, set)) else str(raw_value or "").split(",")
    selected = {str(value).strip().lower() for value in values}
    return [value for value in ZZCODE_PAY_TYPES if value in selected]


class PaymentConfigService:
    """读取支付渠道配置，不创建额外数据库连接。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_settings(self) -> dict[str, str]:
        """读取支付设置，缺失项使用启动自检定义的默认值。"""
        rows = (await self.session.execute(
            select(SystemSetting).where(SystemSetting.key.in_(tuple(PAYMENT_SETTING_DEFAULTS)))
        )).scalars().all()
        settings = {key: default for key, (default, _) in PAYMENT_SETTING_DEFAULTS.items()}
        settings.update({row.key: row.value for row in rows})
        return settings

    async def get_channel(self) -> str:
        """返回当前支付渠道，非法历史值回落为支付宝当面付。"""
        channel = str((await self._load_settings()).get("payment.channel") or "").strip().lower()
        return channel if channel in VALID_CHANNELS else CHANNEL_ALIPAY

    async def get_alipay_config(self) -> dict[str, str]:
        """返回支付宝服务所需配置。"""
        settings = await self._load_settings()
        return {
            "app_id": settings["alipay.app_id"],
            "private_key": settings["alipay.private_key"],
            "alipay_public_key": settings["alipay.alipay_public_key"],
            "gateway_url": settings["alipay.gateway_url"],
            "notify_url": settings["alipay.notify_url"],
        }

    async def get_zzcode_config(self) -> dict[str, str]:
        """返回码支付协议服务所需配置。"""
        settings = await self._load_settings()
        return {key: settings[f"zzcode.{key}"] for key in ("pid", "key", "gateway", "notify_url", "return_url")}

    async def resolve_pay_type(self, requested: str | None) -> str:
        """确定码支付子方式；开启多种时要求用户明确选择。"""
        settings = await self._load_settings()
        enabled = normalize_pay_types(settings.get("zzcode.pay_types"))
        if not enabled:
            raise ValueError("请先在系统设置中开启至少一种码支付支付方式")
        value = str(requested or "").strip().lower()
        if not value:
            if len(enabled) == 1:
                return enabled[0]
            raise ValueError("请选择支付方式")
        if value not in enabled:
            raise ValueError("所选支付方式未开启，请重新选择")
        return value

    async def get_options(self) -> dict:
        """返回前端付款所需的当前渠道及中文选项。"""
        settings = await self._load_settings()
        channel = str(settings.get("payment.channel") or "").strip().lower()
        if channel not in VALID_CHANNELS:
            channel = CHANNEL_ALIPAY
        rows = (await self.session.execute(
            select(XYDataDictionary).where(
                XYDataDictionary.dict_type.in_((PAYMENT_CHANNEL_DICT, ZZCODE_PAY_TYPE_DICT)),
                XYDataDictionary.enabled.is_(True),
            ).order_by(XYDataDictionary.sort_order, XYDataDictionary.id)
        )).scalars().all()
        labels = {(row.dict_type, row.dict_value): row.dict_label for row in rows}
        channel_label = labels.get((PAYMENT_CHANNEL_DICT, channel))
        if not channel_label:
            raise ValueError("支付渠道数据字典未初始化，请联系管理员")
        enabled = normalize_pay_types(settings.get("zzcode.pay_types")) if channel == CHANNEL_ZZCODE else []
        if channel == CHANNEL_ZZCODE and not enabled:
            raise ValueError("请先在系统设置中开启至少一种码支付支付方式")
        pay_types = []
        for value in enabled:
            label = labels.get((ZZCODE_PAY_TYPE_DICT, value))
            if not label:
                raise ValueError("码支付方式数据字典未初始化，请联系管理员")
            pay_types.append({"value": value, "label": label})
        return {"channel": channel, "channel_label": channel_label, "pay_types": pay_types}

    async def get_config_options(self) -> dict:
        """返回系统设置页使用的全部支付渠道和码支付子方式字典项。"""
        rows = (await self.session.execute(
            select(XYDataDictionary).where(
                XYDataDictionary.dict_type.in_((PAYMENT_CHANNEL_DICT, ZZCODE_PAY_TYPE_DICT)),
                XYDataDictionary.enabled.is_(True),
            ).order_by(XYDataDictionary.sort_order, XYDataDictionary.id)
        )).scalars().all()
        grouped = {PAYMENT_CHANNEL_DICT: [], ZZCODE_PAY_TYPE_DICT: []}
        for row in rows:
            grouped[row.dict_type].append({"value": row.dict_value, "label": row.dict_label})
        if len(grouped[PAYMENT_CHANNEL_DICT]) < 2 or not grouped[ZZCODE_PAY_TYPE_DICT]:
            raise ValueError("支付相关数据字典未初始化完整，请联系管理员")
        return {"channels": grouped[PAYMENT_CHANNEL_DICT], "pay_types": grouped[ZZCODE_PAY_TYPE_DICT]}
