"""
商品通用查询 - 执行引擎（backend-web 公开层）

功能：
1. 从商品配置（xy_catalog_items.metadata_json.query_buttons）读取查询按钮
2. 公开接口支撑：按订单号返回按钮名列表（绝不回传 URL/headers 等配置细节）
3. 执行查询：httpx 代理调用外部 API，变量替换 URL/请求头/Body，
   多行卡密（一单多件）逐行并发执行，逐行返回 ExecResult

安全：
- 日志禁止打印 Cookie、请求体、卡密内容；仅记录订单号、按钮名、HTTP 状态
- 买家端只见按钮名与执行结果，配置中的 URL/headers 不下发
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.services.query_template import (
    extract_card_variables,
    mask_account,
    render_template,
    resolve_path,
    template_url_has_variable_host,
)

# 外部查询接口超时时间（秒），与原余额查询保持一致
UPSTREAM_TIMEOUT = 15.0
# 单次执行最多处理的卡密行数上限：防止异常内容导致一次请求向上游打出过多并发
MAX_CARD_LINES_PER_EXECUTE = 20


class ItemQueryService:
    """商品通用查询服务：读取按钮配置并代理执行外部查询"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== 配置读取 ====================

    async def get_buttons_for_item(self, owner_id: int, item_id: str) -> list[dict]:
        """读取商品配置的查询按钮列表（完整配置，仅服务端/管理端使用）。

        Args:
            owner_id: 所属用户ID
            item_id: 商品ID
        Returns:
            ``metadata_json.query_buttons`` 列表；无配置或结构异常时返回空列表。
        """
        if not item_id:
            return []
        result = await self.session.execute(
            select(XYCatalogItem).where(
                XYCatalogItem.owner_id == owner_id,
                XYCatalogItem.item_id == item_id,
            )
        )
        item = result.scalars().first()
        if not item:
            return []
        buttons = (item.metadata_json or {}).get("query_buttons")
        if not isinstance(buttons, list):
            return []
        return [button for button in buttons if isinstance(button, dict)]

    @staticmethod
    def _button_uses_cookie(button: dict) -> bool:
        """判定按钮配置是否引用 ``{cookie}`` 变量（url/headers/body 任一包含即可）。"""
        haystack = (
            (button.get("url") or "")
            + json.dumps(button.get("headers") or {}, ensure_ascii=False)
            + (button.get("body") or "")
        )
        return "{cookie}" in haystack

    # ==================== 公开接口：按钮列表 ====================

    async def get_buttons_public(self, order_no: str) -> tuple[bool, str, dict]:
        """按订单号返回买家可见的按钮列表（只含按钮名）与 uses_cookie 标记。

        Returns:
            (success, message, data)；data 为 ``{"buttons": [{"name": ...}], "uses_cookie": bool}``，
            失败时 data 为 ``{"buttons": [], "uses_cookie": False}``。
        """
        empty = {"buttons": [], "uses_cookie": False}
        order_no = (order_no or "").strip()
        if not order_no:
            return False, "请输入订单号", empty

        result = await self.session.execute(
            select(XYOrder).where(XYOrder.order_no == order_no)
        )
        order = result.scalars().first()
        if not order:
            return False, "订单不存在，请核对订单号", empty

        buttons = await self.get_buttons_for_item(order.owner_id, order.item_id or "")
        if not buttons:
            return False, "该商品未配置查询功能，请联系卖家", empty

        return True, "查询成功", {
            # 每个按钮带 uses_cookie 标记：前端手动 Cookie 查询需要定位到含 {cookie} 变量的按钮
            "buttons": [
                {"name": button.get("name") or "查询", "uses_cookie": self._button_uses_cookie(button)}
                for button in buttons
            ],
            "uses_cookie": any(self._button_uses_cookie(button) for button in buttons),
        }

    # ==================== 公开接口：执行查询 ====================

    async def execute(
        self,
        order_no: Optional[str],
        button_index: int,
        cookie_override: Optional[str],
    ) -> tuple[bool, str, dict]:
        """执行查询按钮：按订单卡密逐行并发执行，或用手动 Cookie 单次执行。

        Args:
            order_no: 订单号（用于定位商品配置与发货内容；cookie_override 模式下仍需提供以定位配置）
            button_index: 按钮在 query_buttons 中的下标
            cookie_override: 买家手动粘贴的 Cookie；非空时跳过发货内容校验，仅替换 ``{cookie}`` 执行一次
        Returns:
            (success, message, data)；data 为 ``{"results": [ExecResult, ...]}``。
        """
        override = (cookie_override or "").strip()
        order_no = (order_no or "").strip()
        if not order_no:
            return False, "缺少订单号，无法定位查询配置", {"results": []}

        result = await self.session.execute(
            select(XYOrder).where(XYOrder.order_no == order_no)
        )
        order = result.scalars().first()
        if not order:
            return False, "订单不存在，请核对订单号", {"results": []}

        buttons = await self.get_buttons_for_item(order.owner_id, order.item_id or "")
        if not buttons:
            return False, "该商品未配置查询功能，请联系卖家", {"results": []}
        if button_index < 0 or button_index >= len(buttons):
            return False, "查询按钮不存在，请刷新页面重试", {"results": []}
        button = buttons[button_index]

        # 手动 Cookie 模式：跳过发货内容校验，仅替换 {cookie} 执行一次（账号为空）
        # 多行并发共享一个 httpx client（连接池复用）；
        # return_exceptions=True：单条异常不拖垮整批，统一在下方转成失败结果
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
            if override:
                variables = {"cookie": override, "account": "", "api_key": "", "line": ""}
                raw_results: list = [await self._execute_one(button, variables, client)]
            else:
                if not order.delivery_content:
                    return False, "该订单暂无发货内容，无法查询", {"results": []}
                lines = self._extract_card_lines(order.delivery_content)
                if not lines:
                    return False, "发货内容中未找到可用的卡密信息，请改用手动 Cookie 查询", {"results": []}
                # 多份卡密并发查询，互不阻塞；单份失败不影响其他结果；行数设上限防异常放大
                raw_results = await asyncio.gather(
                    *(self._execute_one(button, variables, client) for variables in lines[:MAX_CARD_LINES_PER_EXECUTE]),
                    return_exceptions=True,
                )

        results = [
            item if isinstance(item, dict) else {"account": None, "success": False, "error": "查询异常，请稍后重试", "fields": [], "as_of": ""}
            for item in raw_results
        ]

        success_count = sum(1 for item in results if item.get("success"))
        if success_count == 0:
            # 全部失败：透传首条错误，data 仍带 results 供前端逐条展示
            message = results[0].get("error") or "查询失败，请稍后重试"
            return False, message, {"results": results}
        if success_count == len(results):
            return True, "查询成功", {"results": results}
        return True, f"部分查询失败（{success_count}/{len(results)} 成功）", {"results": results}

    @staticmethod
    def _extract_card_lines(delivery_content: str) -> list[dict[str, str]]:
        """从发货内容逐行提取卡密变量，只保留至少一个变量（账号/API Key/Cookie）非空的行。"""
        lines: list[dict[str, str]] = []
        for line in (delivery_content or "").splitlines():
            variables = extract_card_variables(line)
            if variables["account"] or variables["api_key"] or variables["cookie"]:
                lines.append(variables)
        return lines

    # ==================== 单次执行 ====================

    async def _execute_one(self, button: dict, variables: dict[str, str], client: httpx.AsyncClient) -> dict:
        """按按钮配置对单份卡密执行一次外部查询，返回一条 ExecResult。

        任何异常都在内部消化为 ``success=False + error``，不向调用方抛出。
        """
        # base 带齐契约字段（fields/as_of），失败分支也保证结构完整，前端可直接 map 渲染
        base = {"account": mask_account(variables.get("account") or None), "success": False, "fields": [], "as_of": ""}
        button_name = button.get("name") or "查询"

        method = str(button.get("method") or "GET").upper()
        url = render_template(button.get("url"), variables)
        if not url:
            return {**base, "error": "查询配置缺少请求地址"}
        # SSRF 防护：URL 的 host 段禁止含变量占位符，防止 cookie_override 注入任意地址
        if template_url_has_variable_host(button.get("url")):
            return {**base, "error": "查询配置有误，请联系卖家"}
        headers_raw = button.get("headers") or {}
        if not isinstance(headers_raw, dict):
            return {**base, "error": "查询配置有误，请联系卖家"}
        headers = {
            str(key): render_template(str(value), variables) or ""
            for key, value in headers_raw.items()
        }
        body_raw = button.get("body")
        body = render_template(str(body_raw), variables) if method == "POST" and body_raw is not None else None

        try:
            if method == "POST":
                resp = await client.post(url, headers=headers, content=body)
            else:
                resp = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            logger.warning(f"[通用查询] 外部接口超时 button={button_name}")
            return {**base, "error": "查询超时，请稍后重试"}
        except Exception as e:
            # 异常信息不含 Cookie/卡密，但为稳妥只记录异常类型
            logger.warning(f"[通用查询] 外部接口请求异常 button={button_name}: {type(e).__name__}")
            return {**base, "error": "网络异常，请稍后重试"}

        success_path = str(button.get("success_path") or "").strip()
        success_value = button.get("success_value")
        error_path = str(button.get("error_path") or "").strip()

        # 响应体统一尝试按 JSON 解析；解析失败时：
        # - 无成功判定条件且 HTTP 2xx 仍可视为成功（字段全部取空）
        # - 有成功判定条件则判失败
        payload: Any = None
        try:
            payload = resp.json()
        except Exception:
            payload = None

        def _error_message(fallback: str) -> str:
            if error_path and payload is not None:
                message = resolve_path(payload, error_path)
                if message:
                    return str(message)
            return fallback

        if not (200 <= resp.status_code < 300):
            logger.warning(f"[通用查询] 外部接口非2xx button={button_name} status={resp.status_code}")
            return {**base, "error": _error_message(f"查询失败（接口返回 {resp.status_code}），请稍后重试")}

        if success_path and success_value is not None:
            if payload is None:
                return {**base, "error": "接口返回格式异常"}
            actual = resolve_path(payload, success_path)
            if actual is None or str(actual) != str(success_value):
                return {**base, "error": _error_message("查询失败，请稍后重试")}

        # 成功：按 result_fields 解析展示字段，取不到值的字段给空串
        fields = []
        if payload is not None:
            for field in button.get("result_fields") or []:
                if not isinstance(field, dict):
                    continue
                value = resolve_path(payload, str(field.get("path") or ""))
                fields.append({
                    "label": str(field.get("label") or ""),
                    "value": "" if value is None else str(value),
                    "highlight": bool(field.get("highlight")),
                    "prefix": str(field.get("prefix") or ""),
                })

        # as_of 无配置项：沿用原余额查询约定，尽力从 data.asOf 读取，取不到为空串
        as_of = ""
        if payload is not None:
            as_of_value = resolve_path(payload, "data.asOf")
            if as_of_value:
                as_of = str(as_of_value)

        return {**base, "success": True, "error": None, "fields": fields, "as_of": as_of}
