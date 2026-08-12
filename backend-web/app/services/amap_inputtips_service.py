"""
高德宝贝所在地输入提示服务。

功能：
1. 按闲鱼卖家工作台网页 SDK 参数调用高德 inputtips 接口。
2. 将高德 POI 提示转换为前端所在地选择所需的稳定结构。
3. 将网络或高德业务错误转换为明确的中文业务异常，不返回模拟数据。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from app.core.http_client import get_http_client


REQUEST_TIMEOUT_SECONDS = 20
AMAP_INPUTTIPS_URL = "https://restapi.amap.com/v3/assistant/inputtips"
AMAP_WEB_KEY = "c9b68d4ce9a2a97f22a4a439404488ca"
AMAP_APP_NAME = "https://seller.goofish.com"
AMAP_ORIGIN = "https://seller.goofish.com"


class AmapInputTipsError(RuntimeError):
    """高德输入提示接口请求失败或返回业务错误。"""


def _as_text(value: Any) -> str:
    """将高德响应字段安全转换为字符串，过滤空数组等非文本占位值。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _parse_tip(raw_tip: Any) -> dict[str, str] | None:
    """解析单条高德 POI 提示，无名称的无效记录不返回。"""
    if not isinstance(raw_tip, dict):
        return None

    name = _as_text(raw_tip.get("name"))
    if not name:
        return None
    district = _as_text(raw_tip.get("district"))
    address = _as_text(raw_tip.get("address"))
    detail_text = "".join(part for part in (district, address) if part)
    expected_parts = [part for part in (name, detail_text) if part]

    return {
        "id": _as_text(raw_tip.get("id")),
        "name": name,
        "district": district,
        "adcode": _as_text(raw_tip.get("adcode")),
        "location": _as_text(raw_tip.get("location")),
        "address": address,
        "typecode": _as_text(raw_tip.get("typecode")),
        "city": _as_text(raw_tip.get("city")),
        "search_keyword": name,
        "expected_text": " / ".join(expected_parts),
    }


class AmapInputTipsService:
    """调用高德 inputtips 接口搜索宝贝所在地。"""

    async def search(self, keywords: str, city: str = "全国") -> dict[str, Any]:
        """
        根据关键词查询高德 POI 输入提示。

        Args:
            keywords: 用户输入的所在地关键词。
            city: 搜索城市，默认全国且不限制城市范围。
        Returns:
            包含高德实际返回提示列表和数量的字典。
        Raises:
            AmapInputTipsError: 请求失败或高德返回失败时抛出。
        """
        normalized_keywords = keywords.strip()
        if not normalized_keywords:
            raise AmapInputTipsError("请输入所在地关键词")

        params = {
            "s": "rsv3",
            "key": AMAP_WEB_KEY,
            "platform": "JS",
            "logversion": "2.0",
            "sdkversion": "2.0",
            "appname": AMAP_APP_NAME,
            "keywords": normalized_keywords,
            "city": city.strip() or "全国",
            "citylimit": "false",
            "datatype": "all",
        }
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "origin": AMAP_ORIGIN,
            "referer": f"{AMAP_ORIGIN.rstrip('/')}/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        }

        try:
            body = await asyncio.wait_for(
                get_http_client().get(
                    AMAP_INPUTTIPS_URL,
                    params=params,
                    headers=headers,
                ),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(f"高德所在地搜索超时: keywords={normalized_keywords}")
            raise AmapInputTipsError("所在地搜索超时，请稍后重试") from exc
        except Exception as exc:
            logger.warning(f"高德所在地搜索请求失败: keywords={normalized_keywords}, error={exc}")
            raise AmapInputTipsError("所在地搜索接口请求失败，请稍后重试") from exc

        logger.info(
            f"高德inputtips接口完整返回: keywords={normalized_keywords}, "
            f"response={json.dumps(body, ensure_ascii=False, default=str)}"
        )
        if not isinstance(body, dict) or str(body.get("status")) != "1":
            info = _as_text(body.get("info")) if isinstance(body, dict) else ""
            infocode = _as_text(body.get("infocode")) if isinstance(body, dict) else ""
            logger.warning(
                f"高德所在地搜索业务失败: keywords={normalized_keywords}, "
                f"info={info}, infocode={infocode}"
            )
            raise AmapInputTipsError(f"所在地搜索失败：{info or '高德接口未返回成功状态'}")

        tips = [
            parsed_tip
            for raw_tip in (body.get("tips") or [])
            if (parsed_tip := _parse_tip(raw_tip)) is not None
        ]
        return {"tips": tips, "count": len(tips), "keywords": normalized_keywords}
