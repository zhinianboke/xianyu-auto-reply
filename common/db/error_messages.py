"""
数据库异常对外提示转换。

功能：
1. 识别需要数据库管理员介入的连接异常
2. 返回适合直接展示给用户的中文错误信息
"""
from __future__ import annotations


def get_public_database_error_message(exc: BaseException) -> str | None:
    """
    将已知数据库异常转换为可展示的中文提示。

    Args:
        exc: 捕获到的原始异常

    Returns:
        已知数据库异常对应的中文提示；无法识别时返回 None
    """
    error_message = str(exc)

    if "(1129," in error_message and "is blocked because of many connection errors" in error_message:
        return (
            "数据库服务器已因连续连接异常暂时封锁当前应用服务器，"
            "请联系管理员在 MySQL 服务器执行 FLUSH HOSTS 后重试"
        )

    return None


__all__ = ["get_public_database_error_message"]
