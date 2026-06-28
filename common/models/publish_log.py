"""
商品发布日志模型

功能：
1. 定义商品发布日志表结构（xy_publish_logs）
2. 记录每次发布操作的结果（成功/失败/进行中）
3. 支持单品发布和批量发布任务的日志记录
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class PublishLog(TimestampMixin, Base):
    """商品发布日志表 - 记录每次发布操作的结果"""

    __tablename__ = "xy_publish_logs"
    __table_args__ = (
        Index("idx_publish_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="操作用户ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="闲鱼账号ID（cookie_id）")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="商品标题")
    description: Mapped[str | None] = mapped_column(Text, comment="商品描述")
    price: Mapped[str | None] = mapped_column(String(20), comment="发布价格")
    material_id: Mapped[int | None] = mapped_column(BigInteger, comment="关联的素材ID（批量发布时使用）")
    batch_id: Mapped[str | None] = mapped_column(String(36), index=True, comment="批次ID（批量发布任务标识）")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", comment="状态：pending/publishing/success/failed")
    item_url: Mapped[str | None] = mapped_column(String(500), comment="发布成功后的商品链接")
    item_id: Mapped[str | None] = mapped_column(String(64), comment="发布成功后的商品ID")
    error_message: Mapped[str | None] = mapped_column(String(1000), comment="失败原因")
    resolved_address_id: Mapped[int | None] = mapped_column(BigInteger, comment="本次发布命中的地址池ID")
    resolved_address_text: Mapped[str | None] = mapped_column(String(200), comment="本次发布实际使用的地址搜索词")
    address_source: Mapped[str | None] = mapped_column(String(20), comment="地址来源：material/account_pool/global_pool/personal_pool")
