"""WebSocket 建连异常分类，区分认证失效与可重试的网络中断。

明确的 Token/Session 失效优先于异常类型，避免关闭帧中的认证错误
被当成网络抖动；Windows 信号灯超时仍按传输错误处理。
"""
from __future__ import annotations


def is_token_or_session_failure(exc: BaseException) -> bool:
    """判断服务端是否明确报告认证失效。

    Args:
        exc: 建连或收发消息时捕获的原始异常。
    Returns:
        异常类型或内容含明确的 Token/Session 失效标识时返回 True。
    """
    error_text = f"{type(exc).__name__} {exc}".upper()
    return any(marker in error_text for marker in (
        "FAIL_SYS_SESSION_EXPIRED",
        "FAIL_SYS_TOKEN_EXPIRED",
        "FAIL_SYS_TOKEN_EXOIRED",
        "SESSION_EXPIRED",
        "TOKEN_EXPIRED",
        "SESSION IS INVALID",
        "INVALID SESSION",
        "TOKEN IS INVALID",
        "INVALID TOKEN",
    ))


def is_network_connection_error(exc: BaseException) -> bool:
    """判断异常是否应进入网络重试流程，明确的认证错误除外。

    Args:
        exc: 原始异常，保留 Windows OSError 的 winerror 属性。
    Returns:
        连接中断、超时或 Windows 信号灯超时返回 True。
    """
    if is_token_or_session_failure(exc):
        return False

    error_type = type(exc).__name__
    error_text = str(exc).lower()
    return (
        "ConnectionClosed" in error_type
        or "ConnectionResetError" in error_type
        or "TimeoutError" in error_type
        or getattr(exc, "winerror", None) == 121
        or any(marker in error_text for marker in (
            "no close frame received or sent",
            "connection reset",
            "winerror 121",
            "信号灯超时时间已到",
            "semaphore timeout period has expired",
        ))
    )
