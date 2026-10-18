"""卡密处理结果日志管理接口。"""
from fastapi import APIRouter, Depends, Query
from app.api import deps
from app.services.card_process_result_log_service import CardProcessResultLogService
from common.models.user import User
from common.schemas.common import ApiResponse

router = APIRouter()

@router.get("/card-process-result-logs", response_model=ApiResponse)
async def list_logs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    order_no: str | None = Query(None), trigger_scene: str | None = Query(None),
    success: bool | None = Query(None),
    _: User = Depends(deps.get_current_admin_user),
    service: CardProcessResultLogService = Depends(deps.get_card_process_result_log_service),
) -> ApiResponse:
    data = await service.list_logs(page, page_size, order_no, trigger_scene, success)
    return ApiResponse(success=True, message="操作成功", data=data)

__all__ = ["router"]
