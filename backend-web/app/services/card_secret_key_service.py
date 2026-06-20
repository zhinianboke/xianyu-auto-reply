"""
对接卡密秘钥创建服务

功能：
1. 从配置读取外部密钥管理服务基址（复用 CARD_DOCK_BASE_URL）与鉴权 key（EXTERNAL_API_KEY，禁止写死）
2. 以「xy_ + 15 位随机字母数字」作为 key_name，调用外部接口创建 API 密钥
3. 统一返回 {success, message, data} 结构，业务错误以 HTTP 200 携带标志字段返回

外部接口：
- POST {base}/api/api-management/keys/external-create-key
- 请求体：{"key": <鉴权key>, "key_name": "xy_随机15位", "description": "密钥描述"}
- 返回体：{"success": true, "message": "...", "data": {"key_value": "ak_xxx", ...}}
"""
from __future__ import annotations

import secrets
import string
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import get_settings
from app.core.http_client import HTTPClient

# 创建密钥的外部接口路径
_EXTERNAL_CREATE_KEY_PATH = "/api/api-management/keys/external-create-key"

# 用户名前缀：key_name = 前缀 + 15 位随机字母数字
_KEY_NAME_PREFIX = "xy_"
# 随机部分长度与字符集（数字 + 大写字母 + 小写字母）
_RANDOM_NAME_LENGTH = 15
_RANDOM_NAME_ALPHABET = string.ascii_letters + string.digits


def _gen_random_key_name() -> str:
    """生成 key_name：xy_ + 15 位随机字符（数字/大写/小写字母）"""
    random_part = "".join(secrets.choice(_RANDOM_NAME_ALPHABET) for _ in range(_RANDOM_NAME_LENGTH))
    return f"{_KEY_NAME_PREFIX}{random_part}"

# 专用 HTTP 客户端（模块级单例）：创建密钥为非幂等操作，禁用重试避免重复创建
_external_api_http_client: Optional[HTTPClient] = None


def _get_http_client() -> HTTPClient:
    """获取外部 API 专用 HTTP 客户端（不重试，超时 60 秒）"""
    global _external_api_http_client
    if _external_api_http_client is None:
        _external_api_http_client = HTTPClient(timeout=60, max_retries=1)
    return _external_api_http_client


class CardSecretKeyService:
    """对接卡密秘钥创建服务：封装对外部密钥管理服务的调用"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.http = _get_http_client()

    @property
    def base_url(self) -> str:
        """外部服务基址（复用卡券对接基址 CARD_DOCK_BASE_URL，去除末尾斜杠）"""
        return (self.settings.card_dock_base_url or "").rstrip("/")

    @property
    def api_key(self) -> str:
        """创建密钥的鉴权 key"""
        return (self.settings.external_api_key or "").strip()

    @staticmethod
    def _fail(message: str) -> Dict[str, Any]:
        """构造统一失败响应"""
        return {"success": False, "message": message, "data": None}

    async def create_key(self, username: str) -> Dict[str, Any]:
        """为指定用户创建对接卡密秘钥。

        Args:
            username: 当前用户名，用于拼接 key_name（xy_用户名）

        Returns:
            统一结构 {success, message, data}，成功时 data 含外部返回的密钥信息
        """
        if not self.base_url or not self.api_key:
            return self._fail("外部密钥服务未配置，请联系管理员设置 CARD_DOCK_BASE_URL 与 EXTERNAL_API_KEY")

        key_name = _gen_random_key_name()
        payload = {
            "key": self.api_key,
            "key_name": key_name,
            "description": f"闲鱼自动回复系统用户 {username} 的对接卡密秘钥",
        }
        url = f"{self.base_url}{_EXTERNAL_CREATE_KEY_PATH}"

        try:
            result = await self.http.post(url, json=payload)
        except Exception as exc:  # noqa: BLE001 网络/上游异常统一兜底为业务失败
            logger.error(f"调用外部创建密钥接口失败 {url}: {exc}")
            return self._fail("调用外部密钥服务失败，请稍后重试")

        if not isinstance(result, dict) or not result.get("success"):
            message = (result or {}).get("message") if isinstance(result, dict) else None
            return self._fail(message or "创建密钥失败")

        data = result.get("data") or {}
        key_value = (data.get("key_value") or "").strip()
        if not key_value:
            logger.error(f"外部创建密钥成功但未返回 key_value: {result}")
            return self._fail("创建密钥成功但未返回密钥值")

        return {
            "success": True,
            "message": result.get("message") or "创建密钥成功",
            "data": data,
        }
