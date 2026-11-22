"""系统用户登录日志兼容入口：主系统与推广系统共用追加和查询实现。"""
from common.services.user_login_log_service import (
    LOGIN_METHOD_EMAIL_CODE,
    LOGIN_METHOD_EMAIL_PASSWORD,
    LOGIN_METHOD_USERNAME_PASSWORD,
    UserLoginLogService,
)

__all__ = [
    "LOGIN_METHOD_EMAIL_CODE",
    "LOGIN_METHOD_EMAIL_PASSWORD",
    "LOGIN_METHOD_USERNAME_PASSWORD",
    "UserLoginLogService",
]
