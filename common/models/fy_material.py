"""
返佣系统 - 素材库模型

功能：
1. 定义素材库表结构（fy_materials）
2. 存储定时任务从选品规则获取的商品素材
3. 包含商品标题、售价、描述、图片、推广链接、淘口令等
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin

PUBLISH_STATUS_UNPUBLISHED = "unpublished"
PUBLISH_STATUS_PUBLISHED = "published"
PUBLISH_STATUS_FAILED = "failed"
VALID_PUBLISH_STATUS_VALUES = {
    PUBLISH_STATUS_UNPUBLISHED,
    PUBLISH_STATUS_PUBLISHED,
    PUBLISH_STATUS_FAILED,
}


def normalize_publish_status(value: str | None, published: bool | None = None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_PUBLISH_STATUS_VALUES:
        return normalized
    if published is True:
        return PUBLISH_STATUS_PUBLISHED
    return PUBLISH_STATUS_UNPUBLISHED


class FYMaterial(TimestampMixin, Base):
    """返佣系统素材库表"""

    __tablename__ = "fy_materials"
    __table_args__ = (
        Index("idx_fy_material_owner", "owner_id"),
        Index("idx_fy_material_account", "account_id"),
        Index("idx_fy_material_owner_account_publish_status", "owner_id", "account_id", "publish_status"),
        Index("idx_fy_material_rule", "rule_id"),
        Index("idx_fy_material_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, comment="所属用户ID")
    account_id: Mapped[str | None] = mapped_column(String(80), comment="闲鱼账号ID（xy_accounts.account_id）")
    rule_id: Mapped[int | None] = mapped_column(BigInteger, comment="来源选品规则ID")
    item_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="淘宝商品ID")
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="商品标题")
    price: Mapped[float] = mapped_column(Numeric(10, 2), default=0.1, server_default="0.10", comment="售价（默认0.1）")
    stock: Mapped[int] = mapped_column(Integer, default=999, server_default="999", comment="库存")
    description: Mapped[str | None] = mapped_column(Text, comment="商品描述")
    images: Mapped[str | None] = mapped_column(Text, comment="商品图片URL列表（JSON数组）")
    click_url: Mapped[str | None] = mapped_column(String(1000), comment="推广链接")
    coupon_url: Mapped[str | None] = mapped_column(String(1000), comment="券二合一推广链接")
    tpwd: Mapped[str | None] = mapped_column(String(200), comment="淘口令")
    short_url: Mapped[str | None] = mapped_column(String(1000), comment="短连接")
    original_price: Mapped[str | None] = mapped_column(String(20), comment="商品原价")
    commission_rate: Mapped[str | None] = mapped_column(String(20), comment="佣金率")
    commission_amount: Mapped[str | None] = mapped_column(String(20), comment="佣金金额")
    promotion_price: Mapped[str | None] = mapped_column(String(20), comment="到手价")
    coupon_info: Mapped[str | None] = mapped_column(String(255), comment="优惠券信息")
    shop_title: Mapped[str | None] = mapped_column(String(200), comment="店铺名称")
    volume: Mapped[str | None] = mapped_column(String(50), comment="月销量")
    publish_status: Mapped[str] = mapped_column(
        String(20),
        default=PUBLISH_STATUS_UNPUBLISHED,
        server_default=PUBLISH_STATUS_UNPUBLISHED,
        comment="发布状态",
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已发布到闲鱼")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="发布时间")
    published_item_id: Mapped[str | None] = mapped_column(String(64), comment="发布后闲鱼商品ID")
    publish_random_str: Mapped[str | None] = mapped_column(String(32), comment="发布随机字符")

    # 关系定义 - 无外键约束
    owner: Mapped["User"] = relationship(
        "User",
        primaryjoin="FYMaterial.owner_id == User.id",
        foreign_keys="[FYMaterial.owner_id]",
        viewonly=True,
    )
