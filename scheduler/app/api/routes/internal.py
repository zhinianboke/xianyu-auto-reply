"""
Scheduler服务内部API路由

功能：
1. 提供任务配置重新加载接口
2. 提供任务运行状态查询接口
3. 提供手动触发任务执行接口
4. 提供内部日志保留天数实时刷新接口
"""
from __future__ import annotations

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from app.services.scheduler_service import get_scheduler_service
from common.utils.time_utils import get_beijing_now_naive

router = APIRouter(prefix="/internal", tags=["internal"])


class LogRetentionRequest(BaseModel):
    """日志保留天数刷新请求"""
    retention_days: int


@router.post("/logs/retention")
async def refresh_log_retention(request: LogRetentionRequest):
    """实时刷新日志保留天数"""
    try:
        from common.utils.logging_utils import update_log_retention

        updated = update_log_retention(request.retention_days)
        return {
            "success": True,
            "code": 200,
            "message": "日志保留天数已刷新" if updated else "日志保留天数无需变更",
            "data": {
                "retention_days": request.retention_days,
                "updated": updated,
            },
        }
    except Exception as e:
        logger.error(f"[内部API] 刷新日志保留天数失败: {e}")
        return {
            "success": False,
            "code": 500,
            "message": f"日志保留天数刷新失败: {str(e)}",
            "data": None,
        }


@router.post("/tasks/reload")
async def reload_tasks():
    """
    重新加载任务配置
    
    功能：
    - 从数据库重新读取任务配置
    - 更新任务执行间隔
    - 启用/禁用任务
    
    Returns:
        操作结果
    """
    try:
        scheduler = get_scheduler_service()
        await scheduler.reload_all_configs()
        
        return {
            "success": True,
            "code": 200,
            "message": "任务配置已重新加载",
            "data": None,
        }
    except Exception as e:
        logger.error(f"[内部API] 重新加载任务配置失败: {e}")
        return {
            "success": False,
            "code": 500,
            "message": f"重新加载任务配置失败: {str(e)}",
            "data": None,
        }


@router.get("/tasks/status")
async def get_tasks_status():
    """
    查询所有任务运行状态
    
    Returns:
        任务状态信息
    """
    try:
        scheduler = get_scheduler_service()
        status = scheduler.get_task_status()
        
        return {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": status,
        }
    except Exception as e:
        logger.error(f"[内部API] 查询任务状态失败: {e}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询任务状态失败: {str(e)}",
            "data": None,
        }


@router.post("/tasks/{task_code}/trigger")
async def trigger_task(task_code: str):
    """
    手动触发任务执行
    
    Args:
        task_code: 任务代码(redelivery/rate/polish/day_switch等)
        
    Returns:
        操作结果
    """
    try:
        # 验证任务代码
        if task_code not in ["redelivery", "rate", "polish", "day_switch", "cleanup_browser_data", "fetch_orders", "fetch_pending_orders", "fetch_items", "login_renew", "cookies_refresh", "api_cookie_renew", "close_notice", "red_flower", "db_backup"]:
            return {
                "success": False,
                "code": 400,
                "message": f"无效的任务代码: {task_code}",
                "data": None,
            }
        
        scheduler = get_scheduler_service()
        await scheduler.trigger_task(task_code)
        
        return {
            "success": True,
            "code": 200,
            "message": f"任务 {task_code} 已触发执行",
            "data": {
                "task_code": task_code,
                "triggered_at": get_beijing_now_naive().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"[内部API] 触发任务执行失败: {e}")
        return {
            "success": False,
            "code": 500,
            "message": f"触发任务执行失败: {str(e)}",
            "data": None,
        }
