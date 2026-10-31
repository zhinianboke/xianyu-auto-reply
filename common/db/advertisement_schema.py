"""广告新增首页类型、软删除、支付关联字段和类型字典的启动自检，保留历史数据。"""
from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import text

from common.services.advertisement_types import AD_PRICE_DEFAULTS, AD_TYPE_DICTIONARY, AD_TYPE_LABELS


async def ensure_advertisement_schema(conn) -> None:
    """在启动命名锁内幂等补齐广告字段、类型字典与空价格，不覆盖已配置价格。"""
    result = await conn.execute(text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'xy_advertisements' AND COLUMN_NAME = 'ad_type'"
    ))
    column_type = result.scalar()
    if not column_type:
        raise RuntimeError("广告表类型字段不存在，无法初始化首页广告")
    existing = re.findall(r"'([^']+)'", column_type)
    required = [item.value for item in AD_TYPE_LABELS]
    if not set(required).issubset(existing):
        # 元数据枚举值严格限定字符，原有枚举顺序保留，只追加缺失项。
        values = existing + [value for value in required if value not in existing]
        if any(not re.fullmatch(r"[A-Za-z0-9_]+", value) for value in values):
            raise RuntimeError("广告类型字段包含无法安全迁移的枚举值")
        enum_sql = ",".join(f"'{value}'" for value in values)
        await conn.execute(text(
            f"ALTER TABLE xy_advertisements MODIFY COLUMN ad_type ENUM({enum_sql}) "
            "DEFAULT 'text' COMMENT '广告类型：仪表盘轮播图、仪表盘文字广告、首页轮播图、首页文字广告'"
        ))
        logger.info("广告类型字段已扩展，历史类型值和顺序保留")

    columns = (
        ("xy_advertisements", "is_deleted", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否删除：0-正常，1-已删除'"),
        ("xy_recharge_orders", "ad_id", "BIGINT DEFAULT NULL COMMENT '广告付款关联广告ID'"),
        ("xy_recharge_orders", "ad_settled_at", "DATETIME DEFAULT NULL COMMENT '广告付款结算时间'"),
    )
    for table_name, column_name, definition in columns:
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table_name AND COLUMN_NAME = :column_name"
        ), {"table_name": table_name, "column_name": column_name})
        if not result.scalar():
            await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
            logger.info("广告相关字段已补齐：{}.{}", table_name, column_name)

    for index, (ad_type, label) in enumerate(AD_TYPE_LABELS.items(), 1):
        await conn.execute(text(
            "INSERT INTO xy_data_dictionaries (dict_type, dict_value, dict_label, sort_order, enabled) "
            "VALUES (:dict_type, :dict_value, :dict_label, :sort_order, 1) "
            "ON DUPLICATE KEY UPDATE dict_label = VALUES(dict_label), sort_order = VALUES(sort_order)"
        ), {"dict_type": AD_TYPE_DICTIONARY, "dict_value": ad_type.value, "dict_label": label, "sort_order": index * 10})
    for key, (value, description) in AD_PRICE_DEFAULTS.items():
        await conn.execute(text(
            "INSERT IGNORE INTO xy_system_settings (`key`, value, description, updated_at) "
            "VALUES (:key, :value, :description, NOW())"
        ), {"key": key, "value": value, "description": description})
    logger.info("广告类型字典及四类费用设置自检完成")
