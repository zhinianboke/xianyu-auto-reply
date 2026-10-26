"""无需登录的公开状态接口，通过前端代理访问并按真实 IP 执行 Redis 限流。"""
from __future__ import annotations

import asyncio
from ipaddress import ip_address
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from loguru import logger

from app.services.public_status_service import get_public_status
from common.schemas.common import ApiResponse
from common.services.redis_rate_limit_service import check_sliding_window_limit
from common.utils.http_utils import get_client_ip

router = APIRouter(prefix="/public", tags=["公开状态"])
WINDOW_SECONDS = 30
MAX_REQUESTS = 15


async def _check_access(request: Request, response: Response) -> ApiResponse | None:
    """校验客户端 IP 和共享限流额度，失败返回统一响应，放行返回 None。

    Args:
        request: 前端代理转发的请求，通过公共工具读取首个真实 IP。
        response: 用于设置禁止缓存、限流额度及重试等待响应头。
    Returns:
        IP 无效、超限或 Redis 异常时的业务响应；通过校验时为 None。
    """
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-RateLimit-Limit"] = str(MAX_REQUESTS)
    response.headers["X-RateLimit-Window"] = str(WINDOW_SECONDS)
    request_id = uuid4().hex
    client_ip = get_client_ip(request)
    log = logger.bind(request_id=request_id, operation="public_status", client_ip=client_ip)
    request.state.public_status_log = log
    log.info("[公开状态] 接口请求：method={} path={} query={} headers={}", request.method, request.url.path, str(request.query_params), dict(request.headers))
    try:
        address = ip_address(client_ip)
        client_ip = str(getattr(address, "ipv4_mapped", None) or address)
    except ValueError:
        log.warning("[公开状态] 无法识别客户端IP：{}", client_ip)
        return ApiResponse(success=False, code=40001, message="无法识别客户端IP", data=None)
    try:
        async with asyncio.timeout(5):
            limit = await check_sliding_window_limit(
                "public_status:ip", client_ip, window_seconds=WINDOW_SECONDS, max_requests=MAX_REQUESTS,
            )
    except Exception:
        log.exception("[公开状态] Redis限流检查失败，拒绝请求")
        return ApiResponse(success=False, code=50301, message="访问频率校验暂不可用，请稍后重试", data=None)
    response.headers["X-RateLimit-Remaining"] = str(limit.remaining)
    if not limit.allowed:
        response.headers["Retry-After"] = str(limit.retry_after)
        log.warning("[公开状态] 请求超过限制：retry_after={}", limit.retry_after)
        return ApiResponse(
            success=False, code=42901,
            message=f"访问过于频繁，同一IP在30秒内最多访问15次，请{limit.retry_after}秒后重试", data=None,
        )
    return None


@router.get("/status/", include_in_schema=False)
@router.get("/status")
async def public_status(request: Request, response: Response) -> ApiResponse:
    """校验 IP 和限流额度后查询四服务、在线账号数及全局总数。"""
    rejected = await _check_access(request, response)
    if rejected is not None:
        return rejected
    log = request.state.public_status_log
    try:
        data = await get_public_status()
    except Exception:
        log.exception("[公开状态] 状态查询失败")
        return ApiResponse(success=False, code=50302, message="服务状态查询暂不可用，请稍后重试", data=None)
    log.info("[公开状态] 查询完成：data={}", data)
    unavailable = []
    if not data["online_accounts_available"]:
        unavailable.append("在线账号数量")
    if not data["totals_available"]:
        unavailable.append("用户和账号总数")
    return ApiResponse(
        success=True, code=200,
        message="查询成功" if not unavailable else f"状态查询完成，{'、'.join(unavailable)}暂不可用",
        data=data,
    )


@router.api_route(
    "/status/", methods=["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"],
    include_in_schema=False,
)
@router.api_route(
    "/status", methods=["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"],
    include_in_schema=False,
)
async def unsupported_status_method(request: Request, response: Response) -> ApiResponse:
    """错误请求方法同样计入限流，校验通过后返回 HTTP 200 和中文业务错误。"""
    rejected = await _check_access(request, response)
    if rejected is not None:
        return rejected
    request.state.public_status_log.warning("[公开状态] 请求方法不支持：method={} path={}", request.method, request.url.path)
    return ApiResponse(success=False, code=40501, message="请求方法不支持，请使用GET请求", data=None)
