"""
卡券发货内容获取服务（公共版）

功能：
1. 按卡券类型（text/data/api/image）统一生成发货内容
2. API 类型卡券的 HTTP 拉取（含动态参数替换与重试）
3. 提供给提货接口（backend-web）按对接卡券取内容使用

说明：
    自动发货（websocket 服务）有自己的一套带 IM 上下文的取卡流程，
    本模块面向"无闲鱼订单"的提货场景，只负责把一张卡券转换成纯文本发货内容，
    不涉及 IM 发送、确认发货、免拼等闲鱼订单相关逻辑。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.services.delivery_utils import (
    process_delivery_content_with_description,
    recursive_replace_params,
    replace_order_context_variables,
)

# API 取卡最大重试次数
_API_MAX_RETRIES = 4
# API 取卡请求超时（秒）
_API_DEFAULT_TIMEOUT = 10


async def consume_batch_data(session: AsyncSession, card_id: int) -> Optional[str]:
    """消费批量数据卡券的一条数据（行锁，防止并发重复派发）

    从卡券 data_content 中取出第一行并删除，使用 SELECT ... FOR UPDATE 行锁，
    保证同一张卡券在并发消费时被串行化。调用方需保证在同一事务内执行，
    行锁在事务提交或回滚时释放。

    Args:
        session: 数据库会话（调用方负责事务边界）
        card_id: 卡券ID

    Returns:
        消费的数据内容；无数据时返回 None
    """
    stmt = select(Card).where(Card.id == card_id).with_for_update()
    result = await session.execute(stmt)
    card = result.scalars().first()

    if not card or not card.data_content:
        logger.warning(f"卡券 {card_id} 不存在或没有批量数据")
        return None

    lines = [line.strip() for line in card.data_content.split('\n') if line.strip()]
    if not lines:
        logger.warning(f"卡券 {card_id} 批量数据已用完")
        return None

    consumed_data = lines[0]
    remaining_lines = lines[1:]
    card.data_content = '\n'.join(remaining_lines) if remaining_lines else ''
    await session.flush()

    logger.info(f"卡券 {card_id} 消费数据成功，剩余 {len(remaining_lines)} 条")
    return consumed_data


async def get_api_card_content(
    api_config: Any,
    context: Optional[Dict[str, str]] = None,
    retry_count: int = 0,
) -> Optional[str]:
    """调用 API 获取卡券内容（纯函数版，无 cookie 依赖）

    Args:
        api_config: 卡券 api_config（JSON 字符串或 dict）
        context: 动态参数上下文（用于 POST 参数占位符替换），如 order_id/item_id/buyer_id 等
        retry_count: 当前重试次数（内部递归用）

    Returns:
        API 返回的卡券内容；失败返回 None
    """
    if retry_count >= _API_MAX_RETRIES:
        logger.error(f"API调用失败，已达到最大重试次数({_API_MAX_RETRIES})")
        return None

    try:
        if not api_config:
            logger.error("API配置为空，无法获取卡券内容")
            return None

        if isinstance(api_config, str):
            api_config = json.loads(api_config)

        url = api_config.get('url')
        method = api_config.get('method', 'GET').upper()
        timeout = api_config.get('timeout', _API_DEFAULT_TIMEOUT)
        headers = api_config.get('headers', '{}')
        params = api_config.get('params', '{}')

        if isinstance(headers, str):
            headers = json.loads(headers)
        if isinstance(params, str):
            params = json.loads(params)

        # 如果是POST请求且没有指定Content-Type，则默认设为application/json
        if method == 'POST' and isinstance(headers, dict):
            has_content_type = any(k.lower() == 'content-type' for k in headers.keys())
            if not has_content_type:
                headers['Content-Type'] = 'application/json'

        # POST 动态参数替换
        if method == 'POST' and params:
            params = _build_api_params(params, context or {})

        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession() as http_session:
            if method == 'GET':
                async with http_session.get(url, headers=headers, params=params, timeout=timeout_obj) as response:
                    status_code = response.status
                    response_text = await response.text()
            elif method == 'POST':
                async with http_session.post(url, headers=headers, json=params, timeout=timeout_obj) as response:
                    status_code = response.status
                    response_text = await response.text()
            else:
                logger.error(f"不支持的HTTP方法: {method}")
                return None

        if status_code == 200:
            try:
                result = json.loads(response_text)
                if isinstance(result, dict):
                    content = result.get('data') or result.get('content') or result.get('card') or str(result)
                else:
                    content = str(result)
            except Exception:
                content = response_text
            logger.info(f"API调用成功，返回内容长度: {len(content)}")
            return content

        logger.warning(f"API调用失败: {status_code} - {response_text[:200]}")
        # 5xx 或 408 重试
        if (status_code >= 500 or status_code == 408) and retry_count < _API_MAX_RETRIES - 1:
            wait_time = (retry_count + 1) * 2
            logger.info(f"等待 {wait_time} 秒后重试...")
            await asyncio.sleep(wait_time)
            return await get_api_card_content(api_config, context, retry_count + 1)
        return None

    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        logger.warning(f"API调用网络异常: {e}")
        if retry_count < _API_MAX_RETRIES - 1:
            wait_time = (retry_count + 1) * 2
            logger.info(f"等待 {wait_time} 秒后重试...")
            await asyncio.sleep(wait_time)
            return await get_api_card_content(api_config, context, retry_count + 1)
        logger.error(f"API调用网络异常，已达到最大重试次数: {e}")
        return None
    except Exception as e:
        logger.error(f"API调用异常: {e}")
        return None


def _build_api_params(params: dict, context: Dict[str, str]) -> dict:
    """构建 API POST 参数，替换其中的占位符

    Args:
        params: 原始参数（含占位符）
        context: 上下文映射，提货场景包含 order_id/item_id/buyer_id/spec_name/spec_value 等

    Returns:
        替换后的参数
    """
    if not params or not isinstance(params, dict):
        return params

    param_mapping = {
        'order_id': context.get('order_id', ''),
        'item_id': context.get('item_id', ''),
        'buyer_id': context.get('buyer_id', ''),
        'spec_name': context.get('spec_name', ''),
        'spec_value': context.get('spec_value', ''),
        'order_amount': context.get('order_amount', ''),
        'order_quantity': context.get('order_quantity', ''),
        'timestamp': str(int(time.time())),
    }
    return recursive_replace_params(params, param_mapping)


async def build_delivery_content(
    session: AsyncSession,
    card: Card,
    context: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """按卡券类型生成纯文本发货内容（提货场景）

    各类型处理：
    - text：固定文字
    - data：消费一条批量数据（行锁）
    - api：调用外部接口拉取
    - image：返回图片URL（提货为纯文本，约定将图片URL作为文本返回）

    图片URL（image_url / image_urls）与备注（description）会拼接到文本内容中，
    备注支持 {DELIVERY_CONTENT} 及订单上下文变量替换。

    Args:
        session: 数据库会话（data 类型消费库存需在同一事务内）
        card: 卡券对象
        context: 订单上下文（提货时为虚拟订单号等），用于变量替换与 API 参数

    Returns:
        发货内容文本；获取失败返回 None
    """
    context = context or {}
    card_type = card.type
    text_content: Optional[str] = None

    if card_type == 'text':
        text_content = card.text_content
    elif card_type == 'data':
        text_content = await consume_batch_data(session, card.id)
        if text_content is None:
            logger.warning(f"卡券 {card.id} 批量数据已用完，提货失败")
            return None
    elif card_type == 'api':
        text_content = await get_api_card_content(card.api_config, context)
        if text_content is None:
            logger.warning(f"卡券 {card.id} API 获取内容失败，提货失败")
            return None
    elif card_type == 'image':
        # 图片类型本身无文字内容，下方统一处理图片URL拼接
        text_content = None
    else:
        logger.warning(f"卡券 {card.id} 类型 {card_type} 不支持提货")
        return None

    # 收集图片URL
    image_urls: list[str] = []
    if card.image_urls:
        try:
            parsed = json.loads(card.image_urls)
            if isinstance(parsed, list):
                image_urls = [u for u in parsed if u]
        except (json.JSONDecodeError, TypeError):
            image_urls = []
    if not image_urls and card.image_url:
        image_urls = [card.image_url]

    card_description = card.description or ''

    # 组装文本部分
    if text_content:
        text_part = process_delivery_content_with_description(text_content, card_description, context)
    elif card_description:
        text_part = replace_order_context_variables(card_description, context)
    else:
        text_part = ''

    # 纯文本返回：将图片URL以换行附加在内容后
    parts = []
    if text_part:
        parts.append(text_part)
    if image_urls:
        parts.append('\n'.join(image_urls))

    if not parts:
        logger.warning(f"卡券 {card.id} 没有可发货的内容（文字/图片/备注均为空）")
        return None

    return '\n'.join(parts)
