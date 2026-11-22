"""主系统登录兼容入口，注入当前系统的滑动验证码和设置读取服务。"""
from __future__ import annotations

from app.api.routes.geetest import check_geetest_verified
from app.services.system_setting_service import SystemSettingService
from common.services.login_flow_service import perform_login as common_perform_login


async def _load_settings(session):
    """按请求读取主系统当前登录配置，不缓存或吞掉数据库异常。"""
    return await SystemSettingService(session).list_settings()


async def perform_login(payload, ip, auth_service, session, login_log_service):
    """保持已有路由签名，三种登录方式共用公共认证流程。"""
    return await common_perform_login(
        payload, ip, auth_service, session, login_log_service,
        captcha_check=check_geetest_verified, settings_loader=_load_settings,
    )
