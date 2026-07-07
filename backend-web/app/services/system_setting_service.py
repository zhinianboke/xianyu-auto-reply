"""
系统设置服务

功能：
1. 系统设置CRUD操作
2. 敏感设置过滤
3. 键值对存储和查询
4. XSS防护
"""
from __future__ import annotations

from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.system_setting import SystemSetting
from common.utils.text_utils import escape_xss

SENSITIVE_KEYS = {"admin_password_hash"}

DEFAULT_DISCLAIMER_CONTENT = (
    "数据存储说明\n"
    "1. 本系统在运行过程中，为保障服务正常运行，会存储用户账号密码、登录 Cookie、商品信息、卡券信息等业务数据。\n"
    "2. 上述数据仅用于系统功能运行、自动化处理和业务管理，不作为其他用途。\n"
    "3. 请您自行确认服务器环境、账号权限和数据保管措施的安全性。\n\n"
    "用户须知\n"
    "1. 用户应确保使用本系统的行为符合相关平台规则和法律法规。\n"
    "2. 因用户自身违规操作、账号共享、密码泄露、服务器安全问题导致的损失，由用户自行承担。\n"
    "3. 建议用户定期备份重要数据，因系统故障、第三方平台变更、不可抗力等导致的异常或损失，本系统不承担责任。\n"
    "4. 本系统依赖第三方平台接口和网络环境，无法保证服务始终连续、稳定、无中断。\n\n"
    "隐私与风险提示\n"
    "1. 请勿在未充分评估风险的情况下接入生产环境或敏感账号。\n"
    "2. 使用本系统即表示您已充分理解并接受相关风险，并愿意自行承担相应责任。"
)

DEFAULT_LOGIN_SYSTEM_TITLE = "高效专业的\n闲鱼自动化管理平台"
DEFAULT_LOGIN_SYSTEM_DESCRIPTION = "自动回复、智能客服、订单管理、数据分析，一站式解决闲鱼运营难题"
DEFAULT_AUTH_FOOTER_AD_HTML = "© 2026 划算云服务器 ·<a href=\"http://www.hsykj.com\" target=\"_BLANK\">www.hsykj.com</a>"

DEFAULT_SYSTEM_SETTINGS: dict[str, tuple[str, str | None]] = {
    "disclaimer.title": ("免责声明", "系统免责声明标题"),
    "disclaimer.content": (DEFAULT_DISCLAIMER_CONTENT, "系统免责声明正文"),
    "disclaimer.checkbox_text": ("我已阅读并同意以上免责声明", "免责声明勾选提示文案"),
    "disclaimer.agree_button_text": ("同意并继续", "免责声明同意按钮文案"),
    "disclaimer.disagree_button_text": ("不同意", "免责声明不同意按钮文案"),
    "login.system_name": ("闲鱼管理系统", "登录页系统名称"),
    "login.system_title": (DEFAULT_LOGIN_SYSTEM_TITLE, "登录页系统标题"),
    "login.system_description": (DEFAULT_LOGIN_SYSTEM_DESCRIPTION, "登录页系统描述"),
    "auth.footer_ad_html": (DEFAULT_AUTH_FOOTER_AD_HTML, "登录页和注册页底部广告 HTML"),
    "theme.effect": ("solid", "系统主题效果（solid-纯色，gradient-炫彩）"),
    "theme.color_preset": ("ocean", "系统主题颜色预设"),
    "theme.font_family": ("system", "系统主题字体预设"),
    "log.retention_days": ("7", "日志保留天数（所有模块生效，修改后实时刷新各服务日志策略）"),
    "account.face_verify_timeout_disable": ("true", "人脸验证超时是否自动禁用账号"),
    # 代理设置：用于配置网络请求的代理 API URL 和启用开关
    # api_url 默认空字符串表示未配置；enabled 默认 false 表示不启用
    "proxy.api_url": ("", "代理 API 的 URL（可能较长，用于配置外部代理服务）"),
    "proxy.enabled": ("false", "是否启用代理（true/false）"),
    # 用户到期/续期设置
    # renew_month_price：续期一个月的价格（元），空表示未配置（续期功能不可用）
    # register_default_days：注册用户默认有效天数，空表示注册不设置到期日（永不过期）
    "user.renew_month_price": ("", "用户续期一个月的价格（元），空=未配置"),
    "user.register_default_days": ("", "注册用户默认有效天数（空=不设置到期日）"),
    # real_mouse 过滑块本地/远程排队权重（默认 1:1，多来源同时排队时按比例放行）
    "captcha.real_mouse_weight_local": ("1", "real_mouse过滑块本地排队权重"),
    "captcha.real_mouse_weight_remote": ("1", "real_mouse过滑块远程排队权重"),
}

# 不需要XSS转义的键（布尔值、数字等）
NO_ESCAPE_KEYS = {
    "registration_enabled",
    "show_default_login_info", 
    "login_captcha_enabled",
    "disclaimer.title",
    "disclaimer.content",
    "disclaimer.checkbox_text",
    "disclaimer.agree_button_text",
    "disclaimer.disagree_button_text",
    "login.system_name",
    "login.system_title",
    "login.system_description",
    "auth.footer_ad_html",
    "theme.effect",
    "theme.color_preset",
    "theme.font_family",
    "navigation.hidden_menu_keys",
    "smtp_port",
    "smtp_use_tls",
    "smtp_use_ssl",
    "distribution.fee_type",
    "distribution.fee_rate",
    "alipay.app_id",
    "alipay.private_key",
    "alipay.alipay_public_key",
    "alipay.gateway_url",
    "alipay.notify_url",
    "ad_price.carousel",
    "ad_price.text",
    "withdraw.notify_email",
    "withdraw.min_amount",
    "log.retention_days",
    "account.face_verify_timeout_disable",
    # 用户到期/续期设置：均为数字字符串，无需 XSS 转义
    "user.renew_month_price",
    "user.register_default_days",
    # 代理设置：URL 含 :、/、?、&、= 等字符不能被 XSS 转义；布尔字符串"true"/"false"也无需转义
    "proxy.api_url",
    "proxy.enabled",
    # 远程过滑块配置：URL 含 :// 等字符、秘钥为随机串，均不能被 XSS 转义
    "captcha.remote_service_url",
    "captcha.remote_secret_key",
    # 是否传递账号Cookie：布尔字符串"true"/"false"，无需转义
    "captcha.remote_pass_cookies",
    # real_mouse 排队权重：数字字符串，无需 XSS 转义
    "captcha.real_mouse_weight_local",
    "captcha.real_mouse_weight_remote",
}


class SystemSettingService:
    """Provides CRUD helpers for global system settings."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_default_settings(self) -> None:
        existing_stmt = select(SystemSetting.key).where(SystemSetting.key.in_(tuple(DEFAULT_SYSTEM_SETTINGS.keys())))
        existing_result = await self.session.execute(existing_stmt)
        existing_keys = set(existing_result.scalars().all())

        missing_records = [
            SystemSetting(key=key, value=value, description=description)
            for key, (value, description) in DEFAULT_SYSTEM_SETTINGS.items()
            if key not in existing_keys
        ]

        if not missing_records:
            return

        self.session.add_all(missing_records)
        await self.session.commit()

    async def list_settings(self, include_sensitive: bool = False) -> Dict[str, str]:
        await self.ensure_default_settings()
        stmt = select(SystemSetting)
        result = await self.session.execute(stmt)
        settings: Dict[str, str] = {}
        for entry in result.scalars().all():
            if not include_sensitive and entry.key in SENSITIVE_KEYS:
                continue
            settings[entry.key] = entry.value
        return settings

    async def set_setting(self, key: str, value: str, description: str | None = None) -> None:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await self.session.execute(stmt)
        record = result.scalars().first()

        # 对非特殊键的值进行XSS转义
        safe_value = value if key in NO_ESCAPE_KEYS else escape_xss(value)
        safe_description = escape_xss(description) if description else None

        if record:
            record.value = safe_value
            if description is not None:
                record.description = safe_description
        else:
            record = SystemSetting(key=key, value=safe_value, description=safe_description)

        self.session.add(record)
        await self.session.commit()
