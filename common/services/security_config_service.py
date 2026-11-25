"""安全配置共享锁与版本：所有安全保存和自动封禁复用同一数据库任务行锁。"""
from __future__ import annotations

from sqlalchemy import select, update

from common.db.idempotent_insert import insert_defaults
from common.models.security_task import (
    SECURITY_INTERVAL_SECONDS,
    SECURITY_TASK_CODE,
    SecurityTask,
)
from common.models.system_setting import SystemSetting
from common.services.auth_security_policy import (
    AUTH_SECURITY_DEFAULTS,
    AUTH_SECURITY_GROUP,
)
from common.utils.time_utils import get_beijing_now_naive


async def lock_security_task(session) -> SecurityTask:
    """取得事务锁并刷新ORM对象；SQLite先争取写锁，避免延迟读事务升级死锁。"""
    if session.get_bind().dialect.name == 'sqlite':
        await session.execute(update(SecurityTask).where(SecurityTask.task_code == SECURITY_TASK_CODE)
                              .values(config_version=SecurityTask.config_version))
    task = (await session.execute(select(SecurityTask).where(SecurityTask.task_code == SECURITY_TASK_CODE)
                                  .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if task is None:
        raise RuntimeError('安全频率任务尚未初始化，请联系管理员完成数据库自检')
    return task


async def ensure_security_defaults(connection) -> None:
    """并发幂等补任务及安全项；已有非法配置保留原值，交由管理员修正。"""
    now = get_beijing_now_naive()
    await insert_defaults(connection, SecurityTask.__table__, {
        'task_code': SECURITY_TASK_CODE, 'interval_seconds': SECURITY_INTERVAL_SECONDS, 'config_version': 0,
        'enabled': False, 'next_run_at': None, 'created_at': now, 'updated_at': now,
    }, ('task_code',))
    for key, (value, description) in AUTH_SECURITY_DEFAULTS.items():
        await insert_defaults(connection, SystemSetting.__table__, {
            'key': key, 'value': value, 'description': description,
            'group': AUTH_SECURITY_GROUP, 'updated_at': now,
        }, ('key',))


async def save_security_values(session, task: SecurityTask, changes: dict[str, str]) -> None:
    """锁内只更新提交或实际追加的安全字段并递增版本，不提交调用方事务。"""
    current = await load_security_values_locked(session)
    changed = False
    for key, value in changes.items():
        if current.get(key) == value:
            continue
        await insert_defaults(session, SystemSetting.__table__, {
            'key': key, 'value': value, 'description': AUTH_SECURITY_DEFAULTS[key][1],
            'group': AUTH_SECURITY_GROUP, 'updated_at': get_beijing_now_naive(),
        }, ('key',))
        await session.execute(update(SystemSetting).where(SystemSetting.key == key).values(
            value=value, group=AUTH_SECURITY_GROUP, updated_at=get_beijing_now_naive()))
        changed = True
    if changed:
        task.config_version = (task.config_version or 0) + 1
        task.updated_at = get_beijing_now_naive()


async def load_security_values_locked(session) -> dict[str, str]:
    """锁内使用当前读，避免认证依赖已开启的MySQL旧快照覆盖最新后台追加值。"""
    return dict((await session.execute(select(SystemSetting.key, SystemSetting.value).where(
        SystemSetting.key.in_(tuple(AUTH_SECURITY_DEFAULTS))).with_for_update())).all())
