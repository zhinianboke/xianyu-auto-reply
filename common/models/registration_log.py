"""独立注册审计模型：记录注册提交和明确注册用途的验证码尝试，只追加不删除。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base
from common.utils.time_utils import get_beijing_now_naive

REGISTRATION_OPERATION_SUBMIT = "register_submit"
REGISTRATION_OPERATION_CODE = "register_code"
REGISTRATION_OPERATION_DICTIONARY = "registration_operation"
REGISTRATION_STATUS_DICTIONARY = "registration_status"
REGISTRATION_OPERATIONS = (REGISTRATION_OPERATION_SUBMIT, REGISTRATION_OPERATION_CODE)
REGISTRATION_STATUSES = ("success", "failed")


class RegistrationLog(Base):
    """注册日志表；非法、超长输入使用长文本保存，禁止外键和历史记录更新。"""

    __tablename__ = "api_registration_logs"
    __table_args__ = (
        Index("idx_rl_created_id", "created_at", "id"),
        Index("idx_rl_owner_created_id", "owner_id", "created_at", "id"),
        Index("idx_rl_operation_created_id", "operation", "created_at", "id"),
        Index("idx_rl_success_created_id", "success", "created_at", "id"),
        {
            "comment": "注册日志表",
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="注册日志ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联用户ID，无法真实定位时为空")
    username: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), comment="提交用户名")
    email: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), comment="注册邮箱")
    operation: Mapped[str] = mapped_column(String(32), nullable=False, comment="注册操作，取值来自注册操作字典")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否成功，取值对应注册结果字典")
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="经可信代理校验的客户端IP")
    message: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), comment="真实结果说明或失败原因")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=get_beijing_now_naive,
        server_default=func.now(), comment="发生时间，北京时间",
    )


__all__ = [
    "REGISTRATION_OPERATIONS",
    "REGISTRATION_OPERATION_CODE",
    "REGISTRATION_OPERATION_DICTIONARY",
    "REGISTRATION_OPERATION_SUBMIT",
    "REGISTRATION_STATUSES",
    "REGISTRATION_STATUS_DICTIONARY",
    "RegistrationLog",
]
