"""
返佣系统 - 发布规则模型

功能：
1. 定义发布规则表结构（fy_publish_rules）
2. 存储自动发布到闲鱼的规则配置
3. 包含闲鱼账号ID、每日发布数量、今日已发布数量等
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class FYPublishRule(TimestampMixin, Base):
    """返佣系统发布规则表"""

    __tablename__ = "fy_publish_rules"
    __table_args__ = (
        UniqueConstraint("owner_id", "account_id", name="uq_fy_publish_rules_owner_account"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户ID")
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="规则名称")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, comment="闲鱼账号ID（xy_accounts.account_id）")
    daily_count: Mapped[int] = mapped_column(Integer, default=5, server_default="5", comment="每天发布数量")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", comment="是否启用")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后执行时间")
    last_run_date: Mapped[date | None] = mapped_column(Date, comment="最后执行日期（用于判断今天是否已完成）")
    today_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="今天已发布数量")

    # 关系定义 - 无外键约束，通过代码控制数据一致性
    owner: Mapped["User"] = relationship(
        "User",
        primaryjoin="FYPublishRule.owner_id == User.id",
        foreign_keys="[FYPublishRule.owner_id]",
        viewonly=True,
    )
