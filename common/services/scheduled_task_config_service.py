"""统一定时任务配置保存：使用原任务表，安全任务只附加必要的事务状态联动。"""
from __future__ import annotations

from sqlalchemy import select

from common.models.scheduled_task import ScheduledTask
from common.models.security_task import SECURITY_INTERVAL_SECONDS, SECURITY_TASK_CODE
from common.services.audit_writer import AuditWriter
from common.services.security_config_service import (
    lock_security_schedule,
    lock_security_task,
)
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


def serialize_scheduled_task(task: ScheduledTask) -> dict:
    """返回原任务的真实配置及时间，保持原查询、更新响应字段兼容。"""
    return {key: getattr(task, key) for key in (
        'id', 'task_code', 'task_name', 'interval_seconds', 'enabled', 'description',
    )} | {'created_at': safe_isoformat(task.created_at), 'updated_at': safe_isoformat(task.updated_at)}


async def update_scheduled_task(task_code: str, interval_seconds: int | None, enabled: bool | None,
                                *, session_factory=None) -> dict:
    """统一锁内更新间隔和开关，未提交字段保留；返回提交后的真实配置。

    Args:
        task_code: 原任务表中的任务代码。
        interval_seconds: 可选间隔；安全检查固定20秒。
        enabled: 可选启停状态，停止不取消已取得占用的检查。
        session_factory: 隔离验证注入，默认使用项目统一工厂。
    Returns:
        原任务配置；安全任务下次执行状态与配置在同事务保存。
    """
    if interval_seconds is not None and (type(interval_seconds) is not int
                                         or not 1 <= interval_seconds <= 2147483647):
        raise ValueError('执行间隔必须是1至2147483647之间的整数秒数')
    if enabled is not None and not isinstance(enabled, bool):
        raise ValueError('定时任务启用状态必须是布尔值')
    if task_code == SECURITY_TASK_CODE and interval_seconds not in (None, SECURITY_INTERVAL_SECONDS):
        raise ValueError('安全频率检查固定每20秒执行，请在安全设置中修改频率阈值')

    async def save(session):
        """安全锁先于原配置锁，避免与统计、设置保存形成反向锁顺序。"""
        state = await lock_security_task(session) if task_code == SECURITY_TASK_CODE else None
        if state is not None:
            task = await lock_security_schedule(session)
        else:
            task = (await session.execute(select(ScheduledTask).where(ScheduledTask.task_code == task_code)
                .with_for_update())).scalar_one_or_none()
        if task is None:
            raise ValueError(f'任务不存在：{task_code}')
        if interval_seconds is not None:
            task.interval_seconds = interval_seconds
        if enabled is not None and task.enabled != enabled:
            task.enabled = enabled
            if state is not None:
                state.next_run_at = get_beijing_now_naive() if enabled else None
                state.updated_at = get_beijing_now_naive()
        await session.flush()
        # 服务端更新时间在异步会话中可能过期，显式刷新后再序列化，避免隐式IO。
        await session.refresh(task)
        return serialize_scheduled_task(task)

    return await AuditWriter(session_factory).write(save, context=f'定时任务配置 task_code={task_code} '
        f'interval_seconds={interval_seconds} enabled={enabled}')
