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


def _patch_asyncmy_ping():
    """
    兼容 asyncmy 新版本 ping() 方法签名变更

    新版 asyncmy (>=0.2.10) 移除了 ping(reconnect) 参数，
    而 SQLAlchemy 的 pool_pre_ping 机制调用 ping(reconnect=True)，
    导致 TypeError。直接 patch asyncmy 底层方法使其接受 reconnect 参数。
    """
    try:
        import asyncmy.connection as _asyncmy_conn

        _original = _asyncmy_conn.Connection.ping

        # 如果已经 patch 过，跳过
        if getattr(_original, '_compat_patched', False):
            return

        # 检查是否需要 patch（新版本不接受 reconnect）
        import inspect
        try:
            sig = inspect.signature(_original)
            if 'reconnect' in sig.parameters:
                # 旧版本，无需 patch
                return
        except (ValueError, TypeError):
            # 无法检测签名，保险起见做 patch
            pass

        # 替换为兼容版本
        async def _patched_ping(self, reconnect=True):
            return await _original(self)

        _patched_ping._compat_patched = True
        _asyncmy_conn.Connection.ping = _patched_ping

    except (ImportError, AttributeError, Exception):
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
        
        if parameters:
            if isinstance(parameters, dict):
                # 字典参数
                for key, value in parameters.items():
                    if isinstance(value, str):
                        value = f"'{value}'"
                    elif value is None:
                        value = "NULL"
                    elif isinstance(value, bool):
                        value = "1" if value else "0"
                    elif isinstance(value, bytes):
                        value = f"X'{value.hex()}'"
                    sql_str = sql_str.replace(f":{key}", str(value))
            elif isinstance(parameters, (list, tuple)):
                # 位置参数
                for param in parameters:
                    if isinstance(param, dict):
                        for key, value in param.items():
                            if isinstance(value, str):
                                value = f"'{value}'"
                            elif value is None:
                                value = "NULL"
                            elif isinstance(value, bool):
                                value = "1" if value else "0"
                            sql_str = sql_str.replace(f":{key}", str(value), 1)
        
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

