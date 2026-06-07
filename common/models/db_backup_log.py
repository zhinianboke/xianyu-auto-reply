"""
数据库备份日志模型

功能：
1. 定义数据库备份日志表结构（xy_db_backup_log）
2. 记录每一次数据库备份任务的执行结果（成功/失败）
3. 记录备份文件名、存储路径、文件大小、备份的表数量与数据行数，供前端展示与下载
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class DbBackupLog(TimestampMixin, Base):
    """数据库备份日志表"""

    __tablename__ = "xy_db_backup_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 备份结果状态：success（成功）/ failed（失败）
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="状态：success/failed")
    # 备份文件名（仅文件名，下载时由后端结合备份目录解析为真实路径）
    file_name: Mapped[str | None] = mapped_column(String(255), comment="备份文件名")
    # 备份文件绝对路径（生成时所在机器/容器的路径，仅作记录展示）
    file_path: Mapped[str | None] = mapped_column(String(500), comment="备份文件绝对路径")
    # 备份文件大小（字节）
    file_size: Mapped[int | None] = mapped_column(BigInteger, comment="备份文件大小(字节)")
    # 本次备份涉及的数据表数量
    table_count: Mapped[int | None] = mapped_column(Integer, comment="备份的数据表数量")
    # 本次备份导出的数据总行数
    total_rows: Mapped[int | None] = mapped_column(BigInteger, comment="备份的数据总行数")
    # 备份耗时（毫秒）
    duration_ms: Mapped[int | None] = mapped_column(Integer, comment="备份耗时(毫秒)")
    # 失败时的错误信息
    error_message: Mapped[str | None] = mapped_column(String(1000), comment="错误信息")
