"""
日志配置工具

功能：
1. 提供 InterceptHandler，将标准 logging 日志转发到 loguru
2. 提供 setup_logging 函数，统一配置各服务的普通日志与错误日志输出
3. 提供 update_log_retention 函数，动态更新日志保留天数
4. 提供 apply_db_log_retention 函数，从数据库读取日志保留天数并应用
5. 提供 run_db_log_retention_sync 函数，支持日志保留天数运行时动态刷新和数据库轮询同步，便于系统设置修改后实时生效
6. 避免各服务重复定义相同的日志配置代码
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from loguru import logger
from common.core.config import get_settings
from common.utils.file_log_sink import ObservableFileSink
from common.utils.time_utils import BEIJING_TZ

# 默认日志保留天数
DEFAULT_LOG_RETENTION_DAYS = 7

# 模块级变量：跟踪普通日志与错误日志处理器，支持动态更新
_file_handler_id: int | None = None
_error_file_handler_id: int | None = None
_current_log_file: Path | None = None
_current_retention_days: int = DEFAULT_LOG_RETENTION_DAYS

# 文件日志格式与轮转大小（普通日志和错误日志共用）
_FILE_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
_FILE_LOG_ROTATION = os.environ.get('LOG_FILE_MAX_SIZE') or get_settings().log_file_max_size
_current_log_level = 'INFO'


def _beijing_log_time(record: dict) -> None:
    """将同一日志记录时间转为北京时间，所有输出复用该记录。"""
    record['time'] = record['time'].astimezone(BEIJING_TZ)


class InterceptHandler(logging.Handler):
    """拦截标准logging日志并转发到loguru
    
    将 Python 标准 logging 模块的日志统一转发到 loguru，
    确保所有日志输出格式一致。
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru 级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用者
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _add_file_handlers(log_file: Path, retention_days: int) -> tuple[int, int]:
    """创建普通日志和错误日志处理器。

    Args:
        log_file: 普通日志文件路径。
        retention_days: 日志文件保留天数。

    Returns:
        普通日志处理器 ID 和错误日志处理器 ID。
    """
    common_handler_id = logger.add(
        ObservableFileSink(log_file, rotation=_FILE_LOG_ROTATION, retention=f"{retention_days} days", encoding='utf-8'),
        level=_current_log_level,
        format=_FILE_LOG_FORMAT,
        enqueue=True,
    )
    error_handler_id = logger.add(
        ObservableFileSink(log_file.with_name(log_file.stem + '_error.log'), rotation=_FILE_LOG_ROTATION,
                           retention=f"{retention_days} days", encoding='utf-8'),
        level="ERROR",
        format=_FILE_LOG_FORMAT,
        enqueue=True,
    )
    return common_handler_id, error_handler_id


def setup_logging(
    log_file: Path,
    log_level: str = "INFO",
    third_party_loggers: Optional[List[str]] = None,
    retention_days: int = DEFAULT_LOG_RETENTION_DAYS,
) -> None:
    """统一配置服务日志
    
    配置控制台、项目业务日志及项目专属错误日志，并将标准logging转发到loguru。
    ERROR及以上同条记录双写，控制台和文件使用相同格式、级别与滚动保留策略。
    
    Args:
        log_file: 日志文件路径
        log_level: 控制台日志级别，默认 INFO
        third_party_loggers: 需要拦截的第三方库日志名称列表
        retention_days: 日志保留天数，默认 7 天
    """
    global _file_handler_id, _error_file_handler_id, _current_log_file, _current_retention_days
    global _current_log_level
    # 禁止DEBUG输出，同时确保ERROR始终进入控制台和正常文件。
    configured_level = logger.level(log_level.upper()).no
    _current_log_level = 'INFO' if configured_level < 20 else 'ERROR' if configured_level > 40 else log_level.upper()
    _current_log_file = log_file
    _current_retention_days = retention_days

    # 确保日志目录存在
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认的 stderr handler
    logger.remove()
    logger.configure(patcher=_beijing_log_time)

    # 添加控制台输出
    logger.add(
        sys.stderr,
        level=_current_log_level,
        format=_FILE_LOG_FORMAT,
        colorize=False,
    )

    # 普通日志和控制台共用配置级别，ERROR及以上同时写入项目专属错误文件。
    _file_handler_id, _error_file_handler_id = _add_file_handlers(
        log_file,
        retention_days,
    )

    # 配置标准 logging 使用 InterceptHandler
    # 设置根 logger 级别为 INFO，避免第三方库的 DEBUG 日志被转发
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

    # 设置第三方库的日志拦截，并强制设为 INFO 级别
    if third_party_loggers:
        for name in third_party_loggers:
            lib_logger = logging.getLogger(name)
            lib_logger.handlers = [InterceptHandler()]
            lib_logger.setLevel(logging.INFO)
            lib_logger.propagate = False
    
    # 额外设置一些常见第三方库的日志级别为 INFO，避免 DEBUG 日志泄漏
    for name in ["passlib", "asyncio", "concurrent", "urllib3", "charset_normalizer"]:
        logging.getLogger(name).setLevel(logging.INFO)

    # SQLAlchemy 引擎/连接池自带的原生日志（BEGIN/SELECT/ROLLBACK 等）。
    # 引擎以 echo=False 创建时，其 logger 级别为 NOTSET，会继承 root 的 INFO，
    # 导致即便项目未开启 SQL_ECHO 仍会输出 SQL。这里显式钉到 WARNING 关闭原生输出。
    # 项目自有的 SQL 打印由 common.db.session 中的 sql_echo 钩子单独控制。
    for name in ["sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool", "asyncmy"]:
        logging.getLogger(name).setLevel(logging.WARNING)


def update_log_retention(retention_days: int, log_applied: bool = True) -> bool:
    """动态更新日志文件保留天数
    
    移除当前普通日志和错误日志处理器，使用新的保留天数重新添加。
    
    Args:
        retention_days: 新的日志保留天数（1~365）
    """
    global _file_handler_id, _error_file_handler_id, _current_retention_days

    if (
        _file_handler_id is None
        or _error_file_handler_id is None
        or _current_log_file is None
    ):
        logger.warning("日志文件处理器未初始化，无法更新保留天数")
        return False

    # 校验范围
    if not (1 <= retention_days <= 365):
        logger.warning(f"日志保留天数 {retention_days} 不在有效范围(1~365)内，跳过更新")
        return False

    if retention_days == _current_retention_days:
        return False

    # 移除旧处理器后统一重建，保证普通日志与错误日志策略始终一致。
    for handler_id in (_file_handler_id, _error_file_handler_id):
        try:
            logger.remove(handler_id)
        except ValueError:
            pass

    _file_handler_id, _error_file_handler_id = _add_file_handlers(
        _current_log_file,
        retention_days,
    )
    _current_retention_days = retention_days
    if log_applied:
        logger.info(f"日志保留天数已实时更新为 {retention_days} 天")
    return True


async def _query_db_log_retention_value() -> str | None:
    from common.db.session import async_session_maker
    from sqlalchemy import text

    async with async_session_maker() as session:
        result = await session.execute(
            text("SELECT value FROM xy_system_settings WHERE `key` = :key LIMIT 1"),
            {"key": "log.retention_days"},
        )
        row = result.fetchone()
        if not row or row[0] in (None, ""):
            return None
        return str(row[0]).strip()


async def apply_db_log_retention() -> None:
    """从数据库读取日志保留天数配置并应用
    
    读取 xy_system_settings 表中 log.retention_days 的值，
    如果存在且有效，则动态更新当前服务的日志保留天数。
    数据库读取失败时使用默认值，不影响服务启动。
    """
    try:
        raw_value = await _query_db_log_retention_value()
        if raw_value is None:
            logger.info(f"数据库中未找到日志保留天数配置，使用默认值 {DEFAULT_LOG_RETENTION_DAYS} 天")
            return

        days = int(raw_value)
        if 1 <= days <= 365:
            update_log_retention(days, log_applied=False)
            logger.info(f"日志保留天数已从数据库加载: {days} 天")
        else:
            logger.warning(f"数据库中日志保留天数 {days} 不在有效范围(1~365)，使用默认值")
    except Exception as e:
        logger.warning(f"读取日志保留天数配置失败，使用默认值: {e}")


async def run_db_log_retention_sync(poll_interval_seconds: int = 5) -> None:
    last_error_message: str | None = None
    last_invalid_value: str | None = None
    interval_seconds = max(1, int(poll_interval_seconds or 5))

    while True:
        try:
            raw_value = await _query_db_log_retention_value()
            if raw_value is not None:
                days = int(raw_value)
                if 1 <= days <= 365:
                    update_log_retention(days)
                    last_invalid_value = None
                elif raw_value != last_invalid_value:
                    logger.warning(f"数据库中日志保留天数 {days} 不在有效范围(1~365)，已忽略自动同步")
                    last_invalid_value = raw_value
            last_error_message = None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            error_message = str(e)
            if error_message != last_error_message:
                logger.warning(f"日志保留天数自动同步失败，将稍后重试: {error_message}")
                last_error_message = error_message

        await asyncio.sleep(interval_seconds)
