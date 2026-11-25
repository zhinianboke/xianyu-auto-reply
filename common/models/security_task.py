"""安全执行状态模型：保留历史字段，任务配置统一由xy_scheduled_tasks管理。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base

SECURITY_TASK_CODE = 'security_frequency'
SECURITY_INTERVAL_SECONDS = 20
SECURITY_SCAN_TIMEOUT_SECONDS = 60
SECURITY_LEASE_SECONDS = 180
SECURITY_METHODS = ('auto', 'manual')
SECURITY_RESULTS = ('success', 'no_violation', 'disabled', 'failed')
SECURITY_DICTIONARIES = {
    'security_execution_method': (('auto', '自动执行'), ('manual', '手动执行')),
    'security_execution_result': (('success', '执行成功'), ('no_violation', '无违规'),
                                  ('disabled', '全部档位关闭'), ('failed', '执行失败')),
    'security_task_name': ((SECURITY_TASK_CODE, '安全频率限制'),),
}


class SecurityTask(Base):
    """安全业务状态；enabled、interval_seconds和next_run_at保留旧值，不作为调度来源。"""

    __tablename__ = 'security_tasks'
    __table_args__ = (UniqueConstraint('task_code', name='uk_security_task_code'),
                      {'comment': '安全定时任务表', 'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='安全任务ID')
    task_code: Mapped[str] = mapped_column(String(64), nullable=False, comment='任务代码，关联任务名称字典')
    interval_seconds: Mapped[int] = mapped_column(Integer, default=SECURITY_INTERVAL_SECONDS,
                                                server_default=str(SECURITY_INTERVAL_SECONDS), comment='执行间隔秒数')
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0',
                                        comment='是否启用自动安全检查，默认停止')
    config_version: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment='安全配置版本')
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, comment='下次执行北京时间')
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, comment='上次执行开始北京时间')
    last_result: Mapped[str | None] = mapped_column(String(32), comment='上次结果，关联执行结果字典')
    last_message: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'), comment='上次执行说明')
    lease_id: Mapped[str | None] = mapped_column(String(64), comment='本轮持久化占用执行编号')
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, comment='占用到期北京时间')
    created_at: Mapped[datetime | None] = mapped_column(DateTime, comment='创建北京时间')
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, comment='更新北京时间')
