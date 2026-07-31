"""
远程 Token 获取风控日志记录服务。

功能：
1. 在调用远程 Token 接口后写入 xy_risk_control_logs
2. 记录远程取 Token 成功或失败状态
3. 避免在各业务流程中重复拼装风控日志字段
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from common.db.compat import db_manager
from common.db.session import async_session_maker
from common.models.risk_control_log import XYRiskControlLog
from common.models.xy_account import XYAccount


REMOTE_TOKEN_EVENT_TYPE = "remote_token"

# 远程回退场景下，风控日志事件描述使用的远程接口结果文案
REMOTE_OUTCOME_SUCCESS = "远程接口获取Token成功"
REMOTE_OUTCOME_FAILED = "远程接口获取Token失败"


def build_remote_fallback_event_description(
    *,
    local_failure_reason: str,
    remote_outcome: str,
    scene: str = "",
) -> str:
    """构造「本地接口失败后回退远程接口」的风控日志事件描述。

    事件描述同时说明本地网页接口返回了什么、远程接口最终是否成功，
    避免只写本地失败原因导致与处理结果、处理状态看起来互相矛盾。

    Args:
        local_failure_reason: 本地网页接口失败原因（如「未返回有效Token」）。
        remote_outcome: 远程接口结果文案（如「远程接口获取Token成功」）。
        scene: 场景前缀，如「重取滑块验证链接时」；普通取 Token 场景传空。
    Returns:
        用于风控日志 event_description 的中文事件描述。
    """
    scene_text = str(scene or "").strip()
    reason = str(local_failure_reason or "").strip() or "未说明原因"
    outcome = str(remote_outcome or "").strip() or "远程接口结果未知"
    return f"{scene_text}本地网页Token接口返回：{reason}；{outcome}"


def build_remote_token_log_result(
    *,
    success: bool,
    message: str,
    api_mode: str = "",
    status_code: int = 0,
    duration_seconds: float = 0,
    local_duration_seconds: float = 0,
) -> str:
    """构造远程 Token 获取结果文案。

    取 Token 是「先本地网页接口、失败后再远程接口」两段串行流程，耗时分开记录，
    便于排查究竟是本地慢还是远程慢；两段都有时额外给出总耗时。

    Args:
        success: 远程接口业务是否成功。
        message: 远程接口返回或本地解析出的结果说明。
        api_mode: 远程接口返回的实际 Token 接口。
        status_code: HTTP 状态码。
        duration_seconds: 远程接口耗时。
        local_duration_seconds: 本地网页接口耗时（含令牌过期重试）。
    Returns:
        用于风控日志 processing_result 的中文结果文案。
    """
    status_text = "成功" if success else "失败"
    parts = [f"远程接口获取Token{status_text}"]
    if message:
        parts.append(f"说明：{message}")
    if api_mode:
        parts.append(f"实际接口：{api_mode}")
    if status_code:
        parts.append(f"HTTP状态：{status_code}")
    if local_duration_seconds:
        parts.append(f"本地接口耗时：{local_duration_seconds:.2f}秒")
    if duration_seconds:
        parts.append(f"远程接口耗时：{duration_seconds:.2f}秒")
    if local_duration_seconds and duration_seconds:
        parts.append(f"总耗时：{local_duration_seconds + duration_seconds:.2f}秒")
    return "；".join(parts)


async def record_remote_token_risk_log(
    *,
    account_identifier: str,
    success: bool,
    message: str,
    api_mode: str = "",
    status_code: int = 0,
    duration_seconds: float = 0,
    local_duration_seconds: float = 0,
    owner_id: int | None = None,
    call_user: str | None = None,
    event_description: str = "远程接口获取闲鱼Token",
) -> None:
    """异步记录远程 Token 获取风控日志。

    Args:
        account_identifier: 账号标识；系统测试场景可传入固定说明。
        success: 是否成功。
        message: 结果说明。
        api_mode: 实际 Token 接口。
        status_code: HTTP 状态码。
        duration_seconds: 远程接口耗时。
        local_duration_seconds: 本地网页接口耗时；无本地调用时传 0。
        owner_id: 所属用户 ID；账号不存在时使用该值。
        call_user: 调用用户说明。
        event_description: 事件描述。
    Returns:
        无返回值；写入失败只记录日志，不影响取 Token 主流程。
    """
    safe_account_identifier = str(account_identifier or "").strip()[:80] or "remote_token"
    processing_result = build_remote_token_log_result(
        success=success,
        message=message,
        api_mode=api_mode,
        status_code=status_code,
        duration_seconds=duration_seconds,
        local_duration_seconds=local_duration_seconds,
    )
    try:
        async with async_session_maker() as session:
            account_row = None
            if safe_account_identifier != "remote_token":
                account_row = (
                    await session.execute(
                        select(XYAccount.id, XYAccount.owner_id)
                        .where(XYAccount.account_id == safe_account_identifier)
                        .limit(1)
                    )
                ).first()

            log = XYRiskControlLog(
                owner_id=account_row.owner_id if account_row else owner_id,
                account_pk=account_row.id if account_row else None,
                account_identifier=safe_account_identifier,
                event_type=REMOTE_TOKEN_EVENT_TYPE,
                event_description=event_description,
                processing_status="success" if success else "failed",
                processing_result=processing_result,
                call_type="remote",
                call_user=call_user,
                error_message=None if success else (message or "远程接口获取Token失败"),
            )
            session.add(log)
            await session.commit()
    except Exception as exc:
        logger.error(
            f"记录远程Token风控日志失败: account={safe_account_identifier}, "
            f"success={success}, error={type(exc).__name__}: {exc}"
        )


def record_remote_token_risk_log_sync(
    *,
    account_identifier: str,
    success: bool,
    message: str,
    api_mode: str = "",
    status_code: int = 0,
    duration_seconds: float = 0,
    local_duration_seconds: float = 0,
    event_description: str = "远程接口获取闲鱼Token",
) -> None:
    """同步记录远程 Token 获取风控日志。

    Args:
        account_identifier: 账号标识。
        success: 是否成功。
        message: 结果说明。
        api_mode: 实际 Token 接口。
        status_code: HTTP 状态码。
        duration_seconds: 远程接口耗时。
        local_duration_seconds: 本地网页接口耗时；无本地调用时传 0。
        event_description: 事件描述。
    Returns:
        无返回值；写入失败只记录日志，不影响取 Token 主流程。
    """
    safe_account_identifier = str(account_identifier or "").strip()[:80] or "remote_token"
    processing_result = build_remote_token_log_result(
        success=success,
        message=message,
        api_mode=api_mode,
        status_code=status_code,
        duration_seconds=duration_seconds,
        local_duration_seconds=local_duration_seconds,
    )
    try:
        log_id = db_manager.add_risk_control_log(
            cookie_id=safe_account_identifier,
            event_type=REMOTE_TOKEN_EVENT_TYPE,
            event_description=event_description,
            processing_status="success" if success else "failed",
            call_type="remote",
        )
        if log_id:
            db_manager.update_risk_control_log(
                log_id=log_id,
                processing_result=processing_result,
                error_message=None if success else (message or "远程接口获取Token失败"),
            )
    except Exception as exc:
        logger.error(
            f"同步记录远程Token风控日志失败: account={safe_account_identifier}, "
            f"success={success}, error={type(exc).__name__}: {exc}"
        )
