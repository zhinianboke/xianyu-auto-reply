"""支付订单表关键字段与交易号唯一索引的启动自检。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text


_PAYMENT_COLUMNS = (
    ("order_type", "VARCHAR(20) NOT NULL DEFAULT 'recharge' COMMENT '订单类型：recharge-余额充值，ad-广告申请付款'"),
    ("channel", "VARCHAR(16) NOT NULL DEFAULT 'alipay' COMMENT '支付渠道：alipay-支付宝当面付，zzcode-码支付'"),
    ("pay_type", "VARCHAR(16) DEFAULT NULL COMMENT '码支付子方式：alipay/wxpay/qqpay'"),
    ("zzcode_amount_confirmed", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '码支付订单金额是否已确认'"),
    ("callback_merchant_id", "VARCHAR(128) DEFAULT NULL COMMENT '创建订单时使用的回调验签商户ID'"),
    ("callback_verify_key", "TEXT NULL COMMENT '创建订单时使用的回调验签密钥或公钥'"),
    ("pay_target_kind", "VARCHAR(16) DEFAULT NULL COMMENT '支付目标类型：qrcode/payurl/urlscheme'"),
    ("pay_url", "VARCHAR(1000) DEFAULT NULL COMMENT '支付跳转或协议链接'"),
    ("ad_id", "BIGINT DEFAULT NULL COMMENT '广告付款关联广告ID'"),
    ("ad_settled_at", "DATETIME DEFAULT NULL COMMENT '广告付款结算时间'"),
)


async def ensure_payment_schema(conn) -> None:
    """幂等补齐支付关键结构，无法保证回调幂等时阻止服务启动。

    Args:
        conn: 已进入启动命名锁的数据库连接。
    Returns:
        None。支付结构不完整或历史交易号冲突时抛出 RuntimeError。
    """
    table_exists = (await conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'xy_recharge_orders'"
    ))).scalar()
    if not table_exists:
        raise RuntimeError("充值订单表不存在，无法初始化支付功能")

    for column_name, definition in _PAYMENT_COLUMNS:
        exists = (await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'xy_recharge_orders' "
            "AND COLUMN_NAME = :column_name"
        ), {"column_name": column_name})).scalar()
        if not exists:
            await conn.execute(text(
                f"ALTER TABLE xy_recharge_orders ADD COLUMN `{column_name}` {definition}"
            ))
            logger.info("支付订单字段已补齐：xy_recharge_orders.{}", column_name)

    index_rows = (await conn.execute(text(
        "SELECT NON_UNIQUE, COLUMN_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'xy_recharge_orders' "
        "AND INDEX_NAME = 'uk_recharge_trade_no' ORDER BY SEQ_IN_INDEX"
    ))).all()
    if index_rows:
        if len(index_rows) != 1 or index_rows[0][0] != 0 or index_rows[0][1] != "trade_no":
            raise RuntimeError("支付交易号索引 uk_recharge_trade_no 结构异常，请人工核查数据库")
    else:
        duplicate_trade_no = (await conn.execute(text(
            "SELECT trade_no FROM xy_recharge_orders "
            "WHERE trade_no IS NOT NULL "
            "GROUP BY trade_no HAVING COUNT(*) > 1 LIMIT 1"
        ))).scalar()
        if duplicate_trade_no is not None:
            raise RuntimeError(
                f"充值订单存在重复交易号 {duplicate_trade_no!r}，请先备份并人工核查历史数据"
            )
        await conn.execute(text(
            "ALTER TABLE xy_recharge_orders "
            "ADD UNIQUE KEY uk_recharge_trade_no (trade_no)"
        ))
        logger.info("支付交易号唯一索引已补齐：uk_recharge_trade_no")

    required_columns = {"trade_no", *(name for name, _ in _PAYMENT_COLUMNS)}
    existing_columns = set((await conn.execute(text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'xy_recharge_orders'"
    ))).scalars().all())
    missing_columns = sorted(required_columns - existing_columns)
    if missing_columns:
        raise RuntimeError(f"支付订单表关键字段缺失：{', '.join(missing_columns)}")



