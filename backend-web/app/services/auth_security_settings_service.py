"""管理员安全配置读写：七档频率及名单原子校验，锁内版本防止旧表单覆盖自动封禁。"""
from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from common.services.auth_security_policy import (
    AUTH_FREQUENCY_KEYS, AUTH_SECURITY_DEFAULTS, AUTH_SECURITY_FIELDS,
    MAX_SECURITY_FREQUENCY, normalize_security_setting, normalize_security_updates,
)
from common.services.security_config_service import (
    load_security_values_locked, lock_security_task, save_security_values,
)


class AuthSecuritySettingsService:
    """只操作安全组，不读取、解密或覆盖SMTP配置；未提交字段保留。"""

    def __init__(self, session: AsyncSession):
        """使用当前请求会话与统一锁，不创建引擎或会话工厂。"""
        self.session = session

    async def get_settings(self) -> dict:
        """锁内读取一致的配置与版本；频率返回整数，提示语保持原始普通文本。"""
        task = await lock_security_task(self.session)
        current = await load_security_values_locked(self.session)
        result = {field: current.get(key, AUTH_SECURITY_DEFAULTS[key][0])
                  for field, key in AUTH_SECURITY_FIELDS.items()}
        for key in AUTH_FREQUENCY_KEYS.values():
            field = key.removeprefix('auth.')
            result[field] = int(normalize_security_setting(key, result[field]))
        result['config_version'] = str(task.config_version or 0)
        return result

    async def save_settings(self, updates: Mapping) -> dict:
        """校验整个目标后只保存提交字段；新客户端携带版本，旧客户端保留兼容。"""
        if set(updates) - set(AUTH_SECURITY_FIELDS) - {'config_version'}:
            raise ValueError('安全设置包含未知字段')
        submitted = {}
        for field, value in updates.items():
            if field == 'config_version':
                continue
            key = AUTH_SECURITY_FIELDS[field]
            if key in AUTH_FREQUENCY_KEYS.values():
                if type(value) is not int or not 0 <= value <= MAX_SECURITY_FREQUENCY:
                    raise ValueError('安全频率必须为0至9007199254740991的非负整数，0表示关闭')
                value = str(value)
            elif not isinstance(value, str):
                raise ValueError('安全设置名单和提示语必须为文本，清空请提交空字符串')
            submitted[key] = value
        task = await lock_security_task(self.session)
        if 'config_version' in updates and updates['config_version'] != str(task.config_version or 0):
            raise ValueError('安全配置已被后台检查或其他管理员更新，请重新加载后再保存')
        current = await load_security_values_locked(self.session)
        normalized = normalize_security_updates(current, submitted)
        await save_security_values(self.session, task, normalized)
        result = await self.get_settings()
        await self.session.commit()
        return result
