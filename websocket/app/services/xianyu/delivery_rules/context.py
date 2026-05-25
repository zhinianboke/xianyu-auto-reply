"""
禁止发货检查上下文

功能：
1. 封装规则检查所需的所有上下文信息
2. 避免每条规则方法签名过长
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeliveryCheckContext:
    """发货检查上下文，传递给每条规则的 check 方法"""

    # 卖家账号ID（xy_accounts.account_id）
    cookie_id: str

    # 卖家Cookie字符串
    cookies_str: str

    # 订单号
    order_no: str

    # 买家用户ID
    buyer_id: str

    # 商品ID（可能为空）
    item_id: str | None = None

    # 聊天会话ID（可能为空）
    chat_id: str | None = None

    # 日志前缀
    log_prefix: str = ""

    # 规则专属参数（从数据库 config 字段加载）
    rule_config: dict[str, Any] = field(default_factory=dict)

    # 卖家账号主键ID（用于查询本地订单表等）
    account_pk: int | None = None

    # 卖家所属用户ID
    owner_id: int | None = None
