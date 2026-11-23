"""注册与登录共用的邮箱后缀策略：配置规范化、即时读取及完整域名匹配。"""
from __future__ import annotations

from collections.abc import Mapping
import ipaddress

import idna
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.system_setting import SystemSetting
from common.utils.email_utils import normalize_email_address

EMAIL_DOMAIN_ALLOW_KEY = "auth.email_allowed_suffixes"
EMAIL_DOMAIN_DENY_KEY = "auth.email_denied_suffixes"
EMAIL_DOMAIN_MESSAGE_KEY = "auth.email_denied_message"
DEFAULT_EMAIL_DOMAIN_MESSAGE = "该邮箱后缀不允许登录或注册，请更换邮箱"
MAX_SUFFIX_LIST_LENGTH = 60000
MAX_DENIAL_MESSAGE_LENGTH = 500
EMAIL_DOMAIN_DEFAULTS = {
    EMAIL_DOMAIN_ALLOW_KEY: ("", "允许注册和登录的邮箱后缀（英文逗号分隔，留空不限制）"),
    EMAIL_DOMAIN_DENY_KEY: ("", "禁止注册和登录的邮箱后缀（英文逗号分隔，优先于允许名单）"),
    EMAIL_DOMAIN_MESSAGE_KEY: ("", "邮箱后缀被拒绝时的普通文本提示，留空使用默认提示"),
}


class EmailDomainRejected(ValueError):
    """邮箱格式或后缀规则导致的业务拒绝；响应使用统一业务码。"""

    code = 40001


def normalize_domain(value: str) -> str:
    """将单个域名按 IDNA 转换为小写 ASCII；非法域名抛出 ValueError。"""
    if not value or value.endswith('.') or any(char.isspace() for char in value):
        raise ValueError("邮箱后缀必须是完整域名，不能包含空白或末尾句点")
    try:
        domain = idna.encode(value, uts46=True, std3_rules=True).decode('ascii').lower()
    except idna.IDNAError as exc:
        raise ValueError("邮箱后缀格式不正确，请填写 qq.com 等完整域名") from exc
    if len(domain) > 253 or '.' not in domain or domain.endswith('.'):
        raise ValueError("邮箱后缀必须是长度不超过253字符的完整域名")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        # 与注册邮箱格式校验保持一致，拒绝纯数字顶级域等无法用于邮箱的域名。
        _, error = normalize_email_address(f"x@{domain}")
        if error:
            raise ValueError("邮箱后缀不是有效的邮箱域名，请填写 qq.com 等完整域名")
        return domain
    raise ValueError("邮箱后缀不能填写 IP 地址")


def normalize_suffixes(raw_value: str) -> str:
    """校验英文逗号分隔的后缀，去空白、前导 @、大小写及重复项；返回规范文本。"""
    if len(raw_value) > MAX_SUFFIX_LIST_LENGTH:
        raise ValueError(f"邮箱后缀列表不能超过{MAX_SUFFIX_LIST_LENGTH}字符")
    if not raw_value.strip():
        return ""
    domains: dict[str, None] = {}
    for item in raw_value.split(','):
        value = item.strip()
        if value.startswith('@'):
            value = value[1:]
        if not value:
            raise ValueError("邮箱后缀不能包含空项，请使用英文逗号分隔")
        domains[normalize_domain(value)] = None
    result = ','.join(domains)
    if len(result) > MAX_SUFFIX_LIST_LENGTH:
        raise ValueError(f"规范化后的邮箱后缀列表不能超过{MAX_SUFFIX_LIST_LENGTH}字符")
    return result


def normalize_policy_setting(key: str, value: str) -> str:
    """校验一个后缀配置值；提示语按原始普通文本保留，非法值抛出 ValueError。"""
    if key in {EMAIL_DOMAIN_ALLOW_KEY, EMAIL_DOMAIN_DENY_KEY}:
        return normalize_suffixes(value)
    if key == EMAIL_DOMAIN_MESSAGE_KEY and len(value) > MAX_DENIAL_MESSAGE_LENGTH:
        raise ValueError(f"禁止提示语不能超过{MAX_DENIAL_MESSAGE_LENGTH}字符")
    return value


def check_email_domain(email: str, settings: Mapping[str, str]) -> None:
    """校验邮箱格式并精确匹配最后一个 @ 后的域名；拒绝时抛出业务错误。"""
    normalized, error = normalize_email_address(email)
    if error or not normalized:
        raise EmailDomainRejected(error or "邮箱地址格式不正确")
    try:
        domain = normalize_domain(normalized.rsplit('@', 1)[1])
        denied = set(normalize_suffixes(settings.get(EMAIL_DOMAIN_DENY_KEY, '')).split(',')) - {''}
        allowed = set(normalize_suffixes(settings.get(EMAIL_DOMAIN_ALLOW_KEY, '')).split(',')) - {''}
    except ValueError as exc:
        # 历史数据库中若存在旧的非法配置，给出管理员可理解的业务错误，避免认证入口返回模糊的服务异常。
        raise EmailDomainRejected("邮箱后缀配置无效，请管理员修正后重试") from exc
    if domain in denied or (allowed and domain not in allowed):
        message = settings.get(EMAIL_DOMAIN_MESSAGE_KEY, '')
        raise EmailDomainRejected(message if message.strip() else DEFAULT_EMAIL_DOMAIN_MESSAGE)


async def enforce_email_domain(
    session: AsyncSession, email: str, *, bound_email: str | None = None,
) -> None:
    """读取当前策略，校验请求邮箱及已匹配账号的绑定邮箱；拒绝时抛出业务错误。

    Args:
        session: 当前请求的数据库会话。
        email: 请求使用的邮箱。
        bound_email: 查询命中的账号绑定邮箱，防止数据库宽松字符比较绕过后缀规则。
    Returns:
        无返回值，不缓存配置或修改历史记录。
    """
    rows = await session.execute(
        select(SystemSetting.key, SystemSetting.value).where(
            SystemSetting.key.in_(tuple(EMAIL_DOMAIN_DEFAULTS))
        )
    )
    settings = dict(rows.all())
    check_email_domain(email, settings)
    if bound_email and bound_email != email:
        check_email_domain(bound_email, settings)
