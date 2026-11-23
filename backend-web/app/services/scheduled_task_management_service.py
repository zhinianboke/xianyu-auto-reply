"""原定时任务管理服务：保留原配置更新与调度器通知，安全任务复用独立审计执行器。"""
from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.models.scheduled_task import ScheduledTask
from common.models.security_task import SECURITY_INTERVAL_SECONDS, SECURITY_TASK_CODE
from common.services.audit_writer import report_safely
from common.services.scheduled_task_query_service import ScheduledTaskQueryService
from common.services.security_frequency_service import security_frequency_service
from common.services.security_task_service import set_security_task_enabled


class ScheduledTaskManagementService:
    """管理员路由调用的配置、执行服务；权限在统一管理员依赖中校验。"""

    def __init__(self, session):
        """复用请求会话及项目HTTP客户端，不创建数据库工厂或连接池。"""
        self.session = session

    async def update(self, task_code: str, interval_seconds: int | None, enabled: bool | None) -> dict:
        """只更新指定配置；安全任务支持持久化启停，执行间隔固定20秒。"""
        if task_code == SECURITY_TASK_CODE:
            if interval_seconds is not None and interval_seconds != SECURITY_INTERVAL_SECONDS:
                raise ValueError('安全频率检查固定每20秒执行，请在系统设置的安全设置中修改频率阈值')
            # 释放鉴权只读事务，独立事务重新取得调度与安全设置共用的锁。
            await self.session.commit()
            data = await set_security_task_enabled(enabled)
            return {'message': '安全定时任务已启用' if data['enabled'] else '安全定时任务已停止', 'data': data}
        result = await self.session.execute(select(ScheduledTask).where(ScheduledTask.task_code == task_code))
        task = result.scalar_one_or_none()
        if task is None:
            raise ValueError(f'任务不存在: {task_code}')
        if interval_seconds is not None:
            if interval_seconds < 1 or interval_seconds > 2147483647:
                raise ValueError('执行间隔必须是1至2147483647之间的整数秒数')
            task.interval_seconds = interval_seconds
        if enabled is not None:
            task.enabled = enabled
        await self.session.commit()
        await self.session.refresh(task)
        data = ScheduledTaskQueryService.serialize_task(task)
        report_safely(f'定时任务配置已保存 task_code={task_code} result={data}', level='INFO')
        try:
            response = await get_http_client().post(f'{get_settings().scheduler_service_url}/internal/tasks/reload')
        except Exception as exc:
            report_safely(f'定时任务配置已保存但通知调度器失败 task_code={task_code} data={data}', exc)
            return {'message': f'配置已保存，但通知调度器失败：{exc}，请刷新调度器配置', 'data': data}
        if not response.get('success'):
            report_safely(f'定时任务配置已保存但调度器刷新失败 task_code={task_code} response={response}')
            return {'message': f"配置已保存，但调度器刷新失败：{response.get('message') or '未返回处理结果'}", 'data': data}
        return {'message': '更新成功，已通知调度器刷新配置', 'data': data}

    async def trigger(self, task_code: str, owner_id: int) -> dict:
        """按原任务代码分派执行；安全检查完成实际审计后才返回成功结果。"""
        if task_code == SECURITY_TASK_CODE:
            data = await security_frequency_service.execute_manual(self.session, owner_id)
            return {'message': data['message'], 'data': data}
        response = await get_http_client().post(
            f'{get_settings().scheduler_service_url}/internal/tasks/{task_code}/trigger')
        if not response.get('success'):
            raise ValueError(response.get('message') or '触发任务失败')
        report_safely(f'定时任务手动触发成功 task_code={task_code} owner_id={owner_id} response={response}', level='INFO')
        return {'message': response.get('message') or f'任务 {task_code} 已触发执行', 'data': None}
