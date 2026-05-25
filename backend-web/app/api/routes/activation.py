"""
激活码公开API路由

功能：
1. 根据机器码生成试用激活码（15天）
2. 根据机器码生成续期码（5天）
3. 同一机器码每种类型每天只能生成一次
4. 所有生成记录写入 xy_activation_logs 表
均为公开接口，无需登录
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from common.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["激活码"])

# 激活码生成用的密钥盐值（与 launcher/activation.py 保持一致）
_SECRET_SALT = "XianyuAutoReply@2024#Lic"

# 北京时间时区
_BJ_TZ = timezone(timedelta(hours=8))

# 试用激活码默认天数
_TRIAL_DAYS = 15

# 续期码默认天数
_RENEW_DAYS = 5

# ========== SQL语句统一管理 ==========

# 查询指定机器码+类型在24小时内的最近一条记录（用于续期码限制）
SQL_CHECK_RECENT_LOG = text("""
    SELECT id, created_at FROM xy_activation_logs
    WHERE machine_id = :machine_id AND code_type = :code_type
      AND created_at >= :since
    ORDER BY created_at DESC
    LIMIT 1
""")

# 查询指定机器码是否已获取过试用激活码（永久限制，一个机器码只能获取一次）
SQL_CHECK_TRIAL_EXISTS = text("""
    SELECT id FROM xy_activation_logs
    WHERE machine_id = :machine_id AND code_type = 'generate'
    LIMIT 1
""")

# 插入激活码生成日志
SQL_INSERT_LOG = text("""
    INSERT INTO xy_activation_logs (machine_id, code_type, generated_code, days, ip_address, created_at)
    VALUES (:machine_id, :code_type, :generated_code, :days, :ip_address, :created_at)
""")

# 查询指定机器码的历史记录（按创建时间倒序）
SQL_GET_HISTORY = text("""
    SELECT id, machine_id, code_type, generated_code, days, ip_address, created_at
    FROM xy_activation_logs
    WHERE machine_id = :machine_id
    ORDER BY created_at DESC
    LIMIT :limit OFFSET :offset
""")

# 查询指定机器码的历史记录总数
SQL_COUNT_HISTORY = text("""
    SELECT COUNT(*) as total FROM xy_activation_logs
    WHERE machine_id = :machine_id
""")


class ActivationRequest(BaseModel):
    """激活码/续期码请求参数"""
    machine_id: str

    @field_validator("machine_id")
    @classmethod
    def validate_machine_id(cls, v: str) -> str:
        """校验机器码格式：32位十六进制字符串"""
        v = v.strip().upper()
        if len(v) != 32:
            raise ValueError(f"机器码长度应为32位，当前{len(v)}位")
        if not re.match(r'^[0-9A-F]{32}$', v):
            raise ValueError("机器码应为十六进制字符串（0-9, A-F）")
        return v


def _now_bj() -> datetime:
    """获取当前北京时间"""
    return datetime.now(_BJ_TZ)


def _calc_expire_time(days: int) -> int:
    """
    计算到期时间戳（北京时间）

    Args:
        days: 天数
    Returns:
        到期时间的Unix时间戳（秒）
    """
    expire = _now_bj() + timedelta(days=days)
    return int(expire.timestamp())


def _generate_activation_code(machine_id: str, expire_ts: int) -> str:
    """
    根据机器码和到期时间戳生成激活码

    激活码格式: {到期时间戳hex大写}-{签名16位大写}

    Args:
        machine_id: 32位大写机器码
        expire_ts: 到期时间的Unix时间戳（秒）
    Returns:
        激活码字符串
    """
    expire_hex = format(expire_ts, "X")
    sig = hashlib.sha256(
        f"{machine_id}:{expire_ts}:{_SECRET_SALT}".encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"{expire_hex}-{sig}"


def _build_renew_signature(machine_id: str, duration_seconds: int, issue_marker: str | None = None) -> str:
    """
    构建续期码签名

    Args:
        machine_id: 32位大写机器码
        duration_seconds: 续期时长（秒）
        issue_marker: 可选的唯一标识符（用于防止重复使用）
    Returns:
        16位大写签名字符串
    """
    if issue_marker is None:
        payload = f"{machine_id}:R:{duration_seconds}:{_SECRET_SALT}"
    else:
        payload = f"{machine_id}:R:{duration_seconds}:{issue_marker}:{_SECRET_SALT}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def _generate_renew_code(machine_id: str, duration_seconds: int) -> str:
    """
    生成续期激活码（以R开头，区别于普通激活码）

    续期码格式: R{时长秒数hex大写}-{唯一标识16位hex}-{签名16位大写}
    签名 = SHA256(机器码:R:时长秒数:唯一标识:盐) 取前16位

    Args:
        machine_id: 32位大写机器码
        duration_seconds: 要续期的时长（秒）
    Returns:
        续期码字符串，格式如 "R278D00-A1B2C3D4E5F67890-ABCDEF1234567890"
    """
    # 生成唯一标识符，用于防止续期码被重复使用
    issue_marker = secrets.token_hex(8).upper()
    dur_hex = format(duration_seconds, "X")
    sig = _build_renew_signature(machine_id, duration_seconds, issue_marker)
    return f"R{dur_hex}-{issue_marker}-{sig}"


def _format_expire_time(expire_ts: int) -> str:
    """格式化到期时间为北京时间字符串"""
    dt = datetime.fromtimestamp(expire_ts, tz=_BJ_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _build_history_expire_info(code_type: str, generated_code: str) -> tuple[str | None, bool | None, str]:
    if code_type != "generate":
        return None, None, "不适用"

    parts = (generated_code or "").strip().upper().split("-")
    if len(parts) != 2:
        return None, None, "未知"

    try:
        expire_ts = int(parts[0], 16)
    except ValueError:
        return None, None, "未知"

    expired = int(_now_bj().timestamp()) > expire_ts
    return _format_expire_time(expire_ts), expired, "已到期" if expired else "未到期"


def _get_client_ip(request: Request) -> str:
    """获取客户端真实IP地址"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


async def _check_daily_limit(
    db: AsyncSession, machine_id: str, code_type: str
) -> dict | None:
    """
    检查指定机器码+类型在24小时内是否已生成过

    Args:
        db: 数据库会话
        machine_id: 机器码
        code_type: 类型（generate / renew）
    Returns:
        None表示未超限，否则返回包含剩余时间的提示信息字典
    """
    since = _now_bj() - timedelta(hours=24)
    result = await db.execute(SQL_CHECK_RECENT_LOG, {
        "machine_id": machine_id,
        "code_type": code_type,
        "since": since,
    })
    row = result.first()
    if row is None:
        return None

    # 计算剩余等待时间
    last_time = row.created_at
    # 确保 last_time 带时区信息
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=_BJ_TZ)
    next_available = last_time + timedelta(hours=24)
    now = _now_bj()
    remaining = next_available - now
    if remaining.total_seconds() <= 0:
        return None

    hours = int(remaining.total_seconds()) // 3600
    mins = (int(remaining.total_seconds()) % 3600) // 60
    type_name = "获取激活码" if code_type == "generate" else "获取续期码"
    return {
        "message": f"该机器码每天只能{type_name}一次，请{hours}小时{mins}分钟后再试"
    }


async def _save_activation_log(
    db: AsyncSession, machine_id: str, code_type: str,
    generated_code: str, days: int, ip_address: str
) -> None:
    """
    保存激活码生成记录到数据库

    Args:
        db: 数据库会话
        machine_id: 机器码
        code_type: 类型（generate / renew）
        generated_code: 生成的激活码/续期码
        days: 有效天数
        ip_address: 请求IP
    """
    await db.execute(SQL_INSERT_LOG, {
        "machine_id": machine_id,
        "code_type": code_type,
        "generated_code": generated_code,
        "days": days,
        "ip_address": ip_address,
        "created_at": _now_bj(),
    })
    await db.commit()


@router.post("/generate", response_model=ApiResponse)
async def generate_trial_activation(
    req: ActivationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    生成试用激活码（公开接口，无需登录）
    默认有效期15天，同一机器码只能获取一次
    """
    try:
        # 检查该机器码是否已获取过试用激活码（永久限制）
        exists_result = await db.execute(SQL_CHECK_TRIAL_EXISTS, {
            "machine_id": req.machine_id,
        })
        if exists_result.first():
            return ApiResponse(success=False, message="该机器码已获取过试用激活码，每个机器码只能获取一次")

        expire_ts = _calc_expire_time(_TRIAL_DAYS)
        code = _generate_activation_code(req.machine_id, expire_ts)
        expire_str = _format_expire_time(expire_ts)

        # 记录生成日志
        ip = _get_client_ip(request)
        await _save_activation_log(
            db, req.machine_id, "generate", code, _TRIAL_DAYS, ip
        )

        logger.info(f"生成试用激活码: machine_id={req.machine_id[:8]}***, days={_TRIAL_DAYS}, ip={ip}")

        return ApiResponse(
            success=True,
            message="激活码生成成功",
            data={
                "activation_code": code,
                "expire_time": expire_str,
                "days": _TRIAL_DAYS,
                "machine_id": req.machine_id,
            }
        )
    except Exception as e:
        logger.error(f"生成试用激活码失败: {e}")
        return ApiResponse(success=False, message=str(e))


@router.post("/renew", response_model=ApiResponse)
async def generate_renew_activation(
    req: ActivationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    生成续期码（公开接口，无需登录）
    默认续期5天，同一机器码每天只能生成一次
    """
    try:
        # 检查24小时内是否已生成过
        limit_result = await _check_daily_limit(db, req.machine_id, "renew")
        if limit_result:
            return ApiResponse(success=False, message=limit_result["message"])

        duration_seconds = _RENEW_DAYS * 86400
        code = _generate_renew_code(req.machine_id, duration_seconds)

        # 记录生成日志
        ip = _get_client_ip(request)
        await _save_activation_log(
            db, req.machine_id, "renew", code, _RENEW_DAYS, ip
        )

        logger.info(f"生成续期码: machine_id={req.machine_id[:8]}***, days={_RENEW_DAYS}, ip={ip}")

        return ApiResponse(
            success=True,
            message="续期码生成成功",
            data={
                "renew_code": code,
                "days": _RENEW_DAYS,
                "machine_id": req.machine_id,
            }
        )
    except Exception as e:
        logger.error(f"生成续期码失败: {e}")
        return ApiResponse(success=False, message=str(e))


@router.post("/history", response_model=ApiResponse)
async def get_activation_history(
    req: ActivationRequest,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db_session),
):
    """
    查询激活码生成历史记录（公开接口，无需登录）
    
    根据机器码查询该机器的所有激活码/续期码生成记录，按创建时间倒序排列
    """
    try:
        # 查询总数
        count_result = await db.execute(SQL_COUNT_HISTORY, {
            "machine_id": req.machine_id,
        })
        total = count_result.scalar() or 0
        
        # 查询记录列表
        offset = (page - 1) * page_size
        result = await db.execute(SQL_GET_HISTORY, {
            "machine_id": req.machine_id,
            "limit": page_size,
            "offset": offset,
        })
        rows = result.fetchall()
        
        # 格式化结果
        records = []
        for row in rows:
            created_at = row.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=_BJ_TZ)
            expire_time, expired, expire_status = _build_history_expire_info(row.code_type, row.generated_code)
            records.append({
                "id": row.id,
                "code_type": row.code_type,
                "code_type_name": "激活码" if row.code_type == "generate" else "续期码",
                "generated_code": row.generated_code,
                "days": row.days,
                "ip_address": row.ip_address,
                "expire_time": expire_time,
                "expired": expired,
                "expire_status": expire_status,
                "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        
        total_pages = (total + page_size - 1) // page_size
        
        return ApiResponse(
            success=True,
            message="查询成功",
            data={
                "records": records,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )
    except Exception as e:
        logger.error(f"查询激活码历史失败: {e}")
        return ApiResponse(success=False, message=str(e))
