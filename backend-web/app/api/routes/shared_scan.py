"""
共享多人扫码登录路由

功能：
1. 管理员创建共享会话，生成可分享的链接
2. 兼职人员通过链接加入会话，各自获取独立的闲鱼二维码
3. 兼职轮询自己的扫码状态，成功后自动保存Cookie并启动账号任务
4. 管理员实时查看所有兼职的扫码状态
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db_session as get_db
from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.account_service import AccountService
from app.services.qr_login import qr_login_manager
from common.models.shared_scan_session import SharedScanSession
from common.models.shared_scan_worker import SharedScanWorker
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.account_limit_service import AccountLimitExceededError

router = APIRouter(prefix="/shared-scan", tags=["共享多人扫码登录"])

PART_TIME_SESSIONS: Dict[str, str] = {}
PROCESSED_WORKERS: Dict[str, Dict[str, Any]] = {}
WORKER_PROCESS_LOCKS: Dict[str, asyncio.Lock] = {}
ACCOUNT_SAVE_LOCKS: Dict[str, asyncio.Lock] = {}
JOIN_REQUEST_LOCKS: Dict[str, asyncio.Lock] = {}
JOINED_VISITORS: Dict[str, str] = {}


# ==================== 管理员接口 ====================

@router.post("/create")
async def create_shared_session(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    创建共享扫码登录会话（管理员）

    生成一个唯一的共享会话，返回可发送给多个兼职的链接。
    链接有效期72小时，兼职通过链接加入后各自独立扫码。
    """
    try:
        settings = get_settings()
        session_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=72)

        session = SharedScanSession(
            session_id=session_id,
            owner_id=current_user.id,
            owner_username=current_user.username,
            status="active",
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()

        # 生成分享链接（兼职端公开页面）
        frontend_url = _get_frontend_public_url(request, settings)
        share_url = f"{frontend_url}/shared-scan-page?session_id={session_id}"

        logger.info(f"共享扫码会话已创建: session_id={session_id}, owner={current_user.username}")
        return ApiResponse(
            success=True,
            message="共享会话创建成功",
            data={
                "session_id": session_id,
                "share_url": share_url,
                "expires_at": expires_at.isoformat(),
            },
        )
    except Exception as e:
        logger.exception("创建共享扫码会话失败")
        return ApiResponse(success=False, message=f"创建失败: {str(e)}")


@router.get("/list")
async def list_shared_sessions(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    获取当前用户的共享会话列表（管理员）

    返回所有会话及每个会话下的兼职状态统计。
    """
    try:
        settings = get_settings()
        frontend_url = _get_frontend_public_url(request, settings)
        result = await db.execute(
            select(SharedScanSession)
            .where(SharedScanSession.owner_id == current_user.id)
            .order_by(SharedScanSession.created_at.desc())
        )
        sessions = result.scalars().all()

        data = []
        for s in sessions:
            # 查询该会话下的兼职数量
            workers_result = await db.execute(
                select(SharedScanWorker).where(SharedScanWorker.shared_session_id == s.session_id)
            )
            workers = workers_result.scalars().all()

            data.append({
                "session_id": s.session_id,
                "status": s.status,
                "share_url": f"{frontend_url}/shared-scan-page?session_id={s.session_id}",
                "expires_at": s.expires_at.isoformat(),
                "created_at": s.created_at.isoformat(),
                "worker_count": len(workers),
                "success_count": sum(1 for w in workers if w.status == "success"),
            })

        return ApiResponse(success=True, message="获取成功", data={"sessions": data})
    except Exception as e:
        logger.exception("获取共享会话列表失败")
        return ApiResponse(success=False, message=f"查询失败: {str(e)}")


@router.get("/status")
async def get_session_status(
    session_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    查询共享会话下所有兼职的实时状态（管理员）

    返回该会话下每个兼职的扫码状态、账号ID等信息。
    """
    try:
        session = await _get_session_with_permission(session_id, current_user.id, db)
        if not session:
            return ApiResponse(success=False, message="会话不存在或无权访问")

        result = await db.execute(
            select(SharedScanWorker)
            .where(SharedScanWorker.shared_session_id == session_id)
            .order_by(SharedScanWorker.created_at.asc())
        )
        workers = result.scalars().all()

        worker_list = [
            {
                "sub_session_id": w.sub_session_id,
                "status": w.status,
                "account_id": w.account_id,
                "cookie_saved": w.cookie_saved,
                "joined_at": w.created_at.timestamp(),
            }
            for w in workers
        ]

        return ApiResponse(
            success=True,
            message="获取成功",
            data={
                "session_id": session_id,
                "session_status": session.status,
                "part_time_workers": worker_list,
            },
        )
    except Exception as e:
        logger.exception(f"查询共享会话状态失败: {session_id}")
        return ApiResponse(success=False, message=f"查询失败: {str(e)}")


@router.delete("/{session_id}")
async def delete_shared_session(
    session_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    删除共享会话（管理员）

    同时删除该会话下的所有兼职记录，并清理内存中的映射。
    """
    try:
        session = await _get_session_with_permission(session_id, current_user.id, db)
        if not session:
            return ApiResponse(success=False, message="会话不存在或无权访问")

        # 清理兼职记录及内存映射
        result = await db.execute(
            select(SharedScanWorker).where(SharedScanWorker.shared_session_id == session_id)
        )
        workers = result.scalars().all()
        for w in workers:
            PART_TIME_SESSIONS.pop(w.sub_session_id, None)
            PROCESSED_WORKERS.pop(w.sub_session_id, None)
            await db.delete(w)

        _clear_joined_visitor_cache(session_id)

        await db.delete(session)
        await db.commit()

        logger.info(f"共享扫码会话已删除: session_id={session_id}, owner={current_user.username}")
        return ApiResponse(success=True, message="删除成功")
    except Exception as e:
        logger.exception(f"删除共享会话失败: {session_id}")
        return ApiResponse(success=False, message=f"删除失败: {str(e)}")


# ==================== 兼职端接口（无需登录） ====================

@router.post("/join")
async def join_shared_session(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    兼职加入共享会话（无需登录）

    兼职通过共享链接访问，自动生成独立的闲鱼登录二维码。
    每次调用都会生成一个全新的兼职子会话和QR码。
    """
    try:
        session_id = data.get("session_id", "").strip()
        visitor_token = data.get("visitor_token", "").strip()
        force_refresh = bool(data.get("force_refresh", False))
        if not session_id:
            return ApiResponse(success=False, message="缺少 session_id 参数")

        join_cache_key = _build_join_cache_key(session_id, visitor_token)
        if join_cache_key:
            async with _get_async_lock(JOIN_REQUEST_LOCKS, join_cache_key):
                if force_refresh:
                    JOINED_VISITORS.pop(join_cache_key, None)
                else:
                    cached_sub_session_id = JOINED_VISITORS.get(join_cache_key)
                    if cached_sub_session_id:
                        cached_result = await db.execute(
                            select(SharedScanWorker).where(SharedScanWorker.sub_session_id == cached_sub_session_id)
                        )
                        cached_worker = cached_result.scalar_one_or_none()
                        if cached_worker:
                            return ApiResponse(
                                success=True,
                                message="加入成功，请扫描二维码",
                                data={
                                    "sub_session_id": cached_worker.sub_session_id,
                                    "qrcode_data_url": cached_worker.qr_code_url or "",
                                },
                            )
                        JOINED_VISITORS.pop(join_cache_key, None)

                return await _create_shared_scan_worker(
                    session_id=session_id,
                    join_cache_key=join_cache_key,
                    db=db,
                )

        return await _create_shared_scan_worker(
            session_id=session_id,
            join_cache_key="",
            db=db,
        )
    except Exception as e:
        logger.exception("兼职加入共享会话失败")
        return ApiResponse(success=False, message=f"加入失败: {str(e)}")


@router.get("/worker-status")
async def get_worker_status(
    sub_session_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    查询兼职自己的扫码状态（无需登录，兼职端轮询）

    检测二维码扫描状态，扫码成功后自动保存Cookie到账号表并启动WebSocket任务。
    """
    try:
        result = await db.execute(
            select(SharedScanWorker).where(SharedScanWorker.sub_session_id == sub_session_id)
        )
        worker = result.scalar_one_or_none()
        if not worker:
            return ApiResponse(success=False, message="兼职会话不存在或已过期")

        # 如果已经成功处理过，直接返回
        processed_info = PROCESSED_WORKERS.get(sub_session_id)
        if processed_info:
            return _build_worker_processed_response(processed_info, worker)

        # 从内存映射获取闲鱼 session_id
        xianyu_session_id = PART_TIME_SESSIONS.get(sub_session_id)
        if not xianyu_session_id:
            # 内存丢失（服务重启），尝试从DB恢复
            xianyu_session_id = worker.xianyu_session_id

        if not xianyu_session_id:
            return ApiResponse(
                success=True, message="获取成功",
                data={"status": worker.status}
            )

        # 查询闲鱼扫码状态
        status_info = qr_login_manager.get_session_status(xianyu_session_id)
        current_status = status_info.get("status")

        if current_status == "success" and not worker.cookie_saved:
            async with _get_async_lock(WORKER_PROCESS_LOCKS, sub_session_id):
                await db.refresh(worker)
                processed_info = PROCESSED_WORKERS.get(sub_session_id)
                if processed_info or worker.cookie_saved:
                    return _build_worker_processed_response(processed_info, worker)

                result_data = await _handle_scan_success(
                    worker=worker,
                    session_id=xianyu_session_id,
                    sub_session_id=sub_session_id,
                    db=db,
                )
            return ApiResponse(
                success=True,
                message=result_data.get("message") or ("扫码登录成功" if result_data.get("status") == "success" else "扫码登录失败"),
                data=result_data,
            )

        new_status = _map_qr_status(current_status)
        resp_data: Dict[str, Any] = {"status": new_status}

        if new_status == "verification_required":
            # 人脸验证是瞬时中间态，不落库(status 字段仅 20 字符，且 DB 状态仅用于展示/恢复，
            # 真实状态由 qr_login_manager 维护)，仅透传人脸二维码给兼职端展示
            resp_data["face_qr_url"] = status_info.get("face_qr_url")
        elif new_status != worker.status:
            # 同步其它中间状态到DB
            worker.status = new_status
            await db.commit()

        return ApiResponse(
            success=True, message="获取成功",
            data=resp_data
        )
    except Exception as e:
        logger.exception(f"查询兼职扫码状态失败: {sub_session_id}")
        return ApiResponse(success=False, message=f"查询失败: {str(e)}")


# ==================== 私有辅助函数 ====================

async def _get_session_with_permission(
    session_id: str, owner_id: int, db: AsyncSession
) -> Optional[SharedScanSession]:
    """获取会话并验证权限"""
    result = await db.execute(
        select(SharedScanSession).where(
            SharedScanSession.session_id == session_id,
            SharedScanSession.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_active_session(
    session_id: str, db: AsyncSession
) -> Optional[SharedScanSession]:
    """获取有效的共享会话（未过期且状态为active）"""
    result = await db.execute(
        select(SharedScanSession).where(
            SharedScanSession.session_id == session_id,
            SharedScanSession.status == "active",
            SharedScanSession.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


def _get_frontend_public_url(request: Request, settings: Any) -> str:
    """获取前端公开访问地址，优先取当前请求来源，其次取配置兜底。"""
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        return origin.rstrip("/")

    referer = (request.headers.get("referer") or "").strip()
    if referer:
        referer_base = referer.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        if "://" in referer_base:
            scheme, rest = referer_base.split("://", 1)
            host = rest.split("/", 1)[0]
            if host:
                return f"{scheme}://{host}"

    configured_frontend_url = (getattr(settings, "frontend_public_url", "") or "").strip()
    if configured_frontend_url:
        return configured_frontend_url.rstrip("/")

    return settings.backend_web_public_url.rstrip("/")


def _build_join_cache_key(session_id: str, visitor_token: str) -> str:
    if not session_id or not visitor_token:
        return ""
    return f"{session_id}:{visitor_token}"


def _get_async_lock(lock_store: Dict[str, asyncio.Lock], key: str) -> asyncio.Lock:
    lock = lock_store.get(key)
    if lock is None:
        lock = asyncio.Lock()
        lock_store[key] = lock
    return lock


def _clear_joined_visitor_cache(session_id: str) -> None:
    session_prefix = f"{session_id}:"
    cached_keys = [key for key in JOINED_VISITORS if key.startswith(session_prefix)]
    for key in cached_keys:
        JOINED_VISITORS.pop(key, None)
        JOIN_REQUEST_LOCKS.pop(key, None)


def _build_worker_processed_response(processed_info: dict[str, Any] | None, worker: SharedScanWorker) -> ApiResponse:
    info = processed_info or {}
    processed_status = info.get("status") or ("success" if worker.cookie_saved else worker.status)
    processed_message = info.get("message") or ("扫码登录成功" if processed_status == "success" else "扫码登录失败")
    return ApiResponse(
        success=True,
        message=processed_message,
        data={
            "status": processed_status,
            "account_id": info.get("account_id") or worker.account_id,
            "message": processed_message,
        },
    )


def _map_qr_status(qr_status: Optional[str]) -> str:
    """将 qr_login_manager 的状态映射为兼职状态"""
    mapping = {
        "waiting": "qrcode_ready",
        "scanned": "scanning",
        "success": "success",
        "verification_required": "verification_required",
        "expired": "failed",
        "cancelled": "failed",
        "not_found": "failed",
    }
    return mapping.get(qr_status or "", "qrcode_ready")


async def _create_shared_scan_worker(
    session_id: str,
    join_cache_key: str,
    db: AsyncSession,
) -> ApiResponse:
    session = await _get_active_session(session_id, db)
    if not session:
        return ApiResponse(success=False, message="共享会话不存在或已过期")

    result = await qr_login_manager.generate_qr_code()
    if not result.get("success"):
        error_msg = result.get("message", "生成二维码失败")
        logger.error(f"共享扫码 - 生成QR码失败: {error_msg}")
        return ApiResponse(success=False, message=error_msg)

    xianyu_session_id = result["session_id"]
    qr_code_url = result["qr_code_url"]
    sub_session_id = str(uuid.uuid4())

    worker = SharedScanWorker(
        shared_session_id=session_id,
        sub_session_id=sub_session_id,
        xianyu_session_id=xianyu_session_id,
        status="qrcode_ready",
        qr_code_url=qr_code_url,
    )
    db.add(worker)
    await db.commit()

    PART_TIME_SESSIONS[sub_session_id] = xianyu_session_id
    if join_cache_key:
        JOINED_VISITORS[join_cache_key] = sub_session_id

    logger.info(f"兼职加入共享会话: session_id={session_id}, sub_session_id={sub_session_id}")
    return ApiResponse(
        success=True,
        message="加入成功，请扫描二维码",
        data={
            "sub_session_id": sub_session_id,
            "qrcode_data_url": qr_code_url,
        },
    )


async def _handle_scan_success(
    worker: SharedScanWorker,
    session_id: str,
    sub_session_id: str,
    db: AsyncSession,
) -> dict[str, str]:
    """
    处理扫码成功：保存Cookie到账号表，启动WebSocket任务

    Args:
        worker: 兼职工作者记录
        session_id: 闲鱼QR会话ID
        sub_session_id: 兼职子会话ID
        db: 数据库会话

    Returns:
        账号ID（unb）
    """
    cookies_info = qr_login_manager.get_session_cookies(session_id)
    if not cookies_info:
        logger.warning(f"扫码成功但获取Cookie失败: {sub_session_id}")
        worker.status = "success"
        await db.commit()
        processed_info = {"status": "success", "account_id": worker.account_id or "", "message": "扫码登录成功"}
        PROCESSED_WORKERS[sub_session_id] = processed_info
        return processed_info

    cookies_str = cookies_info.get("cookies") or ""
    unb = cookies_info.get("unb") or ""

    if not unb:
        logger.warning(f"共享扫码登录：登录成功但 unb 为空，无法创建账号: {sub_session_id}")
        worker.status = "success"
        await db.commit()
        processed_info = {"status": "success", "account_id": worker.account_id or "", "message": "扫码登录成功"}
        PROCESSED_WORKERS[sub_session_id] = processed_info
        return processed_info

    async with _get_async_lock(ACCOUNT_SAVE_LOCKS, unb):
        await db.refresh(worker)
        processed_info = PROCESSED_WORKERS.get(sub_session_id)
        if processed_info or worker.cookie_saved:
            return processed_info or {"status": "success", "account_id": worker.account_id or unb, "message": "扫码登录成功"}

        session_result = await db.execute(
            select(SharedScanSession).where(SharedScanSession.session_id == worker.shared_session_id)
        )
        shared_session = session_result.scalar_one_or_none()
        owner_id = shared_session.owner_id if shared_session else 0

        try:
            account_service = AccountService(db)
            account, is_new = await account_service.upsert_account_from_qr(
                owner_id=owner_id,
                cookies=cookies_str,
                unb=unb,
                login_method="shared_qr_scan",
            )
        except AccountLimitExceededError as exc:
            worker.status = "failed"
            await db.commit()
            processed_info = {
                "status": "failed",
                "account_id": "",
                "message": str(exc),
            }
            PROCESSED_WORKERS[sub_session_id] = processed_info
            PART_TIME_SESSIONS.pop(sub_session_id, None)
            return processed_info

        logger.info(
            f"共享扫码登录：{'创建新账号' if is_new else '更新现有账号'} unb={unb}, owner_id={owner_id}"
        )

        worker.status = "success"
        worker.account_id = unb
        worker.cookie_saved = True
        await db.commit()
        await db.refresh(account)

        processed_info = {"status": "success", "account_id": unb, "message": "扫码登录成功"}
        PROCESSED_WORKERS[sub_session_id] = processed_info
        PART_TIME_SESSIONS.pop(sub_session_id, None)

        try:
            settings = get_settings()
            client = get_http_client()
            endpoint = "start" if is_new else "restart"
            response = await client.post(
                f"{settings.websocket_service_url}/internal/accounts/{account.account_id}/{endpoint}",
                json={"cookie_value": cookies_str, "user_id": owner_id},
            )
            if response.get("success"):
                logger.info(f"共享扫码登录：账号 WebSocket 任务已{'启动' if is_new else '重启'} {account.account_id}")
            else:
                logger.warning(f"共享扫码登录：WebSocket 任务操作失败 {account.account_id}: {response.get('message')}")
        except Exception as ws_e:
            logger.error(f"共享扫码登录：调用 WebSocket 服务失败 {account.account_id}: {ws_e}")

    return processed_info
