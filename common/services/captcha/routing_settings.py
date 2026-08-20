"""滑块任务的远程/本机路由设置。

所有会在本机启动浏览器或真实鼠标的入口都应通过本模块读取同一份设置，
避免某个调用方绕过 ``captcha.remote_service_url`` 或
``captcha.local_slider_disabled``。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting


REMOTE_URL_KEY = "captcha.remote_service_url"
REMOTE_SECRET_KEY = "captcha.remote_secret_key"
REMOTE_PASS_COOKIES_KEY = "captcha.remote_pass_cookies"
LOCAL_SLIDER_DISABLED_KEY = "captcha.local_slider_disabled"

_ROUTING_KEYS = (
    REMOTE_URL_KEY,
    REMOTE_SECRET_KEY,
    REMOTE_PASS_COOKIES_KEY,
    LOCAL_SLIDER_DISABLED_KEY,
)


@dataclass(frozen=True, slots=True)
class CaptchaRoutingSettings:
    """一次滑块任务使用的路由快照。"""

    remote_config: dict[str, object] | None
    local_slider_disabled: bool


def build_captcha_routing_settings(
    values: Mapping[str, object],
    *,
    device_id: str = "",
) -> CaptchaRoutingSettings:
    """把数据库键值转换为可交给滑块编排器的配置。"""
    remote_url = str(values.get(REMOTE_URL_KEY) or "").strip()
    remote_secret = str(values.get(REMOTE_SECRET_KEY) or "").strip()
    pass_cookies = (
        str(values.get(REMOTE_PASS_COOKIES_KEY) or "").strip().lower()
        == "true"
    )
    local_slider_disabled = (
        str(values.get(LOCAL_SLIDER_DISABLED_KEY) or "").strip().lower()
        == "true"
    )

    remote_config: dict[str, object] | None = None
    if remote_url and remote_secret:
        remote_config = {
            "url": remote_url,
            "secret": remote_secret,
            "pass_cookies": pass_cookies,
            # 未允许传递 Cookie 时，设备 ID 同样不应发往远程服务。
            "device_id": str(device_id or "") if pass_cookies else "",
            # 只要明确配置了远程服务，远程不可用也不能静默抢本机鼠标。
            # 如果管理员希望使用本机引擎，应清空远程配置后再运行。
            "allow_local_fallback": False,
        }

    return CaptchaRoutingSettings(
        remote_config=remote_config,
        local_slider_disabled=local_slider_disabled,
    )


async def load_captcha_routing_settings(
    *,
    device_id: str = "",
    log_tag: str = "",
) -> CaptchaRoutingSettings | None:
    """实时读取滑块路由；读取失败返回 ``None``，由调用方按安全策略处理。"""
    try:
        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(SystemSetting).where(SystemSetting.key.in_(_ROUTING_KEYS))
                )
            ).scalars().all()
        values = {row.key: (row.value or "") for row in rows}
        return build_captcha_routing_settings(values, device_id=device_id)
    except Exception as exc:
        prefix = f"【{log_tag}】" if log_tag else ""
        logger.warning(f"{prefix}读取滑块路由配置失败: {exc}")
        return None
