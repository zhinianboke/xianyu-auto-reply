"""
系统设置路由

功能：
1. 提供系统设置的读取与更新接口
2. 针对日志保留天数（log.retention_days）提供实时生效：
   - 保存成功后立即刷新当前 backend-web 进程的日志保留策略
   - 通过内部 HTTP 通知 websocket / scheduler 服务刷新
   - 未通知成功的服务由各自启动的自动同步任务兜底补齐
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from loguru import logger

from app.api import deps
from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.models.user import User, UserRole
from common.schemas.common import ApiResponse
from common.schemas.system_setting import SystemSettingUpdate
from app.services.system_setting_service import SENSITIVE_KEYS, SystemSettingService
from common.utils.logging_utils import update_log_retention
from common.utils.browser_utils import is_frozen

router = APIRouter(tags=["system_settings"])

# 日志保留天数的设置键，与前端保持一致
LOG_RETENTION_KEY = "log.retention_days"
PASSWORD_LOGIN_MODE_KEY = "password_login.mode"
PASSWORD_LOGIN_MODES = {"auto", "protocol", "browser"}

NON_ADMIN_ALLOWED_KEYS = {
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
    "distribution.fee_type",
    "distribution.fee_rate",
    "withdraw.min_amount",
    "runtime.is_exe_mode",
    # 普通用户需读取续期单价以在个人设置中计算续期总价
    "user.renew_month_price",
}


def _parse_log_retention_days(raw_value: str) -> tuple[int | None, str | None]:
    """解析日志保留天数输入，范围 1~365，返回 (天数, 错误提示)。"""
    value = str(raw_value or "").strip()
    if not value.isdigit():
        return None, "日志保留天数必须为1到365之间的整数"

    retention_days = int(value)
    if not (1 <= retention_days <= 365):
        return None, "日志保留天数必须为1到365之间的整数"
    return retention_days, None


# 布尔值字符串统一解析：代理开关等场景使用
_TRUE_VALUES = {"true", "1", "yes", "on"}


def _is_truthy(raw_value: str | None) -> bool:
    """把字符串形式的布尔值（'true'/'false'/'1'/'0' 等）统一解析为 bool。"""
    return str(raw_value or "").strip().lower() in _TRUE_VALUES


async def _validate_proxy_setting(
    key: str,
    new_value: str,
    service: SystemSettingService,
) -> str | None:
    """
    代理设置跨键校验：防止绕过前端直接 PUT 产生非法状态。

    - PUT proxy.enabled=true：要求数据库中 proxy.api_url 已非空
    - PUT proxy.api_url=''：要求当前 proxy.enabled 为 false，避免"开着代理但 URL 被清空"

    返回 None 表示校验通过，返回字符串表示错误信息。
    """
    if key not in ("proxy.enabled", "proxy.api_url"):
        return None

    # 读当前已保存的代理设置（仅用于读取另一个键的当前值）
    current_settings = await service.list_settings()

    if key == "proxy.enabled" and _is_truthy(new_value):
        current_api_url = str(current_settings.get("proxy.api_url") or "").strip()
        if not current_api_url:
            return "开启代理前请先填写代理 API 的 URL"

    if key == "proxy.api_url" and not str(new_value or "").strip():
        if _is_truthy(current_settings.get("proxy.enabled")):
            return "代理已启用，请先关闭代理再清空代理 API 的 URL"

    return None


async def _notify_log_retention_service(
    service_name: str,
    service_url: str,
    retention_days: int,
) -> dict:
    """通过内部 HTTP 接口通知目标服务刷新日志保留天数。"""
    if not service_url:
        return {
            "success": False,
            "message": f"{service_name}服务地址未配置，将由自动同步任务补齐",
        }

    try:
        response = await get_http_client().post(
            f"{service_url.rstrip('/')}/internal/logs/retention",
            json={"retention_days": retention_days},
        )
        success = bool(response.get("success"))
        default_msg = f"{service_name}服务刷新成功" if success else f"{service_name}服务刷新失败"
        return {
            "success": success,
            "message": str(response.get("message") or default_msg),
        }
    except Exception as e:
        logger.error(f"通知{service_name}服务刷新日志保留天数失败: {e}")
        return {
            "success": False,
            "message": f"{service_name}服务刷新失败: {str(e)}，将由自动同步任务补齐",
        }


async def _refresh_log_retention_runtime(retention_days: int) -> dict:
    """刷新当前服务并广播通知其它服务刷新日志保留天数。"""
    settings = get_settings()
    local_updated = update_log_retention(retention_days)

    results = {
        "backend_web": {
            "success": True,
            "message": "backend-web服务已刷新" if local_updated else "backend-web服务无需变更",
        },
        "websocket": await _notify_log_retention_service(
            "WebSocket", settings.websocket_service_url, retention_days,
        ),
        "scheduler": await _notify_log_retention_service(
            "Scheduler", settings.scheduler_service_url, retention_days,
        ),
        "promotion_backend": {
            "success": True,
            "message": "返佣服务将通过自动同步任务应用最新日志保留天数",
        },
    }
    return results


@router.get("/public")
async def get_public_settings(
    service: SystemSettingService = Depends(deps.get_system_setting_service),
) -> dict[str, str]:
    """获取公开的系统设置（无需登录）"""
    all_settings = await service.list_settings()
    # 只返回公开的配置项
    public_keys = {
        "registration_enabled",
        "show_default_login_info",
        "login_captcha_enabled",
        "login.system_name",
        "login.system_title",
        "login.system_description",
        "auth.footer_ad_html",
        "theme.effect",
        "theme.color_preset",
        "theme.font_family",
        "runtime.is_exe_mode",
    }
    all_settings["runtime.is_exe_mode"] = "true" if is_frozen() else "false"
    return {k: v for k, v in all_settings.items() if k in public_keys}


@router.get("")
async def get_system_settings(
    current_user: User = Depends(deps.get_current_active_user),
    service: SystemSettingService = Depends(deps.get_system_setting_service),
) -> dict[str, str]:
    settings = await service.list_settings()
    settings["runtime.is_exe_mode"] = "true" if is_frozen() else "false"
    if current_user.role == UserRole.ADMIN:
        return settings
    return {key: value for key, value in settings.items() if key in NON_ADMIN_ALLOWED_KEYS}


@router.put("/{key}", response_model=ApiResponse)
async def update_system_setting(
    key: str,
    payload: SystemSettingUpdate,
    current_user: User = Depends(deps.get_current_admin_user),
    service: SystemSettingService = Depends(deps.get_system_setting_service),
) -> ApiResponse:
    if key in SENSITIVE_KEYS:
        return ApiResponse(success=False, message="该设置需要使用专用接口修改")

    setting_value = payload.value
    if key == PASSWORD_LOGIN_MODE_KEY:
        setting_value = str(payload.value or "").strip().lower()
        if setting_value not in PASSWORD_LOGIN_MODES:
            return ApiResponse(
                success=False,
                message="账号密码登录方式无效，请选择自动选择、协议登录或浏览器登录",
            )

    retention_days: int | None = None
    if key == LOG_RETENTION_KEY:
        retention_days, error_message = _parse_log_retention_days(setting_value)
        if error_message:
            return ApiResponse(success=False, message=error_message)

    # 代理设置跨键校验（开启代理必须已配置 URL；代理启用中不允许清空 URL）
    proxy_error = await _validate_proxy_setting(key, setting_value, service)
    if proxy_error:
        return ApiResponse(success=False, message=proxy_error)

    await service.set_setting(key, setting_value, payload.description)

    if retention_days is None:
        return ApiResponse(success=True, message="系统设置已更新")

    refresh_results = await _refresh_log_retention_runtime(retention_days)
    failed_services = [
        service_name
        for service_name, result in refresh_results.items()
        if not bool(result.get("success"))
    ]
    if failed_services:
        return ApiResponse(
            success=True,
            message="系统设置已更新，日志保留天数已生效，部分服务将由自动同步任务补齐",
            data={
                "retention_days": retention_days,
                "refresh_results": refresh_results,
                "pending_sync_services": failed_services,
            },
        )

    return ApiResponse(
        success=True,
        message="系统设置已更新，日志保留天数已实时生效",
        data={
            "retention_days": retention_days,
            "refresh_results": refresh_results,
            "pending_sync_services": [],
        },
    )


@router.post("/test-email", response_model=ApiResponse)
async def test_email_send(
    email: str,
    current_user: User = Depends(deps.get_current_admin_user),
) -> ApiResponse:
    """发送测试邮件"""
    from app.services.email_service import send_test_email
    
    success, message = await send_test_email(email)
    return ApiResponse(success=success, message=message)
