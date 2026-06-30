"""
兜底私信账号配置模型

功能：
1. 定义用户级兜底私信账号配置表结构（xy_dm_fallback_accounts）
2. 每个用户每个分类一条记录（owner_id, category_id 联合唯一）
3. 当商品真实下单成功的账号发私信不可用时，私信任务回退使用此处配置的账号发私信
4. category_id = NULL 表示"未分类"的全局兜底账号
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class DmFallbackAccount(TimestampMixin, Base):
    """用户级兜底私信账号配置表（按分类配置）"""

    __tablename__ = "xy_dm_fallback_accounts"
    __table_args__ = (
        Index("uk_dfa_owner_category", "owner_id", "category_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="归属用户ID")
    category_id: Mapped[int | None] = mapped_column(BigInteger, comment="所属分类ID（NULL=未分类全局兜底）")
    account_ids: Mapped[list | None] = mapped_column(JSON, comment="兜底私信账号ID列表（JSON数组，多选轮换使用）")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已删除（软删除）")
