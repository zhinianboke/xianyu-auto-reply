"""
远程滑块请求超时配置

功能：
1. 为 backend-web、同步远程客户端和异步远程客户端提供统一超时
2. 为真人鼠标单槽位排队预留时间，避免请求仍在服务端执行时调用方提前断开
"""
from __future__ import annotations


_MIN_REMOTE_SOLVE_TIMEOUT_SECONDS = 300.0
_REMOTE_QUEUE_ALLOWANCE_SECONDS = 180.0


def get_remote_solve_timeout(browser_timeout: int) -> float:
    """计算远程滑块 HTTP 总超时。

    Args:
        browser_timeout: 单个滑块任务的浏览器执行超时秒数
    Returns:
        包含真人鼠标排队预算的 HTTP 总超时秒数
    """
    task_timeout = max(20, min(int(browser_timeout or 40), 120))
    return max(
        _MIN_REMOTE_SOLVE_TIMEOUT_SECONDS,
        task_timeout + _REMOTE_QUEUE_ALLOWANCE_SECONDS,
    )
