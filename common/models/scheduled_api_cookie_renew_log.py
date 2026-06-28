"""
接口续期Cookies执行日志模型

功能：
1. 定义接口续期Cookies执行日志表结构（xy_scheduled_api_cookie_renew_log）
2. 记录每次定时任务通过 hasLogin.do 接口续期Cookies的执行结果
3. 支持按批次ID查询同一次定时任务的所有日志
4. 详细记录失败时的接口返回值，以及Cookie被更新时具体更新了哪些键
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledApiCookieRenewLog(TimestampMixin, Base):
    """接口续期Cookies执行日志表。"""

    __tablename__ = "xy_scheduled_api_cookie_renew_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    batch_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, comment="批次ID，标识一次定时任务执行"
    )
    account_id: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True, comment="账号ID"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="状态：success/cookie_updated/browser_renewed/need_password_login/failed"
    )
    updated_cookie_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次更新的Cookie字段数量"
    )
    updated_cookie_names: Mapped[str | None] = mapped_column(
        Text, comment="本次更新的Cookie字段名列表（逗号分隔）"
    )
    response_content: Mapped[str | None] = mapped_column(
        Text, comment="接口返回内容（用于失败排查），最大裁剪到 2000 字符"
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500), comment="错误信息或处理说明"
    )
