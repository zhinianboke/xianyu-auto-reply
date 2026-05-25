"""
健康检查API路由

提供服务健康状态检查接口，用于Docker/K8s健康检查
"""
from fastapi import APIRouter

from common.schemas.common import ApiResponse

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/ping")
async def ping() -> ApiResponse:
    """
    健康检查接口
    
    返回服务运行状态
    """
    return ApiResponse(
        success=True,
        message="ok",
        data={"status": "ok"}
    )
