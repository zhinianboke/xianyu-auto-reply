"""通用展示入口模板模型（用户级，供提货页默认合并与商品配置快速选用）。"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class DisplayLinkTemplate(TimestampMixin, Base):
    """通用展示入口模板 - 与商品级 display_links 条目同构"""

    __tablename__ = "xy_display_link_templates"
    __table_args__ = (
        Index("idx_dlt_user_default", "user_id", "is_default"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="模板ID")
    # 不单独建 user_id 索引：建表 DDL 只有复合索引 idx_dlt_user_default(user_id, is_default)，
    # 其前缀已覆盖按 user_id 的查询；此处加 index=True 会与线上表结构不一致
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属用户ID")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="入口名称")
    type: Mapped[str] = mapped_column(String(16), nullable=False, comment="类型：link/text/image")
    url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="链接/图片地址")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="右侧备注")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="文本弹窗标题")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文本弹窗内容")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
        comment="默认展示：提货页读取时自动合并到所有商品",
    )
