"""
数据库会话配置

提供异步数据库连接和会话管理
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

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

# 配置SQL日志记录器（关闭SQL输出）
sql_logger = logging.getLogger("sqlalchemy.engine")
sql_logger.setLevel(logging.WARNING)  # 只输出警告及以上级别

# 创建自定义的SQL格式化处理器
class SQLFormatter(logging.Formatter):
    """自定义SQL格式化器，输出拼接好参数的完整SQL"""
    
    def format(self, record):
        # 添加时间戳和SQL标识
        return f"[SQL] {record.getMessage()}"


# 添加控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(SQLFormatter())
sql_logger.addHandler(console_handler)
sql_logger.propagate = False


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
async_engine = create_async_engine(
    settings.async_database_url,
    echo=False,  # 关闭SQL输出
    echo_pool=False,  # 不输出连接池日志
    pool_pre_ping=False,  # 关闭 pre_ping（asyncmy 新版本不兼容）
    pool_size=50,  # 连接池大小（增大以支持大量后台任务+前端API请求）
    max_overflow=100,  # 最大溢出连接数
    pool_timeout=60,  # 获取连接超时时间
    pool_recycle=600,  # 连接回收时间（10分钟），防止MySQL断开
)


# 监听SQL执行事件，输出完整的SQL（带参数）
@event.listens_for(async_engine.sync_engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    在SQL执行前触发，打印完整的SQL语句（参数已拼接）
    """
    compiled_sql = _compile_sql_with_params(statement, parameters)
    sql_logger.info(f"\n{'='*60}\n{compiled_sql}\n{'='*60}")


async_session_maker = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    async with async_session_maker() as session:
        yield session

