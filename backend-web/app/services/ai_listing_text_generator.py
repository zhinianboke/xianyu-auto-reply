"""
AI 铺货文案生成

功能：
1. 组装文案生成提示词（支持配置里的自定义模板，占位符非法时回退内置模板）
2. 调用 OpenAI 兼容接口批量生成商品标题与描述
3. 解析并清洗返回的 JSON，字段长度与素材库接口保持一致

说明：拆分自 ai_listing_runner，便于单文件控制在 500 行以内。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
from loguru import logger

from common.models.ai_listing_config import AiListingConfig
from common.services.ai_text_client import AiCallError, DEFAULT_TEXT_TIMEOUT, chat_completion

# 单批文案生成的最大条数：一次请求生成太多容易被截断
TEXT_BATCH_SIZE = 10

# 素材字段长度上限，与素材库创建接口保持一致，避免入库后前端编辑必然校验失败
TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 1500

# 内置文案提示词模板（配置里填了 prompt_template 时优先用用户的）
DEFAULT_PROMPT_TEMPLATE = """请为闲鱼平台生成 {count} 条二手商品素材，主题：{keyword}。
{hints}要求：
1. title 不超过 30 个字，突出卖点；
2. description 不超过 300 个字，说明成色、规格、发货等买家关心的信息；
3. price 为人民币数字（元）；
4. 每条内容互不重复。
只返回如下 JSON，不要任何解释或代码块标记：
{{"items":[{{"title":"...","description":"...","price":0}}]}}"""

SYSTEM_PROMPT = "你是熟悉闲鱼二手交易的商品文案专家，只输出符合要求的 JSON，不输出任何解释。"


def _build_hints(params: Dict[str, Any]) -> str:
    """把分类/成色/价格等约束拼成提示词里的补充说明"""
    defaults = params.get("material_defaults") or {}
    hints: List[str] = []
    if defaults.get("category"):
        hints.append(f"商品分类：{defaults['category']}。")
    if defaults.get("condition"):
        hints.append(f"成色：{defaults['condition']}。")
    if params.get("price_mode") == "fixed" and params.get("price") is not None:
        hints.append(f"价格固定为 {params['price']} 元。")
    elif params.get("price_min") is not None and params.get("price_max") is not None:
        hints.append(f"价格控制在 {params['price_min']}~{params['price_max']} 元之间。")
    return "".join(hints) + ("\n" if hints else "")


def _strip_code_fence(text: str) -> str:
    """去掉模型可能加上的 ```json 代码块标记"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


def parse_generated_items(text: str, expect: int) -> List[Dict[str, Any]]:
    """解析模型返回的 JSON 文案

    Args:
        text: 模型输出。
        expect: 本批期望条数。
    Returns:
        清洗后的条目列表（title/description/price），最多 expect 条。
    Raises:
        AiCallError: 返回内容不是合法 JSON 或没有可用条目。
    """
    try:
        payload = json.loads(_strip_code_fence(text))
    except (ValueError, TypeError) as exc:
        raise AiCallError(f"AI返回内容不是合法JSON：{text[:200]}") from exc

    raw_items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list) or not raw_items:
        raise AiCallError(f"AI返回内容缺少items字段：{text[:200]}")

    items: List[Dict[str, Any]] = []
    for raw in raw_items[:expect]:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()[:TITLE_MAX_LENGTH]
        description = str(raw.get("description") or "").strip()[:DESCRIPTION_MAX_LENGTH]
        if not title or not description:
            continue
        items.append({"title": title, "description": description, "price": raw.get("price")})

    if not items:
        raise AiCallError("AI返回的条目缺少标题或描述")
    return items


async def generate_text_batch(
    client: httpx.AsyncClient,
    config: AiListingConfig,
    params: Dict[str, Any],
    keyword: str,
    batch_size: int,
) -> List[Dict[str, Any]]:
    """生成一批文案

    Args:
        client: 复用的 httpx 客户端。
        config: AI 铺货配置。
        params: 任务参数快照。
        keyword: 生成主题。
        batch_size: 本批条数。
    Returns:
        条目列表。
    Raises:
        AiCallError: 接口调用或解析失败。
    """
    template = (config.prompt_template or "").strip() or DEFAULT_PROMPT_TEMPLATE
    try:
        user_prompt = template.format(count=batch_size, keyword=keyword, hints=_build_hints(params))
    except (KeyError, IndexError, ValueError):
        # 用户自定义模板里有非法占位符时，退回内置模板，避免整个任务卡死
        logger.warning("【AI铺货】自定义提示词模板占位符非法，已回退内置模板")
        user_prompt = DEFAULT_PROMPT_TEMPLATE.format(
            count=batch_size, keyword=keyword, hints=_build_hints(params)
        )

    content = await chat_completion(
        base_url=config.text_base_url,
        api_key=config.text_api_key,
        model=config.text_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=float(config.text_temperature or 0.7),
        max_tokens=int(config.text_max_tokens or 2048),
        timeout=DEFAULT_TEXT_TIMEOUT,
        client=client,
    )
    return parse_generated_items(content, batch_size)



__all__ = ["TEXT_BATCH_SIZE", "generate_text_batch", "parse_generated_items"]
