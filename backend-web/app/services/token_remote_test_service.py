"""
远程 Token 配置测试服务。

功能：
1. 为系统设置和个人设置提供相同的连通性测试
2. 使用空 Cookie 测试，不保存配置
3. 按调用用户记录测试结果和风控日志
"""
from __future__ import annotations

from loguru import logger

from common.models.user import User
from common.schemas.common import ApiResponse
from common.schemas.system_setting import RemoteTokenTestRequest
from common.services.remote_token_api import (
    is_remote_token_empty_cookies_message,
    request_remote_xianyu_token,
    validate_remote_token_settings,
)
from common.services.remote_token_risk_log_service import record_remote_token_risk_log


async def test_token_remote_settings(
    payload: RemoteTokenTestRequest,
    current_user: User,
    *,
    scene: str,
) -> ApiResponse:
    """测试地址与秘钥，返回统一响应并记录当前用户的测试结果。

    Args:
        payload: 待测试的远程 URL 和秘钥。
        current_user: 已通过认证的当前用户。
        scene: 测试入口中文名称，如系统设置、个人设置。
    Returns:
        测试成功或失败的统一业务响应；空 Cookie 校验通过时不返回 Token。
    """
    error_message = validate_remote_token_settings(
        payload.remote_url,
        payload.remote_secret_key,
    )
    if error_message:
        return ApiResponse(success=False, code=40001, message=error_message)

    logger.info(
        "远程Token接口测试开始：owner_id={} scene={} method=POST url={} headers={} body={}",
        current_user.id,
        scene,
        payload.remote_url,
        {"X-API-Key": payload.remote_secret_key},
        {"type": "xianyu_token", "data": {"cookies": ""}},
    )
    try:
        result = await request_remote_xianyu_token(
            payload.remote_url,
            payload.remote_secret_key,
            timeout_seconds=30,
        )
    except Exception as exc:  # noqa: BLE001 - 测试入口须将远程异常记录并返回统一中文提示。
        logger.opt(exception=exc).error(
            "远程Token接口测试异常：owner_id={} scene={} method=POST url={} exception={}: {}",
            current_user.id, scene, payload.remote_url, type(exc).__name__, exc,
        )
        await record_remote_token_risk_log(
            account_identifier=f"{scene}远程接口测试",
            success=False,
            message=f"{type(exc).__name__}: {exc}",
            owner_id=current_user.id,
            call_user=current_user.username,
            event_description=f"{scene}测试远程Token接口",
        )
        return ApiResponse(
            success=False, code=40001,
            message=f"远程接口测试失败：{type(exc).__name__}: {exc}",
        )

    # 测试只传空 Cookie：仅 Cookie 为空的参数校验错误表示地址与秘钥已通过。
    connectivity_only = (
        not result.success and 200 <= result.status_code < 300
        and is_remote_token_empty_cookies_message(result.message)
        and isinstance(result.response_json, dict)
        and result.response_json.get("success") is False
    )
    logger.info(
        "远程Token接口测试结果：owner_id={} scene={} result={}",
        current_user.id, scene, result,
    )
    await record_remote_token_risk_log(
        account_identifier=f"{scene}远程接口测试",
        success=result.success or connectivity_only,
        message=result.message,
        api_mode=result.api_mode,
        status_code=result.status_code,
        duration_seconds=result.duration_seconds,
        owner_id=current_user.id,
        call_user=current_user.username,
        event_description=(
            f"{scene}测试远程Token接口：地址与秘钥校验通过，因测试只传空Cookie未取Token"
            if connectivity_only else f"{scene}测试远程Token接口"
        ),
    )
    if not result.success and not connectivity_only:
        return ApiResponse(
            success=False, code=40001,
            message=f"远程接口返回：{result.message or '未返回错误说明'}",
        )
    return ApiResponse(
        success=True,
        message="远程接口连通性测试成功，请点击保存" if connectivity_only else "远程接口测试成功",
        data={
            "token": result.token,
            "device_id": result.device_id,
            "api_mode": result.api_mode,
        },
    )
