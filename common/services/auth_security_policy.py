"""认证安全设置公共策略：即时读取邮箱和 IP 配置，校验并规范化禁止 IP 列表。"""
from __future__ import annotations

import asyncio
import ipaddress
import re
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.system_setting import SystemSetting
from common.services.email_domain_policy import (
    EMAIL_DOMAIN_ALLOW_KEY,
    EMAIL_DOMAIN_DEFAULTS,
    EMAIL_DOMAIN_DENY_KEY,
    EMAIL_DOMAIN_MESSAGE_KEY,
    normalize_policy_setting,
    normalize_suffixes,
)

AUTH_SECURITY_GROUP = 'security'
AUTH_DENIED_IPS_KEY = 'auth.denied_ips'
DEFAULT_IP_DENIED_MESSAGE = '该 IP 不允许登录或注册，请联系管理员'
MAX_DENIED_IPS_LENGTH = 60000
AUTH_COMMON_SUFFIXES_KEY = 'auth.common_email_suffixes'
AUTH_FREQUENCY_KEYS = {minutes: f'auth.frequency_{minutes}m' for minutes in (1, 5, 10)}
AUTH_FREQUENCY_KEYS.update({hours * 60: f'auth.frequency_{hours}h' for hours in (1, 5, 10, 24)})
MAX_SECURITY_FREQUENCY = 9007199254740991
AUTH_SECURITY_DEFAULTS = {
    **EMAIL_DOMAIN_DEFAULTS,
    AUTH_DENIED_IPS_KEY: ('', '禁止注册和登录的 IP 列表（英文逗号分隔，支持完整地址和地址片段）'),
    AUTH_COMMON_SUFFIXES_KEY: ('', '常见邮箱后缀，仅豁免自动后缀封禁，不豁免IP或管理员原有禁止项'),
    **{key: ('0', f'{str(minutes) + "分钟" if minutes < 60 else str(minutes // 60) + "小时"}安全频率阈值，0关闭，大于等于阈值判定违规')
       for minutes, key in AUTH_FREQUENCY_KEYS.items()},
}
AUTH_SECURITY_FIELDS = {
    'email_allowed_suffixes': EMAIL_DOMAIN_ALLOW_KEY,
    'email_denied_suffixes': EMAIL_DOMAIN_DENY_KEY,
    'email_denied_message': EMAIL_DOMAIN_MESSAGE_KEY,
    'denied_ips': AUTH_DENIED_IPS_KEY,
    'common_email_suffixes': AUTH_COMMON_SUFFIXES_KEY,
    **{key.removeprefix('auth.'): key for key in AUTH_FREQUENCY_KEYS.values()},
}


class AuthIPRejected(ValueError):
    """客户端 IP 命中安全禁止列表，所有认证入口使用统一业务错误码。"""

    code = 40001

    def __init__(self, message: str):
        """保存原始禁止提示，并预留计数取消信号供入口在完成失败审计后传播。"""
        super().__init__(message)
        self.cancellation: asyncio.CancelledError | None = None


def normalize_denied_ips(raw_value: str) -> str:
    """校验英文逗号分隔的 IP 或片段，规范完整 IPv4/IPv6、去重并返回列表文本。"""
    if not isinstance(raw_value, str):
        raise ValueError('禁止 IP 列表必须为文本')  # noqa: TRY004 - 统一设置接口使用ValueError返回中文业务拒绝
    if len(raw_value) > MAX_DENIED_IPS_LENGTH:
        raise ValueError(f'禁止 IP 列表不能超过{MAX_DENIED_IPS_LENGTH}字符')
    if not raw_value.strip():
        return ''
    if '，' in raw_value:
        raise ValueError('禁止 IP 列表必须使用英文逗号分隔，不能使用中文逗号')
    entries = {}
    for item in raw_value.split(','):
        value = item.strip().lower()
        if not value:
            raise ValueError('禁止 IP 列表不能包含空项，请使用英文逗号分隔')
        if '*' in value or '/' in value:
            raise ValueError('禁止 IP 列表不支持 * 通配符或 CIDR，请填写地址或地址片段')
        if not re.fullmatch(r'[0-9a-f:.]+', value):
            raise ValueError('禁止 IP 列表包含非法字符，只支持 IPv4、IPv6 地址及地址片段')
        try:
            value = str(ipaddress.ip_address(value))
        except ValueError:
            # 片段按客户端规范地址包含匹配，不做网段或通配符解释。
            if len(value) > 45 or ':::' in value or value.count('::') > 1:
                raise ValueError('禁止 IP 列表中的地址或片段格式不正确')
            if ':' not in value and '.' not in value:
                if len(value) > 4:
                    raise ValueError('禁止 IP 列表中的地址片段格式不正确')
            elif ':' not in value:
                octets = value.split('.')
                if '..' in value or value.count('.') > 3 or any(
                    part and (not part.isdecimal() or len(part) > 3 or int(part) > 255)
                    for part in octets
                ) or (len(octets) == 4 and all(octets)):
                    raise ValueError('禁止 IP 列表中的 IPv4 地址或片段格式不正确')
            else:
                segments = value.split(':')
                if len(segments) > 8 or any(
                    len(part) > 4 for part in segments if '.' not in part
                ):
                    raise ValueError('禁止 IP 列表中的 IPv6 地址或片段格式不正确')
                if '.' in value:
                    raise ValueError('IPv6 地址片段必须按规范格式填写十六进制内容，不能包含点分十进制')
                if any(part and not re.fullmatch(r'[0-9a-f]{1,4}', part) for part in segments):
                    raise ValueError('禁止 IP 列表中的 IPv6 地址或片段格式不正确')
        entries[value] = None
    normalized = ','.join(entries)
    if len(normalized) > MAX_DENIED_IPS_LENGTH:
        raise ValueError(f'规范化后的禁止 IP 列表不能超过{MAX_DENIED_IPS_LENGTH}字符')
    return normalized


def normalize_security_setting(key: str, value: str) -> str:
    """校验一个安全设置值；邮箱与共享提示沿用原规则，IP 使用公共规范化。"""
    if key in AUTH_FREQUENCY_KEYS.values():
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,16}', value) or int(value) > MAX_SECURITY_FREQUENCY:
            raise ValueError('安全频率必须为0至9007199254740991的非负整数，0表示关闭')
        return str(int(value))
    if not isinstance(value, str):
        raise ValueError('安全配置列表和提示语必须为文本')
    if key == AUTH_COMMON_SUFFIXES_KEY:
        return normalize_suffixes(value)
    return normalize_denied_ips(value) if key == AUTH_DENIED_IPS_KEY else normalize_policy_setting(key, value)


def normalize_security_updates(current: Mapping[str, str], updates: Mapping[str, str]) -> dict[str, str]:
    """按数据库键校验安全组完整目标状态，只返回本次提交字段，避免省略值被覆盖。"""
    target = {key: current.get(key, default[0]) for key, default in AUTH_SECURITY_DEFAULTS.items()}
    target.update(updates)
    normalized = {key: normalize_security_setting(key, value) for key, value in target.items()}
    return {key: normalized[key] for key in updates}


async def load_policy_settings(session: AsyncSession) -> dict[str, str]:
    """读取数据库当前有效安全配置，不缓存、不解密普通提示语，不提交请求事务。"""
    rows = await session.execute(select(SystemSetting.key, SystemSetting.value).where(
        SystemSetting.key.in_(tuple(AUTH_SECURITY_DEFAULTS))
    ))
    return dict(rows.all())


def check_ip_policy(ip: str | None, settings: Mapping[str, str]) -> None:
    """按公共客户端地址的规范格式逐项包含匹配；未知地址保持空值，不补造 IP。"""
    if not isinstance(ip, str) or not ip.strip() or '%' in ip:
        return
    try:
        normalized_ip = str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return
    try:
        denied = normalize_denied_ips(settings.get(AUTH_DENIED_IPS_KEY, ''))
    except ValueError as exc:
        raise AuthIPRejected('禁止 IP 列表配置无效，请管理员修正后重试') from exc
    if denied and any(entry in normalized_ip for entry in denied.split(',')):
        message = settings.get(EMAIL_DOMAIN_MESSAGE_KEY, '')
        raise AuthIPRejected(message if message.strip() else DEFAULT_IP_DENIED_MESSAGE)


async def enforce_ip_policy(session: AsyncSession, ip: str | None) -> None:
    """认证入口共用 IP 禁止检查；读取当前数据库值，命中时抛出 AuthIPRejected。"""
    check_ip_policy(ip, await load_policy_settings(session))
