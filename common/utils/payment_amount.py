"""支付渠道金额格式校验公共工具。

功能：
1. 校验码支付返回及回调的实际支付金额
2. 统一格式化为两位小数字符串，避免充值和广告付款重复实现
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

ZZCODE_AMOUNT_STEP = Decimal("0.01")


def normalize_zzcode_amount(value: Any) -> str:
    """校验码支付金额并格式化为两位小数，禁止静默舍入实际支付金额。

    Args:
        value: 码支付下单响应或已验签回调中的 money 字段。
    Returns:
        固定保留两位小数的金额字符串。
    Raises:
        ValueError: 金额为空、非正数、非有限数值或包含两位以上有效小数。
    """
    raw = str(value).strip()
    if not raw:
        raise ValueError("码支付金额不能为空")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("码支付金额格式不正确") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("码支付金额必须是大于0的有限数值")
    try:
        normalized = amount.quantize(ZZCODE_AMOUNT_STEP)
    except InvalidOperation as exc:
        raise ValueError("码支付金额超出支持范围") from exc
    if amount != normalized:
        raise ValueError("码支付金额最多保留两位小数")
    return f"{normalized:.2f}"


def zzcode_amount_is_confirmed(order: Any) -> bool:
    """判断订单金额是否已由码支付下单响应或回调明确确认。"""
    return bool(getattr(order, "zzcode_amount_confirmed", False))
