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

from app.services.scheduler.listing_monitor_task import listing_monitor_task_service
from app.services.scheduler_service import get_scheduler_service
from common.services.account_cooldown import account_cooldown_manager
from common.utils.time_utils import get_beijing_now_naive

router = APIRouter(prefix="/internal", tags=["internal"])


class LogRetentionRequest(BaseModel):
    """日志保留天数刷新请求"""
    retention_days: int


class AccountCooldownClearRequest(BaseModel):
    """解除账号风控冷却请求"""
    account_id: str


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
        if task_code not in ["redelivery", "rate", "polish", "day_switch", "cleanup_browser_data", "fetch_orders", "fetch_pending_orders", "fetch_refund_orders", "fetch_items", "login_renew", "cookies_refresh", "api_cookie_renew", "close_notice", "red_flower", "db_backup", "delivery_timeout", "listing_monitor", "seller_fill", "dm_send", "auto_order"]:
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


@router.post("/account-cooldown/clear")
async def clear_account_cooldown(request: AccountCooldownClearRequest):
    """解除指定账号的风控冷却（如外部回传新 Cookie 后立即恢复该账号可用）。

    冷却态仅存在于 scheduler 进程内存中，故由 backend-web 通过本内部接口跨进程触发解除。
    """
    try:
        account_id = (request.account_id or "").strip()
        if not account_id:
            return {
                "success": False,
                "code": 400,
                "message": "account_id 不能为空",
                "data": None,
            }
        cleared = account_cooldown_manager.clear(account_id)
        return {
            "success": True,
            "code": 200,
            "message": "账号风控冷却已解除" if cleared else "该账号当前不在冷却期，无需解除",
            "data": {"account_id": account_id, "cleared": cleared},
        }
    except Exception as e:
        logger.error(f"[内部API] 解除账号风控冷却失败: {e}")
        return {
            "success": False,
            "code": 500,
            "message": f"解除账号风控冷却失败: {str(e)}",
            "data": None,
        }


@router.post("/tasks/listing_monitor/run/{task_id}")
async def run_listing_monitor_single(task_id: int):
    """手动执行单个商品监控任务的采集（忽略间隔，立即执行一次，日志记为手动触发）"""
    try:
        result = await listing_monitor_task_service.run_single(task_id, trigger_type="manual")
        return {
            "success": bool(result.get("success")),
            "code": 200 if result.get("success") else 400,
            "message": result.get("message") or "",
            "data": {"task_id": task_id, "triggered_at": get_beijing_now_naive().isoformat()},
        }
    except Exception as e:
        logger.error(f"[内部API] 手动执行商品监控任务失败: {e}")
        return {
            "success": False,
            "code": 500,
            "message": f"手动执行商品监控任务失败: {str(e)}",
            "data": None,
        }


@router.post("/system/self-restart")
async def system_self_restart():
    """
    重启本服务（定时任务服务 / scheduler）

    由 backend-web 的系统管理接口调用。自动识别运行环境：
    - docker：本进程延迟自杀退出，容器 restart 策略自动拉起
    - dev/frozen：派生脱离父进程的协调子进程，杀端口后重新拉起

    先返回成功响应，再在后台触发重启。
    """
    from common.utils.service_restart import restart_service

    result = restart_service("scheduler")
    return {
        "success": bool(result.get("success")),
        "code": 200 if result.get("success") else 500,
        "message": result.get("message") or "",
        "data": {"mode": result.get("mode")},
    }
