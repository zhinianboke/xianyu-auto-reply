"""
禁止发货规则引擎

功能：
1. 从数据库加载账号已启用的规则列表（带 5 分钟 TTL 缓存）
2. 按优先级顺序执行规则检查
3. 首条命中即停，返回统一结果
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger
from sqlalchemy import select, and_

from common.db.session import async_session_maker
from common.models.xy_delivery_block_rule import XYDeliveryBlockRule
from app.services.xianyu.delivery_rules.base_rule import RuleCheckResult
from app.services.xianyu.delivery_rules.context import DeliveryCheckContext
from app.services.xianyu.delivery_rules.rule_registry import get_rule_instance

# ---- TTL rule cache ----
_RULE_CACHE_TTL = 300  # 5 minutes
_rule_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def clear_rule_cache(account_id: str | None = None) -> None:
    """清除规则缓存

    Args:
        account_id: 指定账号则只清该账号缓存；None 清全部
    """
    if account_id is not None:
        _rule_cache.pop(account_id, None)
    else:
        _rule_cache.clear()


async def load_enabled_rules(account_id: str) -> list[dict[str, Any]]:
    """从数据库加载该账号所有已启用的规则配置（按 priority 排序）

    Args:
        account_id: 账号标识（xy_accounts.account_id）

    Returns:
        规则配置列表，每项包含：
        {
            'rule_code': str,
            'enabled': bool,
            'priority': int,
            'block_reason': str | None,
            'auto_close_order': bool,
            'only_card_after_close': bool,
            'excluded_item_ids': list[str],
            'config': dict,
        }
    """
    # Check cache first
    cached = _rule_cache.get(account_id)
    if cached is not None:
        ts, rules = cached
        if time.monotonic() - ts < _RULE_CACHE_TTL:
            return rules

    try:
        async with async_session_maker() as session:
            stmt = (
                select(XYDeliveryBlockRule)
                .where(
                    and_(
                        XYDeliveryBlockRule.account_id == account_id,
                        XYDeliveryBlockRule.enabled == True,
                    )
                )
                .order_by(XYDeliveryBlockRule.priority.asc())
            )
            result = await session.execute(stmt)
            rules = result.scalars().all()

            rule_list = []
            for rule in rules:
                # 归一化 excluded_item_ids
                excluded_raw = rule.excluded_item_ids
                excluded_list: list[str] = []
                if excluded_raw:
                    if isinstance(excluded_raw, str):
                        try:
                            import json
                            excluded_raw = json.loads(excluded_raw)
                        except Exception:
                            excluded_raw = []
                    if isinstance(excluded_raw, list):
                        for item in excluded_raw:
                            if item is not None:
                                text_item = str(item).strip()
                                if text_item:
                                    excluded_list.append(text_item)

                # 归一化 config
                config = rule.config or {}
                if isinstance(config, str):
                    try:
                        import json
                        config = json.loads(config)
                    except Exception:
                        config = {}

                rule_list.append({
                    "rule_code": rule.rule_code,
                    "enabled": rule.enabled,
                    "priority": rule.priority,
                    "block_reason": rule.block_reason,
                    "auto_close_order": bool(rule.auto_close_order),
                    "only_card_after_close": bool(rule.only_card_after_close),
                    "excluded_item_ids": excluded_list,
                    "config": config,
                })
            return rule_list
    except Exception as e:
        logger.error(f"加载禁止发货规则失败: account_id={account_id}, error={e}")
        return []


async def execute_rules(
    cookie_id: str,
    cookies_str: str,
    order_no: str,
    buyer_id: str,
    item_id: str | None = None,
    chat_id: str | None = None,
    log_prefix: str = "",
    account_pk: int | None = None,
    owner_id: int | None = None,
) -> dict[str, Any]:
    """执行禁止发货规则引擎

    按优先级顺序执行所有已启用规则，首条命中即停。

    Args:
        cookie_id: 卖家账号ID
        cookies_str: 卖家Cookie
        order_no: 订单号
        buyer_id: 买家用户ID
        item_id: 商品ID
        chat_id: 聊天会话ID
        log_prefix: 日志前缀
        account_pk: 账号主键
        owner_id: 所属用户ID

    Returns:
        {
            'hit': bool,                    # 是否有规则命中
            'rule_code': str | None,        # 命中的规则编码
            'rule_name': str | None,        # 命中的规则名称
            'reason': str,                  # 命中原因
            'block_reason': str,            # 配置的禁止发货原因（发给买家）
            'auto_close_order': bool,       # 是否主动关闭订单
            'only_card_after_close': bool,  # 关闭后是否只发卡券
            'extra_data': dict,             # 规则附加数据
        }
    """
    pf = log_prefix or f"【{cookie_id}】"

    # 1. 加载已启用规则
    rule_configs = await load_enabled_rules(cookie_id)

    if not rule_configs:
        # 没有任何已启用的规则 → 直接放行
        return {
            "hit": False,
            "rule_code": None,
            "rule_name": None,
            "reason": "",
            "block_reason": "",
            "auto_close_order": False,
            "only_card_after_close": False,
            "extra_data": {},
        }

    # 2. 逐条执行
    for rule_cfg in rule_configs:
        rule_code = rule_cfg["rule_code"]

        # 2.1 获取规则实例
        rule_instance = get_rule_instance(rule_code)
        if rule_instance is None:
            logger.warning(f"{pf}[规则引擎] 未注册的规则编码: {rule_code}，跳过")
            continue

        # 2.2 检查该规则的排除商品列表
        excluded_ids = rule_cfg.get("excluded_item_ids") or []
        if item_id and excluded_ids:
            current_item_id = str(item_id).strip()
            if current_item_id and current_item_id in {str(x).strip() for x in excluded_ids}:
                logger.info(
                    f"{pf}[规则引擎] 商品 {current_item_id} 命中规则 {rule_code} 的排除列表，跳过本规则"
                )
                continue

        # 2.3 构建上下文并执行检查
        context = DeliveryCheckContext(
            cookie_id=cookie_id,
            cookies_str=cookies_str,
            order_no=order_no,
            buyer_id=buyer_id,
            item_id=item_id,
            chat_id=chat_id,
            log_prefix=pf,
            rule_config=rule_cfg.get("config") or {},
            account_pk=account_pk,
            owner_id=owner_id,
        )

        try:
            check_result: RuleCheckResult = await rule_instance.check(context)
        except Exception as e:
            logger.error(
                f"{pf}[规则引擎] 规则 {rule_code} 执行异常: {e}，跳过本规则"
            )
            continue

        # 2.4 命中 → 返回该规则的配置
        if check_result.hit:
            logger.warning(
                f"{pf}[规则引擎] ❌ 命中规则 [{check_result.rule_name}]({rule_code}): "
                f"order_no={order_no}, buyer_id={buyer_id}, reason={check_result.reason}"
            )
            return {
                "hit": True,
                "rule_code": rule_code,
                "rule_name": check_result.rule_name,
                "reason": check_result.reason,
                "block_reason": (rule_cfg.get("block_reason") or "").strip(),
                "auto_close_order": rule_cfg.get("auto_close_order", False),
                "only_card_after_close": rule_cfg.get("only_card_after_close", False),
                "extra_data": check_result.extra_data,
            }

    # 3. 全部通过 → 放行
    logger.info(
        f"{pf}[规则引擎] 所有规则检查通过：order_no={order_no}, buyer_id={buyer_id}"
    )
    return {
        "hit": False,
        "rule_code": None,
        "rule_name": None,
        "reason": "",
        "block_reason": "",
        "auto_close_order": False,
        "only_card_after_close": False,
        "extra_data": {},
    }
