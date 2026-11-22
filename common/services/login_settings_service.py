"""登录配置读取：即时加载滑块开关和公共邮箱后缀策略，不缓存用户配置。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.system_setting import SystemSetting
from common.services.email_domain_policy import EMAIL_DOMAIN_DEFAULTS

LOGIN_CAPTCHA_ENABLED_KEY = "login_captcha_enabled"


async def load_login_settings(session: AsyncSession) -> dict[str, str]:
    """读取当前登录配置；参数为请求会话，返回实际键值，数据库失败继续抛出。"""
    keys = (LOGIN_CAPTCHA_ENABLED_KEY, *EMAIL_DOMAIN_DEFAULTS)
    rows = await session.execute(
        select(SystemSetting.key, SystemSetting.value).where(SystemSetting.key.in_(keys))
    )
    return dict(rows.all())
