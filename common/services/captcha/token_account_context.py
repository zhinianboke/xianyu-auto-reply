"""
外部滑块请求的 Token 账号上下文。

功能：
1. 已登记账号保留原始标识，供公共 Token 客户端读取所属用户配置
2. 未登记的外部标识沿用系统配置；数据库查询异常直接抛出，禁止误判未登记
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from common.db.retry import with_db_retry
from common.db.session import async_session_maker
from common.models.user import User
from common.models.xy_account import XYAccount


@with_db_retry(max_retries=2, initial_delay=0.5)
async def resolve_external_captcha_token_account_id(
    account_id: str, call_user: str | None = None,
) -> str:
    """为未携带账号持久化上下文的外部滑块请求确定 Token 配置关联。

    Args:
        account_id: 外部请求的原始账号标识，不能使用清洗后的浏览器目录名。
        call_user: 公开接口已认证的调用用户名；已登记账号必须属于该用户。
    Returns:
        已登记时返回原始账号标识；未登记时返回空值，明确使用系统配置。
    Raises:
        Exception: 数据库查询失败，停止请求，不使用系统配置。
    """
    raw_id = str(account_id or "").strip()
    try:
        async with async_session_maker() as session:
            registered = (await session.execute(
                select(XYAccount.account_id, User.username)
                .outerjoin(User, User.id == XYAccount.owner_id)
                .where(XYAccount.account_id == raw_id)
            )).one_or_none()
            if registered is not None and call_user and registered.username != call_user:
                raise ValueError("闲鱼账号不属于该调用用户，不能使用其个人Token配置")
    except Exception as exc:
        logger.opt(exception=exc).error("外部滑块Token账号关联读取失败：account_id={}", raw_id)
        raise
    if registered is not None:
        return raw_id
    logger.info("外部滑块账号未登记，沿用系统Token配置：account_id={}", raw_id)
    return ""
