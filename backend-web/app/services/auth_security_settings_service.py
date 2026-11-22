"""管理员安全配置读写服务：邮箱三项和禁止 IP 整组校验，省略字段保留原值。"""
from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.system_setting_service import SystemSettingService
from common.services.auth_security_policy import (
    AUTH_SECURITY_DEFAULTS,
    AUTH_SECURITY_FIELDS,
    load_policy_settings,
    normalize_security_updates,
)


class AuthSecuritySettingsService:
    """安全设置专用服务，只操作四个安全键，不读取或覆盖 SMTP 配置。"""

    def __init__(self, session: AsyncSession):
        """使用当前请求会话与项目统一设置服务，不自行创建数据库连接。"""
        self.session = session
        self.settings = SystemSettingService(session)

    async def get_settings(self) -> dict[str, str]:
        """读取当前四项安全配置；返回接口字段名，提示语保持原始普通文本。"""
        current = await load_policy_settings(self.session)
        return {field: current.get(key, AUTH_SECURITY_DEFAULTS[key][0])
                for field, key in AUTH_SECURITY_FIELDS.items()}

    async def save_settings(self, updates: Mapping[str, str]) -> dict[str, str]:
        """整组校验后单事务保存本次提交的字段，省略保留、显式空字符串清空。

        Args:
            updates: API四个字段的部分或完整更新，不接受空值、数字及未知字段。
        Returns:
            保存后的完整四项配置，使用规范化列表和原始禁止提示语。
        """
        if set(updates) - set(AUTH_SECURITY_FIELDS):
            raise ValueError('安全设置包含未知字段')
        if any(not isinstance(value, str) for value in updates.values()):
            raise ValueError('安全设置必须为文本，清空时请提交空字符串')
        current = await load_policy_settings(self.session)
        submitted = {AUTH_SECURITY_FIELDS[field]: value for field, value in updates.items()}
        normalized = normalize_security_updates(current, submitted)
        # 仅写提交字段，避免省略字段在并发管理员保存时覆盖另一组或其他新值。
        changes = {
            AUTH_SECURITY_FIELDS[field]: (
                normalized[AUTH_SECURITY_FIELDS[field]], AUTH_SECURITY_DEFAULTS[AUTH_SECURITY_FIELDS[field]][1],
            ) for field in updates
        }
        await self.settings.set_settings(changes)
        return await self.get_settings()
