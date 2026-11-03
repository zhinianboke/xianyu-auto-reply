"""码支付（易支付）mapi 下单与异步通知 MD5 验签。"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.services.payment_config_service import VALID_ZZCODE_PAY_TYPES
from common.utils.payment_amount import normalize_zzcode_amount

logger = logging.getLogger(__name__)
TRADE_SUCCESS = "TRADE_SUCCESS"
_SIGN_EXCLUDED_KEYS = {"sign", "sign_type"}
_PAY_TARGET_KEYS = ("payurl", "qrcode", "urlscheme")


def _log_params(params: dict[str, Any]) -> dict[str, Any]:
    """复制请求参数供完整日志记录，避免后续修改影响日志内容。"""
    return dict(params)


class ZzcodeOrderResultUnknownError(ValueError):
    """码支付请求可能已被上游处理，但本系统未取得可确认的下单结果。"""


class ZzcodeService:
    """执行码支付下单和回调验签。"""

    def __init__(self, config: dict[str, str], *, require_order_config: bool = True) -> None:
        required = ("pid", "key", "gateway", "notify_url", "return_url") if require_order_config else ("pid", "key")
        missing = [key for key in required if not config.get(key)]
        if missing:
            raise ValueError(f"码支付配置缺少必要字段: {', '.join(missing)}")
        self.config = config

    async def create_order(self, order_no: str, amount: str, name: str, pay_type: str) -> dict[str, str | None]:
        """提交 mapi 下单并返回支付目标、上游交易号和已校验的最终金额。"""
        if pay_type not in VALID_ZZCODE_PAY_TYPES:
            raise ValueError("码支付支付方式无效")
        params = {
            "pid": str(self.config["pid"]), "type": pay_type, "out_trade_no": order_no,
            "notify_url": str(self.config["notify_url"]), "return_url": str(self.config["return_url"]),
            "name": name, "money": amount,
        }
        params["sign"] = self._sign(params)
        params["sign_type"] = "MD5"
        endpoint = self._endpoint()
        headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
        logged_params = _log_params(params)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(endpoint, data=params, headers=headers)
        except httpx.RequestError as exc:
            logger.exception("码支付网络请求失败: method=POST url=%s query={} headers=%s body=%s exception=%s", endpoint, headers, logged_params, exc)
            raise ZzcodeOrderResultUnknownError("码支付下单结果未知，请稍后查看支付结果或联系管理员") from exc
        except Exception as exc:
            logger.exception(
                "码支付请求发生未预期异常: method=POST url=%s query={} headers=%s body=%s exception=%s",
                endpoint, headers, logged_params, exc,
            )
            raise ZzcodeOrderResultUnknownError(
                "码支付下单结果未知，请稍后查看支付结果或联系管理员"
            ) from exc
        if response.status_code < 200 or response.status_code >= 300:
            logger.error("码支付请求失败: method=POST url=%s query={} headers=%s body=%s status=%s response_headers=%s response_body=%s", endpoint, headers, logged_params, response.status_code, dict(response.headers), response.text)
            raise ZzcodeOrderResultUnknownError("码支付下单结果未知，请稍后查看支付结果或联系管理员")
        try:
            payload = self._parse_response_json(response)
        except (TypeError, ValueError) as exc:
            logger.exception(
                "码支付响应处理失败: method=POST url=%s query={} headers=%s body=%s status=%s response_headers=%s response_body=%s exception=%s",
                endpoint, headers, logged_params, response.status_code,
                dict(response.headers), response.text, exc,
            )
            raise ZzcodeOrderResultUnknownError("码支付下单结果未知，请稍后查看支付结果或联系管理员") from exc
        if not isinstance(payload, dict):
            logger.error(
                "码支付响应格式异常: method=POST url=%s query={} headers=%s body=%s status=%s response_headers=%s response_body=%s",
                endpoint, headers, logged_params, response.status_code, dict(response.headers), response.text,
            )
            raise ZzcodeOrderResultUnknownError("码支付下单结果未知，请稍后查看支付结果或联系管理员")
        if str(payload.get("code")) != "1":
            message = str(payload.get("msg") or "生成支付订单失败")
            logger.error("码支付业务失败: method=POST url=%s query={} headers=%s body=%s status=%s response_headers=%s response_body=%s", endpoint, headers, logged_params, response.status_code, dict(response.headers), response.text)
            raise ValueError(f"码支付下单失败：{message}")
        money = payload.get("money")
        if money not in (None, ""):
            try:
                normalized_money = normalize_zzcode_amount(money)
            except (TypeError, ValueError) as exc:
                logger.exception(
                    "码支付下单成功但返回金额无效: method=POST url=%s query={} headers=%s body=%s status=%s response_headers=%s response_body=%s exception=%s",
                    endpoint, headers, logged_params, response.status_code,
                    dict(response.headers), response.text, exc,
                )
                raise ZzcodeOrderResultUnknownError(
                    "码支付下单结果未知，请稍后查看支付结果或联系管理员"
                ) from exc
        else:
            normalized_money = None
        for kind in _PAY_TARGET_KEYS:
            value = payload.get(kind)
            if value:
                return {
                    "kind": kind,
                    "value": str(value),
                    "trade_no": str(payload["trade_no"]) if payload.get("trade_no") else None,
                    "money": normalized_money,
                }
        logger.error("码支付下单成功但未返回支付链接或二维码: order_no=%s response_body=%s", order_no, response.text)
        raise ZzcodeOrderResultUnknownError(
            "码支付下单结果未知，请稍后查看支付结果或联系管理员"
        )

    def verify_notify(self, values: dict[str, str]) -> bool:
        """验证 GET 或 POST 异步通知签名。"""
        if str(values.get("pid") or "") != str(self.config["pid"]):
            logger.error("码支付通知商户ID不匹配: order_no=%s values=%s", values.get("out_trade_no"), values)
            return False
        received = str(values.get("sign") or "").lower()
        if not received:
            logger.error("码支付通知缺少签名: order_no=%s values=%s", values.get("out_trade_no"), values)
            return False
        if not hmac.compare_digest(self._sign(values), received):
            logger.error("码支付通知验签失败: order_no=%s values=%s", values.get("out_trade_no"), values)
            return False
        return True

    def _endpoint(self) -> str:
        gateway = str(self.config["gateway"]).strip()
        return f"{gateway[:-len('submit.php')]}mapi.php" if gateway.endswith("/submit.php") else gateway

    def _sign(self, params: dict[str, Any]) -> str:
        content = "&".join(f"{key}={params[key]}" for key in sorted(params) if key not in _SIGN_EXCLUDED_KEYS and params[key] not in ("", None))
        return hashlib.md5(f"{content}{self.config['key']}".encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_response_json(response: httpx.Response) -> Any:
        attempted: list[str] = []
        last_error: Exception | None = None
        for encoding in (response.charset_encoding, "utf-8-sig", "gb18030"):
            normalized = str(encoding or "").strip().lower()
            if not normalized or normalized in attempted:
                continue
            attempted.append(normalized)
            try:
                return json.loads(response.content.decode(normalized))
            except (LookupError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
        raise ValueError(f"码支付响应不是有效 JSON，已尝试编码={','.join(attempted)}") from last_error
