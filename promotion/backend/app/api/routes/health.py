"""
推广返佣系统 - 健康检查路由
"""
from fastapi import APIRouter

router = APIRouter(prefix="/health")


@router.get("")
async def health_check():
    """健康检查"""
    return {"success": True, "message": "服务运行正常"}
