"""安全任务启停服务：共用数据库锁与审计写入器，保留配置及历史执行结果。"""
from __future__ import annotations

from common.services.audit_writer import AuditWriter, report_safely
from common.services.security_config_service import lock_security_task
from common.services.security_query_service import SecurityQueryService
from common.utils.time_utils import get_beijing_now_naive


async def set_security_task_enabled(enabled: bool | None, *, session_factory=None) -> dict:
    """锁内保存自动检查启停并返回真实任务状态，未提交开关时保留原值。

    Args:
        enabled: 自动检查开关；None表示只读取原状态。
        session_factory: 仅隔离验证注入，默认使用项目统一会话工厂。
    Returns:
        保存后的真实调度状态；停止不取消已取得占用的执行和审计。
    """
    if enabled is not None and not isinstance(enabled, bool):
        raise ValueError('安全定时任务启用状态必须是布尔值')

    async def save(session):
        """取得自动执行及设置共用的锁，只更新实际改变的开关和下次执行时间。"""
        task = await lock_security_task(session)
        if enabled is not None and task.enabled != enabled:
            now = get_beijing_now_naive()
            task.enabled = enabled
            task.next_run_at = now if enabled else None
            task.updated_at = now
        return SecurityQueryService.serialize_task(task)

    result = await AuditWriter(session_factory).write(save, context=f'安全定时任务启停 enabled={enabled}')
    file_error = report_safely(f'安全定时任务状态已保存 result={result}', level='INFO')
    if file_error:
        raise RuntimeError(f'安全定时任务状态已保存，{file_error}，请刷新任务列表确认')
    return result
