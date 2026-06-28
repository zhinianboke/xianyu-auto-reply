"""
返佣系统 - 选品规则模型

功能：
1. 定义选品规则表结构（fy_product_rules）
2. 存储按类目/关键词自动选品的规则
3. 关联用户表（xy_users）
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class FYProductRule(TimestampMixin, Base):
    """返佣系统选品规则表"""

    __tablename__ = "fy_product_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户ID")
    account_id: Mapped[str | None] = mapped_column(String(80), index=True, comment="闲鱼账号ID（xy_accounts.account_id）")
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="规则名称")
    cat: Mapped[str | None] = mapped_column(String(50), comment="商品类目ID")
    cat_name: Mapped[str | None] = mapped_column(String(100), comment="商品类目名称（冗余存储便于展示）")
    keyword: Mapped[str | None] = mapped_column(String(200), comment="商品关键词")
    sort: Mapped[str] = mapped_column(String(50), default="default", server_default="default", comment="排序规则")
    daily_count: Mapped[int] = mapped_column(Integer, default=10, server_default="10", comment="每天选品条数")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", comment="是否启用")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后执行时间")
    last_run_date: Mapped[date | None] = mapped_column(Date, comment="最后执行日期（用于判断今天是否已完成）")
    today_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="今天已选品数量")
    total_selected_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="累计选品数量")

    # 关系定义 - 无外键约束，通过代码控制数据一致性
    owner: Mapped["User"] = relationship(
        "User",
        primaryjoin="FYProductRule.owner_id == User.id",
        foreign_keys="[FYProductRule.owner_id]",
        viewonly=True,
    )
