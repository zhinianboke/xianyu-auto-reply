"""原定时任务管理服务：统一配置保存、调度器通知和手动执行。"""
from __future__ import annotations

from urllib.parse import quote

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.services.audit_writer import report_safely
from common.services.scheduled_task_config_service import update_scheduled_task


class ScheduledTaskManagementService:
    """管理员路由调用的配置、执行服务；权限在统一管理员依赖中校验。"""

    def __init__(self, session):
        """复用请求会话及项目HTTP客户端，不创建数据库工厂或连接池。"""
        self.session = session

    async def update(self, task_code: str, interval_seconds: int | None, enabled: bool | None) -> dict:
        """所有任务共用原配置保存，未提交字段保持原值，再通知原调度器。"""
        await self.session.commit()
        data = await update_scheduled_task(task_code, interval_seconds, enabled)
        file_error = report_safely(f'定时任务配置已保存 task_code={task_code} result={data}', level='INFO')
        try:
            response = await get_http_client().post(f'{get_settings().scheduler_service_url}/internal/tasks/reload')
        except Exception as exc:
            report_safely(f'定时任务配置已保存但通知调度器失败 task_code={task_code} data={data}', exc)
            if file_error:
                raise RuntimeError(f'配置已保存，但通知调度器失败：{exc}；{file_error}，请刷新确认') from exc
            return {'message': f'配置已保存，但通知调度器失败：{exc}，请刷新调度器配置', 'data': data}
        if not response.get('success'):
            report_safely(f'定时任务配置已保存但调度器刷新失败 task_code={task_code} response={response}')
            if file_error:
                raise RuntimeError(f'配置已保存，但调度器刷新失败：{response.get("message")}；{file_error}')
            return {'message': f"配置已保存，但调度器刷新失败：{response.get('message') or '未返回处理结果'}", 'data': data}
        if file_error:
            raise RuntimeError(f'定时任务配置已保存并通知调度器，{file_error}，请刷新确认')
        return {'message': '更新成功，已通知调度器刷新配置', 'data': data}

    async def trigger(self, task_code: str, owner_id: int) -> dict:
        """按原任务代码分派执行；安全检查完成实际审计后才返回成功结果。"""
        await self.session.commit()
        url = f'{get_settings().scheduler_service_url}/internal/tasks/{quote(task_code, safe="")}/trigger'
        url += f'?owner_id={owner_id}'
        try:
            # 执行请求有副作用；超时不重试，避免一次点击触发多轮审计。
            response = await get_http_client().post(url, timeout=90, max_retries=1)
        except Exception as exc:
            report_safely(f'定时任务执行响应未确认 task_code={task_code} owner_id={owner_id}', exc)
            raise RuntimeError('未能确认定时任务执行结果，请查询执行日志后再操作') from exc
        if not response.get('success'):
            raise ValueError(response.get('message') or '触发任务失败')
        file_error = report_safely(f'定时任务手动触发成功 task_code={task_code} owner_id={owner_id} response={response}', level='INFO')
        if file_error:
            raise RuntimeError(f'定时任务已执行，{file_error}，请查询执行日志确认')
        return {'message': response.get('message') or f'任务 {task_code} 已触发执行',
                'data': response.get('data')}
