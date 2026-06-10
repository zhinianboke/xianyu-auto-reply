"""在线聊天工作台使用的快捷短语模型"""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ChatQuickPhrase(TimestampMixin, Base):
    """归属于单个后台用户的可复用快捷短语"""

    __tablename__ = "xy_chat_quick_phrases"
    __table_args__ = (
        Index("idx_chat_quick_phrase_owner_sort", "owner_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="归属用户（本系统用户ID）")
    title: Mapped[str] = mapped_column(String(80), nullable=False, comment="短语标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="短语内容（发送的文本）")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值，越小越靠前")
