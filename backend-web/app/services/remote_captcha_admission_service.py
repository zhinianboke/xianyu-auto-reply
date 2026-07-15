"""
远程过滑块调用准入服务。

功能：
1. 读取远程调用处理中数量上限和冷却配置
2. 在冷却期内拒绝远程调用
3. 处理中滑块数量达到上限时启动冷却
"""
from __future__ import annotations

import math
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.risk_control_log_service import RiskControlLogService
from app.services.system_setting_service import SystemSettingService
from common.models.system_setting import SystemSetting


REMOTE_PROCESSING_MAX_KEY = "captcha.remote_processing_max"
REMOTE_COOLDOWN_SECONDS_KEY = "captcha.remote_cooldown_seconds"
REMOTE_COOLDOWN_UNTIL_KEY = "captcha.remote_cooldown_until"

DEFAULT_REMOTE_PROCESSING_MAX = 20
DEFAULT_REMOTE_COOLDOWN_SECONDS = 600


def sanitize_nonnegative_int(value: object, default: int) -> int:
    """将配置值规整为非负整数，非法值回退默认值。

    Args:
        value: 待转换的配置值。
        default: 值非法时使用的默认值。

    Returns:
        非负整数配置值。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


class RemoteCaptchaAdmissionService:
    """根据处理中数量和冷却状态控制远程过滑块调用。"""

    def __init__(self, session: AsyncSession):
        """初始化准入服务。

        Args:
            session: 异步数据库会话。
        """
        self.session = session
        self.risk_log_service = RiskControlLogService(session)
        self.setting_service = SystemSettingService(session)

    async def check_admission(self) -> tuple[bool, str | None]:
        """检查当前远程请求是否允许进入滑块处理流程。

        Returns:
            二元组 ``(是否放行, 拒绝原因)``。达到上限时，本次请求被拒绝；
            冷却时间大于零时同时记录冷却截止时间。
        """
        settings = await self._get_settings()
        max_processing = sanitize_nonnegative_int(
            settings.get(REMOTE_PROCESSING_MAX_KEY),
            DEFAULT_REMOTE_PROCESSING_MAX,
        )
        cooldown_seconds = sanitize_nonnegative_int(
            settings.get(REMOTE_COOLDOWN_SECONDS_KEY),
            DEFAULT_REMOTE_COOLDOWN_SECONDS,
        )
        cooldown_until = self._parse_timestamp(settings.get(REMOTE_COOLDOWN_UNTIL_KEY))
        now = time.time()

        # 最大条数为 0 时整套容量限制关闭，历史冷却状态不再生效。
        if max_processing == 0:
            return True, None

        if cooldown_seconds > 0 and cooldown_until > now:
            remaining_seconds = max(1, math.ceil(cooldown_until - now))
            return (
                False,
                f"远程过滑块调用正在冷却中，请在 {remaining_seconds} 秒后重试",
            )

        processing_count = await self.risk_log_service.count_processing_slider_logs()
        if processing_count < max_processing:
            return True, None

        if cooldown_seconds > 0:
            cooldown_until = now + cooldown_seconds
            await self.setting_service.set_setting(
                REMOTE_COOLDOWN_UNTIL_KEY,
                str(cooldown_until),
                "远程过滑块调用冷却截止时间戳",
            )
            return (
                False,
                f"处理中滑块任务已达上限（{processing_count}/{max_processing}），"
                f"远程调用已拒绝并进入 {cooldown_seconds} 秒冷却",
            )

        return (
            False,
            f"处理中滑块任务已达上限（{processing_count}/{max_processing}），远程调用已拒绝",
        )

    async def _get_settings(self) -> dict[str, str]:
        """一次查询读取准入判断需要的设置。"""
        keys = (
            REMOTE_PROCESSING_MAX_KEY,
            REMOTE_COOLDOWN_SECONDS_KEY,
            REMOTE_COOLDOWN_UNTIL_KEY,
        )
        rows = (
            await self.session.execute(
                select(SystemSetting).where(SystemSetting.key.in_(keys))
            )
        ).scalars().all()
        return {row.key: row.value or "" for row in rows}

    @staticmethod
    def _parse_timestamp(value: object) -> float:
        """解析冷却截止时间戳，非法值按未冷却处理。"""
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return parsed if math.isfinite(parsed) and parsed >= 0 else 0.0
