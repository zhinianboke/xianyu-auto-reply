"""安全日志模型：只追加每次真实执行结果与完整统计，候选和实际新增分开记录。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class SecurityLog(Base):
    """安全日志表，不提供更新、删除或历史补造方法，不使用外键。"""

    __tablename__ = 'security_logs'
    __table_args__ = (
        UniqueConstraint('execution_id', name='uk_security_log_execution'),
        Index('idx_security_log_started_id', 'started_at', 'id'),
        Index('idx_security_log_result_started', 'result', 'started_at', 'id'),
        Index('idx_security_log_method_started', 'execution_method', 'started_at', 'id'),
        {'comment': '安全日志表', 'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True,
                                  autoincrement=True, comment='安全日志ID')
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='唯一执行编号')
    owner_id: Mapped[int | None] = mapped_column(BigInteger, comment='手动执行管理员ID，自动为空')
    execution_method: Mapped[str] = mapped_column(String(32), nullable=False, comment='执行方式，关联字典')
    result: Mapped[str] = mapped_column(String(32), nullable=False, comment='真实执行结果，关联字典')
    message: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'), comment='结果说明')
    added_suffixes: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'), comment='实际新增违规后缀')
    added_ips: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'), comment='实际新增违规IP')
    details: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, 'mysql'), comment='完整统计窗口、候选与阈值快照JSON')
    started_at: Mapped[datetime] = mapped_column(DateTime, comment='执行开始北京时间')
    finished_at: Mapped[datetime] = mapped_column(DateTime, comment='执行结束北京时间')
