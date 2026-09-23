"""
AI 铺货任务模型

功能：
1. 定义 AI 铺货任务主表结构（xy_ai_listing_tasks），进度与结果落库，服务重启可恢复
2. 定义 AI 铺货任务明细表结构（xy_ai_listing_task_items），逐条记录生成结果与失败原因
3. 状态常量与归一化工具，供 service 与路由复用
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


# ==================== 状态常量 ====================

# 任务状态：等待中 / 执行中 / 全部成功 / 部分成功 / 全部失败 / 已取消
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_PARTIAL = "partial"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELED = "canceled"

# 未结束状态集合（用于并发闸门与重启清理）
TASK_ACTIVE_STATUSES = (TASK_STATUS_PENDING, TASK_STATUS_RUNNING)

# 明细状态
ITEM_STATUS_PENDING = "pending"
ITEM_STATUS_RUNNING = "running"
ITEM_STATUS_SUCCESS = "success"
ITEM_STATUS_FAILED = "failed"

# 失败原因入库长度上限，与 xy_publish_logs.error_message 保持一致
ERROR_MESSAGE_MAX_LENGTH = 1000


def truncate_error_message(message: object) -> str:
    """把任意异常/文本裁剪成可入库的失败原因（最多 1000 字符）"""
    return str(message or "")[:ERROR_MESSAGE_MAX_LENGTH]


class AiListingTask(TimestampMixin, Base):
    """AI 铺货任务主表 - 记录一次批量生成的整体进度"""

    __tablename__ = "xy_ai_listing_tasks"
    __table_args__ = (
        Index("idx_alt_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="归属用户（本系统用户ID）")
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, comment="任务ID（UUID）")
    config_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="使用的AI铺货配置ID")
    config_name: Mapped[str | None] = mapped_column(String(80), comment="配置名称快照（配置改名或删除后仍可读）")
    keyword: Mapped[str] = mapped_column(String(200), nullable=False, comment="生成主题/关键词")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="计划生成条数")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已成功条数")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已失败条数")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TASK_STATUS_PENDING,
        comment="状态：pending/running/success/partial/failed/canceled",
    )
    error_message: Mapped[str | None] = mapped_column(String(1000), comment="整体失败原因")
    params: Mapped[dict | None] = mapped_column(JSON, comment="提交参数快照（价格模式、素材默认值等）")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, comment="执行结束时间")
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否已删除（软删除）"
    )


class AiListingTaskItem(TimestampMixin, Base):
    """AI 铺货任务明细表 - 每条素材一行，便于回查失败原因"""

    __tablename__ = "xy_ai_listing_task_items"
    __table_args__ = (
        Index("idx_alti_task_status", "task_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="所属任务ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="归属用户（本系统用户ID）")
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="序号（从1开始）")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ITEM_STATUS_PENDING,
        comment="状态：pending/running/success/failed",
    )
    title: Mapped[str | None] = mapped_column(String(200), comment="生成的商品标题")
    material_id: Mapped[int | None] = mapped_column(BigInteger, comment="入库后的素材ID")
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本条素材图片数量")
    error_message: Mapped[str | None] = mapped_column(String(1000), comment="失败原因")
