"""
关键词规则模型

功能：
1. 定义关键词规则表结构（xy_keyword_rules）
2. 支持文本和图片两种回复类型
3. 支持精确匹配和模糊匹配
4. 可绑定到特定商品或作为通用规则
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class XYKeywordRule(TimestampMixin, Base):
    """关键词规则表 - 存储账号的自动回复关键词配置"""

    __tablename__ = "xy_keyword_rules"
    __table_args__ = (
        # 复合索引：加速 list_keywords 的 (account_pk, item_id) JOIN 查询
        Index("idx_kw_account_item", "account_id", "item_id"),
        Index("idx_kw_account_active", "account_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    account_pk: Mapped[int | None] = mapped_column(
        "account_id",
        BigInteger,
        nullable=True,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(120), nullable=False)
    reply_content: Mapped[str | None] = mapped_column(Text)
    reply_type: Mapped[str | None] = mapped_column(String(16))
    image_url: Mapped[str | None] = mapped_column(String(512))
    item_id: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    account: Mapped["XYAccount"] = relationship(
        "XYAccount",
        primaryjoin="XYKeywordRule.account_pk == XYAccount.id",
        foreign_keys="[XYKeywordRule.account_pk]",
        back_populates="keyword_rules",
        viewonly=True,
    )

