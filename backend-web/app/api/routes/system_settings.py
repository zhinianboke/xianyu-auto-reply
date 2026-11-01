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

from fastapi import APIRouter, Depends, Request
from loguru import logger

from app.api import deps
from app.services.email_service import send_test_email
from app.services.log_retention_service import refresh_log_retention_runtime
from app.services.system_setting_service import SENSITIVE_KEYS, SystemSettingService
from app.services.system_settings_email_service import validate_test_email_recipient
from app.services.system_settings_update_service import validate_system_settings_update
from app.services.token_remote_test_service import test_token_remote_settings
from common.models.user import User, UserRole
from common.schemas.common import ApiResponse
from common.schemas.system_setting import (
    RemotePasswordLoginTestRequest,
    RemoteTokenTestRequest,
    SystemSettingsBatchUpdate,
    SystemSettingUpdate,
)
from common.services.remote_password_login_api import (
    test_remote_password_login_interface,
    validate_remote_password_login_settings,
)
from common.utils.browser_utils import is_frozen
from common.utils.http_utils import get_client_ip

router = APIRouter(tags=["system_settings"])

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


async def _save_system_settings(
    updates: dict[str, tuple[str, str | None]],
    service: SystemSettingService,
) -> ApiResponse:
    """校验并在同一事务中保存系统设置，必要时刷新日志保留策略。"""
    try:
        values = {key: value for key, (value, _) in updates.items()}
        validated, error_message = await validate_system_settings_update(values, service)
        if error_message or validated is None:
            return ApiResponse(
                success=False,
                code=40001,
                message=error_message or "系统设置校验失败",
            )

        normalized_updates = {
            key: (value, updates[key][1]) for key, value in validated.values.items()
        }
        await service.set_settings(normalized_updates)
    except Exception as exc:  # noqa: BLE001 - 保存异常必须回滚并转换为统一业务响应。
        await service.rollback()
        logger.opt(exception=exc).error(
            "系统设置保存接口异常：keys={} exception_type={} exception={}",
            sorted(updates),
            type(exc).__name__,
            exc,
        )
        return ApiResponse(
            success=False,
            code=40001,
            message="系统设置保存失败，请稍后重试",
        )

    if validated.retention_days is None:
        return ApiResponse(success=True, message="系统设置已更新")

    refresh_results = await refresh_log_retention_runtime(validated.retention_days)
    failed_services = [
        service_name
        for service_name, result in refresh_results.items()
        if not bool(result.get("success"))
    ]
    message = (
        "系统设置已更新，日志保留天数已生效，部分服务将由自动同步任务补齐"
        if failed_services
        else "系统设置已更新，日志保留天数已实时生效"
    )
    return ApiResponse(
        success=True,
        message=message,
        data={
            "retention_days": validated.retention_days,
            "refresh_results": refresh_results,
            "pending_sync_services": failed_services,
        },
    )


@router.get("/public")
async def get_public_settings(
    service: SystemSettingService = Depends(deps.get_system_setting_service),  # noqa: B008
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
    current_user: User = Depends(deps.get_current_active_user),  # noqa: B008
    service: SystemSettingService = Depends(deps.get_system_setting_service),  # noqa: B008
) -> dict[str, str]:
    settings = await service.list_settings()
    settings["runtime.is_exe_mode"] = "true" if is_frozen() else "false"
    if current_user.role == UserRole.ADMIN:
        return settings
    return {key: value for key, value in settings.items() if key in NON_ADMIN_ALLOWED_KEYS}


@router.put("/batch", response_model=ApiResponse)
async def update_system_settings_batch(
    payload: SystemSettingsBatchUpdate,
    current_user: User = Depends(deps.get_current_admin_user),  # noqa: B008
    service: SystemSettingService = Depends(deps.get_system_setting_service),  # noqa: B008
) -> ApiResponse:
    """在同一事务中批量保存一个设置模块的全部字段。"""
    updates = {
        key: (setting.value, setting.description)
        for key, setting in payload.settings.items()
    }
    return await _save_system_settings(updates, service)


@router.put("/{key}", response_model=ApiResponse)
async def update_system_setting(
    key: str,
    payload: SystemSettingUpdate,
    current_user: User = Depends(deps.get_current_admin_user),  # noqa: B008
    service: SystemSettingService = Depends(deps.get_system_setting_service),  # noqa: B008
) -> ApiResponse:
    if key in SENSITIVE_KEYS:
        return ApiResponse(success=False, code=40001, message="该设置需要使用专用接口修改")
    return await _save_system_settings(
        {key: (payload.value, payload.description)},
        service,
    )


@router.post("/test-email", response_model=ApiResponse)
async def test_email_send(
    email: str,
    http_request: Request,
    current_user: User = Depends(deps.get_current_admin_user),  # noqa: B008
) -> ApiResponse:
    """发送测试邮件"""
    client_ip = get_client_ip(http_request)
    normalized_email, error_message = await validate_test_email_recipient(
        email,
        owner_id=current_user.id,
        client_ip=client_ip,
    )
    if error_message:
        return ApiResponse(success=False, code=40001, message=error_message)

    # 发送结果（成功/失败/配置缺失）由 email_service 统一写入邮件发送日志
    success, message = await send_test_email(
        normalized_email or "",
        owner_id=current_user.id,
        client_ip=client_ip,
    )
    return ApiResponse(success=success, code=200 if success else 40001, message=message)


@router.post("/test-token-remote", response_model=ApiResponse)
async def test_token_remote_interface(
    payload: RemoteTokenTestRequest,
    current_user: User = Depends(deps.get_current_admin_user),  # noqa: B008
) -> ApiResponse:
    """测试远程 Token 接口连通性与返回格式。"""
    return await test_token_remote_settings(payload, current_user, scene="系统设置")


@router.post("/test-password-login-remote", response_model=ApiResponse)
async def test_password_login_remote_interface(
    payload: RemotePasswordLoginTestRequest,
    current_user: User = Depends(deps.get_current_admin_user),  # noqa: B008
) -> ApiResponse:
    """测试协议登录远程接口（阿里滑块获取 x5sec）连通性与秘钥有效性。"""
    error_message = validate_remote_password_login_settings(
        payload.remote_url,
        payload.remote_secret_key,
    )
    if error_message:
        return ApiResponse(success=False, code=40001, message=error_message)

    try:
        result = await test_remote_password_login_interface(
            payload.remote_url,
            payload.remote_secret_key,
            timeout_seconds=15,
        )
    except Exception as exc:  # noqa: BLE001 - 远程测试入口必须将所有上游异常转换为可见业务错误。
        logger.error(f"测试协议登录远程接口异常: {type(exc).__name__}: {exc}")
        return ApiResponse(
            success=False,
            message=f"远程接口测试失败：{type(exc).__name__}: {exc}",
        )

    return ApiResponse(
        success=result.success,
        code=200 if result.success else 40001,
        message=result.message,
    )
