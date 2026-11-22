"""注册日志启动迁移：幂等补表、字段、索引和字典，扩容邮件审计邮箱而不改历史值。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import insert, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from common.models.data_dictionary import XYDataDictionary
from common.models.email_log import XYEmailLog
from common.models.registration_log import (
    REGISTRATION_OPERATION_CODE,
    REGISTRATION_OPERATION_DICTIONARY,
    REGISTRATION_OPERATION_SUBMIT,
    REGISTRATION_STATUS_DICTIONARY,
    RegistrationLog,
)
from common.utils.time_utils import get_beijing_now_naive

# DDL 仅使用固定标识符；历史缺失字段保持 NULL，不补造旧日志或发生时间。
_MISSING_COLUMN_DDL = {
    "id": "ALTER TABLE api_registration_logs ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '注册日志ID'",
    "owner_id": "ALTER TABLE api_registration_logs ADD COLUMN owner_id BIGINT NULL COMMENT '关联用户ID，无法真实定位时为空'",
    "username": "ALTER TABLE api_registration_logs ADD COLUMN username LONGTEXT NULL COMMENT '提交用户名'",
    "email": "ALTER TABLE api_registration_logs ADD COLUMN email LONGTEXT NULL COMMENT '注册邮箱'",
    "operation": "ALTER TABLE api_registration_logs ADD COLUMN operation VARCHAR(32) NULL COMMENT '注册操作，取值来自注册操作字典'",
    "success": "ALTER TABLE api_registration_logs ADD COLUMN success TINYINT(1) NULL COMMENT '是否成功，取值对应注册结果字典'",
    "client_ip": "ALTER TABLE api_registration_logs ADD COLUMN client_ip VARCHAR(64) NULL COMMENT '经可信代理校验的客户端IP'",
    "message": "ALTER TABLE api_registration_logs ADD COLUMN message LONGTEXT NULL COMMENT '真实结果说明或失败原因'",
    "created_at": "ALTER TABLE api_registration_logs ADD COLUMN created_at DATETIME NULL COMMENT '发生时间，北京时间'",
}
_LONGTEXT_COLUMN_DDL = {
    "username": "ALTER TABLE api_registration_logs MODIFY COLUMN username LONGTEXT NULL COMMENT '提交用户名'",
    "email": "ALTER TABLE api_registration_logs MODIFY COLUMN email LONGTEXT NULL COMMENT '注册邮箱'",
    "message": "ALTER TABLE api_registration_logs MODIFY COLUMN message LONGTEXT NULL COMMENT '真实结果说明或失败原因'",
}
_REGISTRATION_DICTIONARY_ITEMS = (
    (REGISTRATION_OPERATION_DICTIONARY, REGISTRATION_OPERATION_SUBMIT, "注册提交", 10),
    (REGISTRATION_OPERATION_DICTIONARY, REGISTRATION_OPERATION_CODE, "注册验证码", 20),
    (REGISTRATION_STATUS_DICTIONARY, "success", "成功", 10),
    (REGISTRATION_STATUS_DICTIONARY, "failed", "失败", 20),
)


async def _ensure_registration_table_options(conn: AsyncConnection) -> None:
    """先校验事务引擎与Unicode容量；既存不兼容表须停止写入、备份并授权迁移。

    Args:
        conn: 启动初始化锁内的连接；不能在校验完成前迁移其他注册日志字段。
    Returns:
        兼容表不执行DDL；不兼容表明确拒绝启动，不查空或自动转换以避免并发写入窗口。
    """
    if conn.dialect.name != "mysql":
        return
    metadata = (await conn.execute(text(
        "SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
    ), {"table_name": RegistrationLog.__tablename__})).first()
    if metadata is None:
        raise RuntimeError("注册日志表不存在，无法校验事务引擎和字符集")
    engine, collation = metadata
    incompatible_columns = (await conn.execute(text(
        "SELECT COLUMN_NAME, CHARACTER_SET_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
        "AND CHARACTER_SET_NAME IS NOT NULL AND CHARACTER_SET_NAME <> :charset"
    ), {"table_name": RegistrationLog.__tablename__, "charset": "utf8mb4"})).all()
    engine_ready = str(engine or "").casefold() == "innodb"
    charset_ready = str(collation or "").casefold().startswith("utf8mb4_") and not incompatible_columns
    if engine_ready and charset_ready:
        return
    # 查空与ALTER不能原子化，其他运行实例可写入；即使当前为空也不得自动转换。
    raise RuntimeError(
        "注册日志表引擎或字符集不兼容，已停止启动以保护历史审计："
        f"引擎={engine!r}，排序规则={collation!r}，非utf8mb4字段={incompatible_columns!r}。"
        "请停止相关服务写入并先备份数据库，经管理员确认后迁移至InnoDB和utf8mb4；"
        "程序不会自动转换既存表，即使当前为空"
    )


async def _ensure_registration_columns(conn: AsyncConnection) -> None:
    """补齐旧注册表缺失字段并扩容文本；参数为统一自检连接，不改变已有记录内容。"""
    columns = await conn.run_sync(lambda sync: inspect(sync).get_columns(RegistrationLog.__tablename__))
    existing = {column["name"]: column for column in columns}
    if conn.dialect.name != "mysql":
        # 非 MySQL 仅用于隔离验证；不尝试在其他数据库执行 MySQL ALTER。
        if not set(_MISSING_COLUMN_DDL).issubset(existing):
            raise RuntimeError("注册日志字段补齐只支持项目使用的 MySQL 数据库")
        return
    for name, ddl in _MISSING_COLUMN_DDL.items():
        if name not in existing:
            await conn.execute(text(ddl))
            logger.info("注册日志迁移已补齐字段: api_registration_logs.{}", name)
    for name, ddl in _LONGTEXT_COLUMN_DDL.items():
        if name in existing and str(existing[name]["type"]).upper() != "LONGTEXT":
            await conn.execute(text(ddl))
            logger.info("注册日志迁移已扩容原参数字段，保留历史值: api_registration_logs.{}", name)
    comment = await conn.run_sync(lambda sync: inspect(sync).get_table_comment(RegistrationLog.__tablename__))
    if comment.get("text") != "注册日志表":
        await conn.execute(text("ALTER TABLE api_registration_logs COMMENT = '注册日志表'"))


async def _ensure_email_recipient_capacity(conn: AsyncConnection) -> None:
    """扩容邮件收件邮箱以容纳被拒绝的超长注册参数，保持邮件与注册联合审计可提交。"""
    table = XYEmailLog.__table__
    await conn.run_sync(lambda sync: table.create(sync, checkfirst=True))
    columns = await conn.run_sync(lambda sync: inspect(sync).get_columns(table.name))
    recipient = next((column for column in columns if column["name"] == "recipient_email"), None)
    if recipient is None:
        raise RuntimeError("邮件日志缺少收件邮箱字段，无法保存注册验证码审计")
    if conn.dialect.name == "mysql" and str(recipient["type"]).upper() != "LONGTEXT":
        await conn.execute(text(
            "ALTER TABLE xy_email_logs MODIFY COLUMN recipient_email LONGTEXT NOT NULL "
            "COMMENT '收件邮箱，保留非法或超长原参数'"
        ))
        logger.info("注册日志迁移已扩容邮件收件邮箱为长文本，历史数据保持不变")


async def _ensure_registration_dictionary(conn: AsyncConnection) -> None:
    """仅插入缺失注册字典项，保留已有中文名称、排序、启用状态和历史时间。"""
    table = XYDataDictionary.__table__
    await conn.run_sync(lambda sync: table.create(sync, checkfirst=True))
    existing = set((await conn.execute(select(table.c.dict_type, table.c.dict_value).where(
        table.c.dict_type.in_((REGISTRATION_OPERATION_DICTIONARY, REGISTRATION_STATUS_DICTIONARY))
    ))).all())
    now = get_beijing_now_naive()
    for dict_type, value, label, order in _REGISTRATION_DICTIONARY_ITEMS:
        if (dict_type, value) not in existing:
            await conn.execute(insert(table).values(
                dict_type=dict_type, dict_value=value, dict_label=label, sort_order=order,
                enabled=True, created_at=now, updated_at=now,
            ))
            logger.info("注册日志迁移已补齐中文字典: {}.{}", dict_type, value)


async def ensure_registration_log_schema(conn: AsyncConnection) -> None:
    """幂等创建注册日志结构与字典；补齐失败向启动入口传播，禁止带缺失审计启动。

    Args:
        conn: 统一启动自检在数据库初始化锁内提供的事务连接。
    Returns:
        无返回值；只变更结构和缺失字典，不更新、删除或补造历史日志。
    """
    try:
        table = RegistrationLog.__table__
        await conn.run_sync(lambda sync: table.create(sync, checkfirst=True))
        # 事务/编码不兼容的既存表先拒绝启动，不能先改字段后才发现需要备份迁移。
        await _ensure_registration_table_options(conn)
        await _ensure_registration_columns(conn)
        for index in sorted(table.indexes, key=lambda item: item.name):
            await conn.run_sync(lambda sync, index=index: index.create(sync, checkfirst=True))
        await _ensure_email_recipient_capacity(conn)
        await _ensure_registration_dictionary(conn)
    except Exception:
        logger.exception("注册日志结构、索引或字典补齐失败，禁止继续启动")
        raise
    logger.info("注册日志表、字段、索引和中文字典自检完成；历史日志与业务数据保持不变")
