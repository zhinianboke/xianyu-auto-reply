"""
返佣系统 - 删除规则模型

功能：
1. 定义删除规则表结构（fy_delete_rules）
2. 存储按账号自动删除闲鱼商品的规则配置
3. 包含闲鱼账号ID、每日删除数量、今日已删除数量等
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class FYDeleteRule(TimestampMixin, Base):
    """返佣系统删除规则表"""

    __tablename__ = "fy_delete_rules"
    __table_args__ = (
        UniqueConstraint("owner_id", "account_id", name="uq_fy_delete_rules_owner_account"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户ID")
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="规则名称")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, comment="闲鱼账号ID（xy_accounts.account_id）")
    daily_count: Mapped[int] = mapped_column(Integer, default=5, server_default="5", comment="每天删除数量")
    min_publish_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7", comment="发布满多少天才能删除")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", comment="是否启用")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后执行时间")
    last_run_date: Mapped[date | None] = mapped_column(Date, comment="最后执行日期（用于判断今天是否已完成）")
    today_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="今天已删除数量")
    total_deleted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="累计删除数量")

    # 关系定义 - 无外键约束，通过代码控制数据一致性
    owner: Mapped["User"] = relationship(
        "User",
        primaryjoin="FYDeleteRule.owner_id == User.id",
        foreign_keys="[FYDeleteRule.owner_id]",
        viewonly=True,
    )
