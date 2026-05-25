"""
版本检测路由

功能：
1. 提供系统当前版本号查询接口
2. 提供"检查更新"接口，向远程更新服务器请求最新版本信息

接口规范：
- 所有接口统一返回 ApiResponse（success/message/data），
  业务错误通过 success=False + message 返回，前端据此弹 toast。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.services.version_service import check_update, get_current_version
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/version", tags=["版本检测"])


@router.get("/current", response_model=ApiResponse)
async def get_current_version_api() -> ApiResponse:
    """
    获取系统当前版本号

    Returns:
        ApiResponse.data: { version: str }
    """
    version = get_current_version()
    if not version:
        return ApiResponse(success=False, message="无法读取当前版本号")
    return ApiResponse(success=True, data={"version": version})


@router.get("/check", response_model=ApiResponse)
async def check_update_api() -> ApiResponse:
    """
    检查是否有新版本可用

    调用远程 version.json，对比本地版本后返回结果。
    即使无更新也返回 success=True，前端依据 data.has_update 判断是否展示弹窗。

    Returns:
        ApiResponse.data: {
            has_update: bool,
            current_version: str,
            remote_version: str,
            description: str,
            filename: str,
            download_url: str,
        }
    """
    result = await check_update()
    if result.get("error"):
        return ApiResponse(
            success=False,
            message=result["error"],
            data={
                "has_update": False,
                "current_version": result.get("current_version", ""),
                "remote_version": "",
                "description": "",
                "filename": "",
                "download_url": "",
            },
        )

    return ApiResponse(
        success=True,
        data={
            "has_update": bool(result.get("has_update")),
            "current_version": result.get("current_version", ""),
            "remote_version": result.get("remote_version", ""),
            "description": result.get("description", ""),
            "filename": result.get("filename", ""),
            "download_url": result.get("download_url", ""),
        },
    )
