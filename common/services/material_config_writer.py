"""
素材配置回写服务

发布成功后把素材携带的商品列表配置（item_config）一步到位回写到新商品列表项：
1. upsert xy_catalog_items（title/price/ai_prompt + metadata 的 multi_quantity_delivery/query_buttons）
2. 卡券绑定：先清旧关联再按 card_ids 批量绑定
3. 默认回复：upsert xy_default_replies(account_id, item_id)

全程分步 try/except，任何子步骤失败只记日志，不影响发布结果；幂等（重复调用结果一致）。
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from common.models.default_reply import DefaultReply
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.services.card_matcher import CardMatcher


def _get_item_config(material: Any) -> dict | None:
    """从素材对象提取 item_config，兼容 ORM 模型与序列化字典。"""
    if material is None:
        return None
    # 字典（_material_to_dict 或请求体）
    if isinstance(material, dict):
        cfg = material.get("item_config")
        return cfg if isinstance(cfg, dict) else None
    # ORM 模型
    cfg = getattr(material, "item_config", None)
    return cfg if isinstance(cfg, dict) else None


def _get_material_attr(material: Any, name: str, default: Any = None) -> Any:
    """读取素材字段，兼容 ORM 模型与字典。"""
    if material is None:
        return default
    if isinstance(material, dict):
        return material.get(name, default)
    return getattr(material, name, default)


async def apply_to_item(session: AsyncSession, material: Any, account_id: str, item_id: str) -> None:
    """把素材的 item_config 回写到指定商品列表项。

    Args:
        session: 当前数据库会话（与发布会话共用，失败时仅回滚回写产生的脏状态）。
        material: 素材对象（ProductMaterial ORM 或 _material_to_dict 字典）。
        account_id: 闲鱼账号标识（xy_accounts.account_id）。
        item_id: 发布成功的商品ID。
    """
    if not item_id or not account_id:
        logger.warning(f"素材配置回写跳过：缺少 item_id 或 account_id（item_id={item_id}）")
        return

    item_config = _get_item_config(material)
    if not item_config:
        logger.info(f"素材配置回写跳过：素材未携带 item_config，item_id={item_id}")
        return

    # account_id 反查 xy_accounts.id（account_pk）与 owner_id
    try:
        account = (
            await session.execute(
                select(XYAccount).where(XYAccount.account_id == account_id)
            )
        ).scalar_one_or_none()
    except Exception as exc:
        logger.warning(f"素材配置回写：反查账号失败 account_id={account_id}: {exc}")
        account = None
    if account is None:
        logger.warning(f"素材配置回写跳过：账号不存在 account_id={account_id}")
        return

    account_pk = account.id
    owner_id = account.owner_id
    title = _get_material_attr(material, "title")
    price = _get_material_attr(material, "price")
    price_str = str(price) if price is not None else None
    multi_quantity_delivery = bool(item_config.get("multi_quantity_delivery", False))
    card_ids = item_config.get("card_ids") or []
    default_reply = (item_config.get("default_reply") or "").strip()
    ai_prompt = item_config.get("ai_prompt")
    query_buttons = item_config.get("query_buttons") or []
    display_links = item_config.get("display_links") or []
    page_hint = item_config.get("page_hint") or ""

    # 1. upsert xy_catalog_items
    try:
        catalog_stmt = select(XYCatalogItem).where(
            XYCatalogItem.account_pk == account_pk,
            XYCatalogItem.item_id == item_id,
        )
        catalog_item = (await session.execute(catalog_stmt)).scalar_one_or_none()
        if catalog_item is not None:
            if title is not None:
                catalog_item.title = title
            if price_str is not None:
                catalog_item.price = price_str
            catalog_item.ai_prompt = ai_prompt
            metadata = dict(catalog_item.metadata_json or {})
            metadata["multi_quantity_delivery"] = multi_quantity_delivery
            metadata["query_buttons"] = query_buttons
            metadata["display_links"] = display_links
            metadata["page_hint"] = page_hint
            catalog_item.metadata_json = metadata
            flag_modified(catalog_item, "metadata_json")
        else:
            from datetime import datetime, timezone

            new_metadata = {
                "multi_quantity_delivery": multi_quantity_delivery,
                "query_buttons": query_buttons,
                "display_links": display_links,
                "page_hint": page_hint,
            }
            new_item = XYCatalogItem(
                owner_id=owner_id,
                account_pk=account_pk,
                item_id=item_id,
                title=title or "",
                price=price_str or "",
                ai_prompt=ai_prompt,
                is_polished=False,
                metadata_json=new_metadata,
                created_at=datetime.now(timezone.utc),
            )
            session.add(new_item)
        await session.flush()
        logger.info(f"素材配置回写：xy_catalog_items 已更新 item_id={item_id}")
    except Exception as exc:
        logger.warning(f"素材配置回写：更新 xy_catalog_items 失败 item_id={item_id}: {exc}")

    # 2. 卡券绑定：先清旧关联再按 card_ids 批量绑定
    try:
        matcher = CardMatcher(session)
        await matcher.delete_relations_by_item_id(item_id)
        if card_ids:
            await matcher.batch_bind_cards_to_items(
                user_id=owner_id,
                card_ids=list(card_ids),
                item_ids=[item_id],
            )
        logger.info(
            f"素材配置回写：卡券绑定完成 item_id={item_id}, card_ids={card_ids}"
        )
    except Exception as exc:
        logger.warning(f"素材配置回写：卡券绑定失败 item_id={item_id}: {exc}")

    # 3. 默认回复：upsert xy_default_replies(account_id, item_id)
    if not default_reply:
        logger.info(f"素材配置回写：default_reply 为空，跳过 item_id={item_id}")
    else:
        try:
            reply_stmt = select(DefaultReply).where(
                DefaultReply.account_id == account_id,
                DefaultReply.item_id == item_id,
            )
            reply = (await session.execute(reply_stmt)).scalar_one_or_none()
            if reply is not None:
                reply.reply_content = default_reply
                reply.enabled = True
            else:
                session.add(
                    DefaultReply(
                        account_id=account_id,
                        item_id=item_id,
                        reply_content=default_reply,
                        enabled=True,
                        reply_type="text",
                    )
                )
            logger.info(f"素材配置回写：默认回复已更新 item_id={item_id}")
        except Exception as exc:
            logger.warning(f"素材配置回写：更新默认回复失败 item_id={item_id}: {exc}")

    # 提交回写结果；失败仅记日志，不影响发布主流程
    try:
        await session.commit()
    except Exception as exc:
        logger.warning(f"素材配置回写：提交失败 item_id={item_id}: {exc}")
        try:
            await session.rollback()
        except Exception as rollback_exc:
            logger.warning(f"素材配置回写：回滚失败 item_id={item_id}: {rollback_exc}")
