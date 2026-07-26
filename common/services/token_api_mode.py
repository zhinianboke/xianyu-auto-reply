"""
Token 获取接口方式（小程序 / 网页）公共模块。

功能：
1. 定义 Token 获取接口的两种方式及其 mtop 接口名
2. 提供系统设置 ``token.api_mode`` 的实时读取（异步 / 同步两种入口）
3. 提供风控自动切换时的「另一个接口」取值

说明：
    设置项每次使用时实时查库，确保运行中的 WebSocket / 定时任务无需重启即可生效，
    与 ``captcha.local_slider_disabled`` 的实时开关口径保持一致。
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from common.db.compat import db_manager
from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting


# 系统设置键名
TOKEN_API_MODE_SETTING_KEY = "token.api_mode"

# 小程序接口（默认）
TOKEN_API_MODE_MINIAPP = "miniapp"
# 网页接口
TOKEN_API_MODE_WEB = "web"

# 合法的接口方式集合
TOKEN_API_MODES = (TOKEN_API_MODE_MINIAPP, TOKEN_API_MODE_WEB)

# 默认接口方式：小程序接口
DEFAULT_TOKEN_API_MODE = TOKEN_API_MODE_MINIAPP

# 接口方式 -> mtop 接口名
TOKEN_API_NAMES = {
    TOKEN_API_MODE_MINIAPP: "mtop.taobao.idlemessage.wx.login.token",
    TOKEN_API_MODE_WEB: "mtop.taobao.idlemessage.pc.login.token",
}

# 接口方式 -> 中文名称，用于日志与提示
TOKEN_API_MODE_LABELS = {
    TOKEN_API_MODE_MINIAPP: "小程序接口",
    TOKEN_API_MODE_WEB: "网页接口",
}


def normalize_token_api_mode(value: object) -> str:
    """把任意输入归一化为合法的接口方式。

    Args:
        value: 待归一化的值（通常来自数据库或接口入参）
    Returns:
        合法的接口方式，非法值一律回落到默认的小程序接口
    """
    mode = str(value or "").strip().lower()
    return mode if mode in TOKEN_API_MODES else DEFAULT_TOKEN_API_MODE


def get_token_api_name(mode: object) -> str:
    """取接口方式对应的 mtop 接口名。

    Args:
        mode: 接口方式
    Returns:
        mtop 接口名
    """
    return TOKEN_API_NAMES[normalize_token_api_mode(mode)]


def get_token_api_mode_label(mode: object) -> str:
    """取接口方式的中文名称，用于日志与用户提示。

    Args:
        mode: 接口方式
    Returns:
        中文名称
    """
    return TOKEN_API_MODE_LABELS[normalize_token_api_mode(mode)]


def get_alternate_token_api_mode(mode: object) -> str:
    """取「另一个」接口方式，用于触发风控后的自动切换。

    Args:
        mode: 当前接口方式
    Returns:
        与当前方式不同的另一种接口方式
    """
    current = normalize_token_api_mode(mode)
    return TOKEN_API_MODE_WEB if current == TOKEN_API_MODE_MINIAPP else TOKEN_API_MODE_MINIAPP


async def load_token_api_mode(log_tag: str = "") -> str:
    """实时读取系统设置中的 Token 获取方式（异步）。

    每次调用都查库，保证系统设置修改后无需重启服务即可生效。
    读取失败时回落到默认的小程序接口，不阻断取 Token 流程。

    Args:
        log_tag: 日志前缀标识（如账号 ID），仅用于日志定位
    Returns:
        合法的接口方式
    """
    try:
        async with async_session_maker() as session:
            value = (
                await session.execute(
                    select(SystemSetting.value)
                    .where(SystemSetting.key == TOKEN_API_MODE_SETTING_KEY)
                    .limit(1)
                )
            ).scalar_one_or_none()
        return normalize_token_api_mode(value)
    except Exception as e:
        prefix = f"【{log_tag}】" if log_tag else ""
        logger.warning(
            f"{prefix}读取Token获取方式设置失败，本次使用默认的"
            f"{TOKEN_API_MODE_LABELS[DEFAULT_TOKEN_API_MODE]}: {e}"
        )
        return DEFAULT_TOKEN_API_MODE


def load_token_api_mode_sync(log_tag: str = "") -> str:
    """实时读取系统设置中的 Token 获取方式（同步）。

    供同步上下文（如滑块线程中的 ``request_fresh_captcha_url``）使用。
    读取失败时回落到默认的小程序接口。

    Args:
        log_tag: 日志前缀标识（如账号 ID），仅用于日志定位
    Returns:
        合法的接口方式
    """
    try:
        value = db_manager.get_system_setting(
            TOKEN_API_MODE_SETTING_KEY, DEFAULT_TOKEN_API_MODE
        )
        return normalize_token_api_mode(value)
    except Exception as e:
        prefix = f"【{log_tag}】" if log_tag else ""
        logger.warning(
            f"{prefix}读取Token获取方式设置失败，本次使用默认的"
            f"{TOKEN_API_MODE_LABELS[DEFAULT_TOKEN_API_MODE]}: {e}"
        )
        return DEFAULT_TOKEN_API_MODE
