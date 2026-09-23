"""
数据库会话配置

提供异步数据库连接和会话管理
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.core.config import get_settings

settings = get_settings()


def _patch_asyncmy_ping() -> None:
    """兼容 SQLAlchemy 2.0.41 与 asyncmy 的 pool_pre_ping 调用签名。

    SQLAlchemy 的 MySQL 通用方言会无参调用适配层 ``ping()``，但该版本的
    ``AsyncAdapt_asyncmy_connection.ping`` 要求必须传入 ``reconnect``。
    仅为适配层补充默认值，不修改 asyncmy 驱动本身。
    """
    try:
        import inspect
        from sqlalchemy.dialects.mysql.asyncmy import AsyncAdapt_asyncmy_connection

        original_ping = AsyncAdapt_asyncmy_connection.ping

        # 如果已经 patch 过，跳过
        if getattr(original_ping, "_compat_patched", False):
            return

        try:
            reconnect = inspect.signature(original_ping).parameters.get("reconnect")
            if reconnect is None or reconnect.default is not inspect.Parameter.empty:
                return
        except (ValueError, TypeError):
            return

        def patched_ping(self, reconnect=False):
            return original_ping(self, reconnect)

        patched_ping._compat_patched = True
        AsyncAdapt_asyncmy_connection.ping = patched_ping

    except (ImportError, AttributeError):
        pass


# 在引擎创建前执行 patch
_patch_asyncmy_ping()


def _compile_sql_with_params(statement, parameters):
    """
    将SQL语句和参数编译成完整的可执行SQL
    
    Args:
        statement: SQL语句
        parameters: 参数字典或元组
    
    Returns:
        拼接好参数的完整SQL字符串
    """
    try:
        sql_str = str(statement)

        # SQL 回显用于排查问题，但不能把系统密钥写入日志。系统设置表中的
        # 敏感键可能通过 ORM 参数绑定出现，先识别键再仅脱敏对应值。
        sensitive_setting_keys = {
            "security.internal_api_token",
            "security.jwt_secret_key",
            "admin_password_hash",
            "password_login.remote_secret_key",
            "token.remote_secret_key",
        }

        def _is_sensitive_key(value) -> bool:
            return (
                isinstance(value, str)
                and value.strip().lower() in sensitive_setting_keys
            )

        def _contains_sensitive_key(value) -> bool:
            if isinstance(value, dict):
                return any(_contains_sensitive_key(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return any(_contains_sensitive_key(item) for item in value)
            return _is_sensitive_key(value)

        # SQLAlchemy 可能传入命名参数、扁平位置参数或 executemany 的参数列表。
        # 统一成若干组，避免只处理某一种驱动的参数形态。
        parameter_groups: list[dict | list | tuple] = []
        if isinstance(parameters, dict):
            parameter_groups = [parameters]
        elif isinstance(parameters, (list, tuple)):
            if any(isinstance(item, (dict, list, tuple)) for item in parameters):
                parameter_groups = list(parameters)
            else:
                parameter_groups = [parameters]

        lowered_sql = sql_str.lower()
        query_targets_settings = "xy_system_settings" in lowered_sql
        sensitive_query = query_targets_settings and (
            any(_contains_sensitive_key(group) for group in parameter_groups)
            or any(
                f"'{key}'" in lowered_sql or f'"{key}"' in lowered_sql
                for key in sensitive_setting_keys
            )
        )

        def _format_value(value, parameter_name: str | None = None):
            # 查询系统敏感设置时保留 setting key 便于定位，其他绑定值全部脱敏。
            if (
                sensitive_query
                and parameter_name not in {"key", "setting_key"}
                and not _is_sensitive_key(value)
            ):
                value = "***REDACTED***"
            if isinstance(value, str):
                return f"'{value}'"
            if value is None:
                return "NULL"
            if isinstance(value, bool):
                return "1" if value else "0"
            if isinstance(value, bytes):
                return f"X'{value.hex()}'"
            return str(value)
        
        def _replace_named(sql: str, key: str, value) -> str:
            formatted = _format_value(value, key)
            # 支持 SQLAlchemy 文本 SQL 和 MySQL pyformat 两种命名占位符。
            sql = sql.replace(f":{key}", formatted, 1)
            return sql.replace(f"%({key})s", formatted, 1)

        def _replace_positional(sql: str, values) -> str:
            for value in values:
                formatted = _format_value(value)
                question_index = sql.find("?")
                format_index = sql.find("%s")
                indexes = [index for index in (question_index, format_index) if index >= 0]
                if not indexes:
                    break
                index = min(indexes)
                token_length = 1 if sql[index] == "?" else 2
                sql = sql[:index] + formatted + sql[index + token_length:]
            return sql

        for group in parameter_groups:
            if isinstance(group, dict):
                for key, value in group.items():
                    sql_str = _replace_named(sql_str, str(key), value)
            elif isinstance(group, (list, tuple)):
                sql_str = _replace_positional(sql_str, group)
            # executemany 的参数组只需渲染第一组；占位符已耗尽时后续组不会污染日志。
            if sql_str.find("?") < 0 and sql_str.find("%s") < 0 and len(parameter_groups) > 1:
                break
        
        return sql_str
    except Exception:
        return str(statement)


# 创建异步引擎
# 连接池参数全部来自配置（可通过环境变量调优），适配上千账号同时运行的场景：
# - pool_pre_ping：取连接前先 ping，自动剔除被远程 MySQL 断开的失效连接，避免拿到坏连接卡住；
# - pool_use_lifo：优先复用最近使用的连接，让多余的空闲连接尽快被 pool_recycle 回收，
#   降低对远程库的常驻连接数（上千账号大多时间空闲时尤其有用）；
# - connect_args.connect_timeout：限制 TCP 建连耗时，远程库不可达时快速失败而不是无限阻塞，
#   从而让连接尽快归还连接池，缓解 "QueuePool limit ... reached" 连接池打满问题。
async_engine = create_async_engine(
    settings.async_database_url,
    echo=False,  # 关闭SQL输出
    echo_pool=False,  # 不输出连接池日志
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_use_lifo=settings.db_pool_use_lifo,
    connect_args={"connect_timeout": settings.db_connect_timeout},
)


# 监听SQL执行事件，输出完整的SQL（带参数）
# 仅在 settings.sql_echo 为 True 时注册钩子：
# - 开启时通过 loguru 输出，控制台与文件日志均可见（Docker 环境亦可见）；
# - 关闭时不注册钩子，不产生任何字符串拼接开销（适合高并发生产环境）。
def _register_sql_echo() -> None:
    @event.listens_for(async_engine.sync_engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """在SQL执行前触发，打印拼接好参数的完整SQL。"""
        compiled_sql = _compile_sql_with_params(statement, parameters)
        logger.opt(depth=1).info(f"[SQL]\n{'='*60}\n{compiled_sql}\n{'='*60}")


if settings.sql_echo:
    _register_sql_echo()


async_session_maker = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    async with async_session_maker() as session:
        yield session

