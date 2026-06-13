"""
分销卡券对接服务

功能：
1. 从系统设置读取「对接卡密秘钥」（distribution.card_secret_key）作为上游 API 密钥
2. 通过 HTTP 调用上游卡券系统（codefree）的代理端接口，完成卡券商查询、商品查询、库存查询与提货
3. 统一返回 {success, code, message, data} 结构，业务错误以 HTTP 200 携带标志字段返回

说明：
- 上游接口前缀为 {base}/api/card-product/agent
- 所有数据均通过上游接口实时获取，本服务不缓存、不落库
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import HTTPClient
from common.models.user_setting import UserSetting

# 对接卡密秘钥在用户设置中的键名（迁移到个人设置后按用户存储）
CARD_SECRET_KEY_SETTING = "distribution.card_secret_key"

# 上游代理端接口路径前缀
_AGENT_PREFIX = "/api/card-product/agent"

# 专用 HTTP 客户端（模块级单例）
# 关键：max_retries=1 表示不重试。提货为非幂等的扣款操作，
# 若超时后自动重试可能导致重复提货/重复扣款，因此禁用重试。
_card_dock_http_client: HTTPClient | None = None


def _get_card_dock_http_client() -> HTTPClient:
    """获取卡券对接专用 HTTP 客户端（不重试，超时 60 秒）"""
    global _card_dock_http_client
    if _card_dock_http_client is None:
        _card_dock_http_client = HTTPClient(timeout=60, max_retries=1)
    return _card_dock_http_client


class CardDockService:
    """分销卡券对接服务：封装对上游卡券系统的调用"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.http = _get_card_dock_http_client()

    @property
    def base_url(self) -> str:
        """上游服务基址（去除末尾斜杠）"""
        return (self.settings.card_dock_base_url or "").rstrip("/")

    def _build_url(self, path: str) -> str:
        """拼接上游完整 URL"""
        return f"{self.base_url}{_AGENT_PREFIX}{path}"

    async def _get_secret_key(self, user_id: int) -> str:
        """从当前用户的个人设置读取对接卡密秘钥"""
        stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == CARD_SECRET_KEY_SETTING,
        )
        result = await self.session.execute(stmt)
        record = result.scalars().first()
        return (record.value or "").strip() if record and record.value else ""

    @staticmethod
    def _fail(message: str, code: int = 400) -> Dict[str, Any]:
        """构造统一失败响应"""
        return {"success": False, "code": code, "message": message, "data": None}

    async def _request_with_key(
        self,
        user_id: int,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """统一注入秘钥并调用上游接口，异常时返回统一失败结构"""
        secret_key = await self._get_secret_key(user_id)
        if not secret_key:
            return self._fail("尚未配置对接卡密秘钥，请前往个人设置-分销管理填写", code=400)

        try:
            if method == "GET":
                merged_params = {"api_key": secret_key, **(params or {})}
                return await self.http.get(self._build_url(path), params=merged_params)
            # POST：秘钥放入请求体
            merged_body = {"api_key": secret_key, **(json_body or {})}
            return await self.http.post(self._build_url(path), json=merged_body)
        except Exception as exc:  # noqa: BLE001 上游/网络异常统一兜底为业务失败
            logger.error(f"调用上游卡券接口失败 {method} {path}: {exc}")
            return self._fail("调用上游卡券服务失败，请稍后重试", code=502)

    async def get_sources(self, user_id: int) -> Dict[str, Any]:
        """获取卡券商下拉列表"""
        return await self._request_with_key(user_id, "GET", "/sources")

    async def get_goods(
        self,
        user_id: int,
        source_code: str,
        page: int = 1,
        per_page: int = 15,
        search: str = "",
    ) -> Dict[str, Any]:
        """获取卡券货源商品列表（分页、搜索）"""
        params: Dict[str, Any] = {
            "source_code": source_code,
            "page": page,
            "per_page": per_page,
        }
        if search:
            params["search"] = search
        return await self._request_with_key(user_id, "GET", "/goods", params=params)

    async def get_goods_detail(self, user_id: int, source_code: str, goods_id: int) -> Dict[str, Any]:
        """获取商品详情（含使用说明）"""
        return await self._request_with_key(
            user_id, "GET", f"/goods/{goods_id}", params={"source_code": source_code}
        )

    async def get_goods_stock(self, user_id: int, source_code: str, goods_id: int) -> Dict[str, Any]:
        """获取商品各规格库存"""
        return await self._request_with_key(
            user_id, "GET", f"/goods/{goods_id}/stock", params={"source_code": source_code}
        )

    async def purchase(
        self,
        user_id: int,
        source_code: str,
        goods_id: int,
        sub_id: int,
        quantity: int,
    ) -> Dict[str, Any]:
        """提货（扣减上游 API 密钥余额并返回卡密）"""
        return await self._request_with_key(
            user_id,
            "POST",
            "/purchase",
            json_body={
                "source_code": source_code,
                "goods_id": goods_id,
                "sub_id": sub_id,
                "quantity": quantity,
            },
        )

    async def get_purchase_url(
        self,
        user_id: int,
        source_code: str,
        goods_id: int,
        sub_id: int,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """生成可直接 GET 调用的提货地址（含 api_key），用于「复制提货api」"""
        secret_key = await self._get_secret_key(user_id)
        if not secret_key:
            return self._fail("尚未配置对接卡密秘钥，请前往个人设置-分销管理填写", code=400)

        query = urlencode(
            {
                "api_key": secret_key,
                "source_code": source_code,
                "goods_id": goods_id,
                "sub_id": sub_id,
                "quantity": quantity,
            },
            quote_via=quote,
        )
        url = f"{self._build_url('/purchase')}?{query}"
        return {"success": True, "code": 200, "message": "ok", "data": {"url": url}}
