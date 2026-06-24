"""
外部账号 Cookie 同步接口

功能：
1. 提供给外部系统回传账号最新 Cookie 的接口（无需登录，凭分销秘钥校验身份）
2. 校验账号存在、分销秘钥有效且归属该账号所属用户后，仅更新账号 Cookie 到数据库
   （不重启账号 WebSocket 任务，避免打断实时连接；定时任务从数据库读取 Cookie 会自动用上最新值）

安全设计：
- 本接口不走登录态，鉴权依赖 secret_key（分销秘钥，32 位密码学随机字符，约 190bit 熵，
  无法被暴力枚举）。
- secret_key 必须属于该账号所属用户（owner），否则拒绝；即一个分销秘钥只能更新自己
  名下账号的 Cookie，限制越权影响面。若秘钥对应用户为管理员，则不限账号归属，可更新任意账号。
- Cookie 内容做长度上限与格式/归属校验（解析 unb，必须与目标账号一致），防止"瞎传数据"
  把无关或垃圾 Cookie 写入账号导致串号或账号损坏。
- 记录审计日志（客户端 IP、账号、Cookie 长度、秘钥仅记录掩码），便于追溯；日志不落明文
  secret_key / Cookie。
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.account_service import AccountService
from common.models.user import User
from common.models.xy_account import XYAccount
from common.schemas.common import ApiResponse
from common.utils.auth_scope import is_admin_user
from common.utils.xianyu_utils import trans_cookies

router = APIRouter(prefix="/external/account-cookie", tags=["外部Cookie同步"])

# Cookie 字符串长度上限（xy_accounts.cookie 为 TEXT，约 64KB；正常闲鱼 Cookie 仅几 KB，
# 这里给 16KB 余量，超长一律拒绝，避免异常/恶意超大数据写入）
_MAX_COOKIE_LENGTH = 16384


def _mask_secret(secret: str) -> str:
    """秘钥掩码，仅保留首尾各 2 位用于日志追溯，避免明文落日志。"""
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


def _client_ip(request: Request) -> str:
    """获取客户端 IP（兼容反向代理 X-Forwarded-For）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


async def _notify_scheduler_clear_cooldown(account_id: str) -> None:
    """通知 scheduler 解除该账号的风控冷却（回传新 Cookie 后让账号立即恢复可用）。

    冷却态仅存在于 scheduler 进程内存中，需跨进程经内部接口触发解除；
    本调用失败不影响 Cookie 更新主流程，仅记录告警日志。
    """
    try:
        from app.core.config import get_settings
        from app.core.http_client import get_http_client

        settings = get_settings()
        url = f"{settings.scheduler_service_url}/internal/account-cooldown/clear"
        await get_http_client().post(url, json={"account_id": account_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[外部Cookie同步] 通知 scheduler 解除账号冷却失败（不影响 Cookie 更新）"
            f" account_id={account_id}: {exc}"
        )


class ExternalCookieSyncRequest(BaseModel):
    """外部回传账号 Cookie 请求"""

    account_id: str = Field(..., min_length=1, max_length=80, description="闲鱼账号ID")
    cookies: str = Field(..., min_length=1, max_length=_MAX_COOKIE_LENGTH, description="账号最新 Cookie 字符串")
    secret_key: str = Field(..., min_length=1, max_length=128, description="分销秘钥（须为该账号所属用户的分销秘钥）")


@router.post("/sync", response_model=ApiResponse)
async def sync_account_cookie(
    payload: ExternalCookieSyncRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(deps.get_db_session),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """外部系统回传账号 Cookie：校验账号、分销秘钥与 Cookie 归属后，仅更新 Cookie 到数据库。

    业务错误统一以 HTTP 200 + success=false 返回，由调用方据标志字段处理。
    """
    client_ip = _client_ip(request)
    account_id = (payload.account_id or "").strip()
    secret_key = (payload.secret_key or "").strip()
    cookies = (payload.cookies or "").strip()

    if not account_id or not secret_key or not cookies:
        logger.warning(f"[外部Cookie同步] 参数不完整 ip={client_ip} account_id={account_id}")
        return ApiResponse(success=False, message="参数不完整")

    # 1. 校验账号是否存在（全局，不区分所属用户）
    account = (
        await session.execute(select(XYAccount).where(XYAccount.account_id == account_id))
    ).scalar_one_or_none()
    if not account:
        logger.warning(f"[外部Cookie同步] 账号不存在 ip={client_ip} account_id={account_id}")
        return ApiResponse(success=False, message="账号不存在")

    # 2. 校验分销秘钥是否存在
    user = (
        await session.execute(select(User).where(User.secret_key == secret_key))
    ).scalar_one_or_none()
    if not user:
        logger.warning(
            f"[外部Cookie同步] 分销秘钥无效 ip={client_ip} account_id={account_id} "
            f"secret={_mask_secret(secret_key)}"
        )
        return ApiResponse(success=False, message="分销秘钥无效")

    # 3. 校验分销秘钥归属该账号所属用户（防止越权更新他人账号）；
    #    若秘钥对应用户为管理员，则不限制账号归属，可更新任意账号。
    if not is_admin_user(user) and (account.owner_id is None or user.id != account.owner_id):
        logger.warning(
            f"[外部Cookie同步] 秘钥与账号不匹配 ip={client_ip} account_id={account_id} "
            f"user={user.id} owner={account.owner_id}"
        )
        return ApiResponse(success=False, message="分销秘钥与账号不匹配")

    # 4. 校验 Cookie 格式与归属：必须能解析出键值对且含登录态 unb；
    #    若账号已有 unb，则提交 Cookie 的 unb 必须一致，防止把别的账号 Cookie 写进来（串号）。
    try:
        cookie_dict = trans_cookies(cookies)
    except Exception:  # noqa: BLE001
        cookie_dict = {}
    cookie_unb = str(cookie_dict.get("unb") or "").strip()
    if not cookie_dict or not cookie_unb:
        logger.warning(f"[外部Cookie同步] Cookie格式不正确 ip={client_ip} account_id={account_id}")
        return ApiResponse(success=False, message="Cookie 格式不正确或缺少登录态")
    expected_unb = str(account.unb or "").strip()
    if expected_unb and cookie_unb != expected_unb:
        logger.warning(
            f"[外部Cookie同步] Cookie与账号不匹配 ip={client_ip} account_id={account_id} "
            f"cookie_unb={cookie_unb} expected_unb={expected_unb}"
        )
        return ApiResponse(success=False, message="Cookie 与账号不匹配（unb 不一致）")

    # 5. 仅更新 Cookie 到数据库（不重启账号 WebSocket 任务，避免打断实时连接）
    await account_service.update_cookie(account, cookies)

    # 6. 回传新 Cookie 意味着账号已恢复，通知 scheduler 解除其风控冷却，
    #    让采集/补全等定时任务无需等满冷却期即可立即重新使用该账号。
    #    放入后台任务执行：不占用本次响应时延，scheduler 不可达时也不拖慢外部回传。
    background_tasks.add_task(_notify_scheduler_clear_cooldown, account_id)

    logger.info(
        f"[外部Cookie同步] 更新成功 ip={client_ip} account_id={account_id} owner={account.owner_id} "
        f"secret={_mask_secret(secret_key)} cookie_len={len(cookies)}"
    )
    return ApiResponse(success=True, message="Cookie 已更新")
