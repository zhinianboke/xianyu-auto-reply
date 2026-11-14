"""
邮箱验证码的共享存储与校验服务。

功能：
1. 生成并保存邮箱验证码，统一清理过期记录
2. 校验验证码类型、有效期与最大错误次数
3. 验证成功后消费验证码，供注册、登录和密码重置复用
4. 发送中的验证码不允许校验，失败清理仅处理本次记录
"""
from __future__ import annotations

import random
import string
import time

# 沿用现有进程内存储；路由与认证服务共用同一个字典。
email_code_store: dict = {}
MAX_EMAIL_CODE_ATTEMPTS = 5


def generate_verification_code(length: int = 6) -> str:
    """生成指定长度的随机数字验证码。

    Args:
        length: 数字位数，默认 6 位。
    Returns:
        验证码字符串。
    """
    return "".join(random.choices(string.digits, k=length))


def cleanup_expired_email_codes():
    """清理共享内存中已过期的邮箱验证码，无参数且无返回值。"""
    current_time = time.time()
    expired_keys = [k for k, v in email_code_store.items() if v["expires_at"] < current_time]
    for k in expired_keys:
        del email_code_store[k]


def invalidate_email_code(email: str, expected_record: dict) -> None:
    """仅清理本次发送保存的验证码，避免误删后续请求的新记录。

    Args:
        email: 收件邮箱。
        expected_record: 本次发送保存在共享内存中的记录对象。
    Returns:
        无返回值；记录已消费或已被替换时不执行清理。
    """
    if email_code_store.get(email) is expected_record:
        email_code_store.pop(email)


def check_email_code(email: str, code: str, code_type: str = "login") -> tuple[bool, str]:
    """
    验证邮箱验证码（供其他模块调用）

    Args:
        email: 收件邮箱。
        code: 用户提交的验证码。
        code_type: 邮件用途，必须与保存的验证码类型一致。
    Returns:
        (是否成功, 成功提示或具体拒绝原因)。

    安全说明：单个验证码最多允许尝试 MAX_EMAIL_CODE_ATTEMPTS 次，
    超过后立即作废，防止 6 位数字验证码被暴力枚举。
    """
    cleanup_expired_email_codes()

    stored = email_code_store.get(email)

    if not stored:
        return False, "验证码不存在或已过期"

    if stored["expires_at"] < time.time():
        del email_code_store[email]
        return False, "验证码已过期"

    if stored["type"] != code_type:
        return False, "验证码类型不匹配"

    if stored.get("is_pending"):
        return False, "验证码正在发送，请稍后重试"

    if stored["code"] != code:
        # 记录失败次数，超过上限直接作废，避免暴力枚举
        stored["fail_count"] = stored.get("fail_count", 0) + 1
        if stored["fail_count"] >= MAX_EMAIL_CODE_ATTEMPTS:
            del email_code_store[email]
            return False, "验证码错误次数过多，请重新获取验证码"
        remaining = MAX_EMAIL_CODE_ATTEMPTS - stored["fail_count"]
        return False, f"验证码错误，还可尝试 {remaining} 次"

    # 验证成功后删除
    del email_code_store[email]

    return True, "验证码验证成功"
