"""安全频率执行器：持久化占用、锁内统计追加与成功审计、独立失败审计及关闭排空。"""
from __future__ import annotations

import asyncio
import json
import traceback
from datetime import timedelta
from uuid import uuid4

from common.models.security_log import SecurityLog
from common.models.security_task import (
    SECURITY_LEASE_SECONDS,
    SECURITY_METHODS,
    SECURITY_SCAN_TIMEOUT_SECONDS,
)
from common.services.audit_writer import AuditWriteError, AuditWriter, report_safely
from common.services.auth_security_policy import (
    AUTH_DENIED_IPS_KEY,
    AUTH_FREQUENCY_KEYS,
    AUTH_SECURITY_DEFAULTS,
    normalize_security_setting,
)
from common.services.email_domain_policy import EMAIL_DOMAIN_DENY_KEY
from common.services.security_config_service import (
    load_security_values_locked,
    lock_security_task,
    save_security_values,
)
from common.services.security_frequency_stats import (
    collect_statistics,
    initialize_statistics,
)
from common.utils.async_cleanup import complete_before_cancellation
from common.utils.time_utils import get_beijing_now_naive


class SecurityExecutionError(RuntimeError):
    """执行失败时向管理端报告明确中文原因，详情保留真实完整故障。"""


class SecurityFrequencyService:
    """自动与手动执行共用服务；实例内排空，实例间使用持久化数据库占用和锁。"""

    def __init__(self, session_factory=None):
        """复用项目统一工厂；隔离测试可注入工厂，不创建引擎或Redis池。"""
        self.writer = AuditWriter(session_factory)
        self.active: set[asyncio.Task] = set()
        self.closing = False

    async def execute(self, method: str = 'auto', owner_id: int | None = None) -> dict | None:
        """注册执行生命周期；请求取消仍等待执行和审计完成，关闭后拒绝新任务。"""
        if method not in SECURITY_METHODS or (method == 'manual' and owner_id is None):
            raise ValueError('安全检查执行方式或管理员信息无效')
        if method == 'manual' and (type(owner_id) is not int or owner_id <= 0):
            raise ValueError('安全检查管理员信息无效')
        if self.closing:
            raise SecurityExecutionError('系统正在关闭，请稍后执行安全检查')
        worker = asyncio.create_task(self._execute(method, owner_id if method == 'manual' else None))
        self.active.add(worker)
        worker.add_done_callback(self.active.discard)
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # 取消只改变调用方等待状态，不中断已经取得占用的数据库审计。
            await complete_before_cancellation(self._wait_execution(worker), operation='安全检查执行与审计排空')
            raise

    async def _wait_execution(self, worker: asyncio.Task) -> None:
        """取消后的收尾只等待已有执行，保留原取消语义，不发起第二次检查。"""
        await asyncio.gather(asyncio.shield(worker), return_exceptions=True)

    async def drain(self) -> None:
        """禁止新增执行，等待当前自动/手动检查及其失败审计全部结束。"""
        self.closing = True
        while self.active:
            await asyncio.gather(*tuple(self.active), return_exceptions=True)

    async def _execute(self, method: str, owner_id: int | None) -> dict | None:
        """先独立提交占用，再原子执行；提交未知时保留占用且禁止相反失败审计。"""
        execution_id = uuid4().hex
        details = {'execution_id': execution_id, 'execution_method': method,
                   'candidate_suffixes': [], 'candidate_ips': [], 'windows': []}

        async def claim(session):
            """行锁下防止业务扫描重叠；执行间隔与启停由原调度器统一管理。"""
            task = await lock_security_task(session)
            now = get_beijing_now_naive()
            if task.lease_id and task.lease_expires_at and task.lease_expires_at > now:
                return False
            task.lease_id, task.lease_expires_at = execution_id, now + timedelta(seconds=SECURITY_LEASE_SECONDS)
            return True

        try:
            claimed = await self.writer.write(claim, context=f'安全占用 execution_id={execution_id}')
        except AuditWriteError as exc:
            reason = '占用提交结果未知，请查询任务占用确认' if exc.commit_unknown else str(exc)
            raise SecurityExecutionError(f'安全检查未能取得占用，执行编号{execution_id}：{reason}') from exc
        if not claimed:
            if method == 'manual':
                raise SecurityExecutionError('安全检查正在执行，请稍后重试')
            return None
        started_at = get_beijing_now_naive()
        details['started_at'] = started_at.isoformat()
        state = {}

        async def prepare(session):
            """重新取得共享事务锁，检查占用仍属于本次执行。"""
            task = await lock_security_task(session)
            if task.lease_id != execution_id:
                raise SecurityExecutionError('安全检查占用已失效，未修改禁止名单')
            state['task'] = task

        async def prepare_execution(session):
            """每次业务重试取锁前清理回滚详情；失败审计取锁仍保留确定的最终故障详情。"""
            details.clear()
            details.update(execution_id=execution_id, execution_method=method, started_at=started_at.isoformat(),
                           candidate_suffixes=[], candidate_ips=[], windows=[])
            await prepare(session)

        async def run(session):
            """扫描超时回滚全部写入；日志、实际新增名单和业务结果同事务提交。"""
            async with asyncio.timeout(SECURITY_SCAN_TIMEOUT_SECONDS):
                raw = await load_security_values_locked(session)
                details['settings_snapshot'] = dict(raw)
                initialize_statistics(raw, started_at, details)
                settings = {key: normalize_security_setting(key, raw.get(key, default[0]))
                            for key, default in AUTH_SECURITY_DEFAULTS.items()}
                await collect_statistics(session, settings, started_at, details)
                changes, additions = {}, {}
                for key, candidate_key in ((EMAIL_DOMAIN_DENY_KEY, 'candidate_suffixes'),
                                           (AUTH_DENIED_IPS_KEY, 'candidate_ips')):
                    current = settings[key].split(',') if settings[key] else []
                    current_set = set(current)
                    added = [item for item in details[candidate_key] if item not in current_set]
                    # 容量校验前先保存完整候选及完整目标，失败审计保留全部上下文。
                    details[f'target_{candidate_key}'] = current + added
                    additions[key] = added
                    if added:
                        original = raw.get(key, '')
                        changes[key] = (original + ',' if original.strip() else '') + ','.join(added)
                for key, value in changes.items():
                    normalize_security_setting(key, value)
                task = state['task']
                await save_security_values(session, task, changes)
                added_suffixes, added_ips = additions[EMAIL_DOMAIN_DENY_KEY], additions[AUTH_DENIED_IPS_KEY]
                if not any(int(settings[key]) for key in AUTH_FREQUENCY_KEYS.values()):
                    result, message = 'disabled', '七档安全频率均为0，本轮检查已关闭'
                elif details.get('direct_suffixes') or details.get('direct_ips'):
                    result, message = 'success', f'安全检查完成，新增{len(added_suffixes)}个后缀、{len(added_ips)}个IP'
                else:
                    result, message = 'no_violation', '安全检查完成，未发现违规项'
                return await self._append_result(session, task, details, execution_id, owner_id, method,
                                                 result, message, added_suffixes, added_ips, started_at)

        try:
            response = await self.writer.write(run, prepare=prepare_execution, context=lambda: json.dumps(details, ensure_ascii=False))
        except AuditWriteError as exc:
            if exc.commit_unknown:
                raise SecurityExecutionError(f'安全检查提交结果未知，请查询执行编号{execution_id}确认；未重复审计或修改名单') from exc
            await self._save_failure(prepare, state, details, execution_id, owner_id, method, started_at, exc)
            raise SecurityExecutionError('安全频率检查失败，详情已记录到安全日志') from exc
        except Exception as exc:
            await self._save_failure(prepare, state, details, execution_id, owner_id, method, started_at, exc)
            raise SecurityExecutionError('安全频率检查失败，详情已记录到安全日志') from exc
        log_error = report_safely('安全检查执行结果 ' + json.dumps(response, ensure_ascii=False), level='INFO')
        if log_error:
            raise SecurityExecutionError(f'安全检查及审计已提交，{log_error}，请查询安全日志确认')
        return response

    async def _save_failure(self, prepare, state, details, execution_id, owner_id, method, started_at, exc):
        """业务回滚后独立会话重新取锁，失败日志和释放业务占用同事务提交。"""
        details['error'] = {'type': type(exc).__name__, 'message': str(exc),
                            'traceback': ''.join(traceback.format_exception(exc))}
        file_error = report_safely('安全检查失败 ' + json.dumps(details, ensure_ascii=False), exc)
        if file_error:
            details['file_log_error'] = file_error

        async def write(session):
            """只追加真实失败，实际新增为空，候选完整保留。"""
            return await self._append_result(session, state['task'], details, execution_id, owner_id,
                                             method, 'failed', '安全频率检查失败：' + str(exc), [], [], started_at)

        try:
            response = await self.writer.write(write, prepare=prepare, context=lambda: json.dumps(details, ensure_ascii=False))
        except AuditWriteError as audit_error:
            reason = '失败审计提交结果未知，未重复写入' if audit_error.commit_unknown else str(audit_error)
            raise SecurityExecutionError(f'安全检查失败且审计未能确认，执行编号{execution_id}：{reason}') from audit_error
        # 审计重试及提交期间也可能产生文件故障，落库后排空输出并向用户明确报告。
        audit_file_error = report_safely('安全检查失败审计已提交 ' + json.dumps(response, ensure_ascii=False), level='INFO')
        if file_error or audit_file_error:
            errors = '; '.join(error for error in (file_error, audit_file_error) if error)
            raise SecurityExecutionError(f'失败审计已提交，{errors}') from exc

    async def _append_result(self, session, task, details, execution_id, owner_id, method,
                             result, message, suffixes, ips, started_at) -> dict:
        """追加审计并保存真实业务结果，同一事务提交后才向调用方返回。"""
        finished = get_beijing_now_naive()
        details['finished_at'] = finished.isoformat()
        record = SecurityLog(execution_id=execution_id, owner_id=owner_id, execution_method=method,
                             result=result, message=message, added_suffixes=','.join(suffixes),
                             added_ips=','.join(ips), details=json.dumps(details, ensure_ascii=False),
                             started_at=started_at, finished_at=finished)
        session.add(record)
        task.last_run_at, task.last_result, task.last_message = started_at, result, message
        task.lease_id = task.lease_expires_at = None
        task.updated_at = finished
        await session.flush()
        return {'id': record.id, 'execution_id': execution_id, 'result': result, 'message': message,
                'added_suffixes': suffixes, 'added_ips': ips, 'started_at': started_at.isoformat(),
                'finished_at': finished.isoformat()}


security_frequency_service = SecurityFrequencyService()
