"""
账号登录日志模型

功能：
1. 定义账号登录日志表结构（xy_account_login_logs）
2. 记录 WebSocket 侧账号密码登录的每一次尝试与最终结果
3. 跟踪登录触发原因、最终状态、失败大类、详细错误消息、耗时

设计要点：
- 每个账号每触发一次 try_password_login_refresh 写入一条日志
- login_status: success / failed / skipped_cooldown / no_credentials
- failure_reason: bad_credentials / baxia_punish_captcha / account_info_missing /
                  cookie_already_updated / cookie_update_failed / exception / other
- 支持按 owner_id / account_identifier / 时间范围 / login_status 筛选
- 与风控日志（xy_risk_control_logs）独立，互不影响
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYAccountLoginLog(Base):
    """账号登录日志表 - 记录账号密码登录每一次尝试与结果"""

    __tablename__ = "xy_account_login_logs"
    __table_args__ = (
        Index("idx_all_identifier_status_created", "account_identifier", "login_status", "created_at"),
        Index("idx_all_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属用户ID")
    # 关联 xy_accounts.id（数据库主键），无外键约束，靠代码控制
    account_pk: Mapped[int | None] = mapped_column(
        "account_id",
        BigInteger,
        nullable=True,
        index=True,
        comment="关联账号ID（xy_accounts.id）",
    )
    # 业务账号ID（与风控日志命名保持一致）
    account_identifier: Mapped[str | None] = mapped_column(String(80), comment="业务账号ID")
    # 闲鱼登录用户名（来自 xy_accounts.username，登录尝试时的快照，便于排查）
    username: Mapped[str | None] = mapped_column(String(255), comment="登录用户名快照")
    # 触发本次登录的原因，例如 "Session过期" / "令牌过期" / "手动重启"
    trigger_reason: Mapped[str | None] = mapped_column(String(128), comment="触发本次登录的原因")
    # 登录状态：
    # - success: 密码登录成功并获取到新 Cookie
    # - failed: 登录失败（账密错误、风控、超时等真实失败）
    # - skipped_cooldown: 处于冷却期被跳过（不是失败，是已知可恢复状态）
    # - no_credentials: 未配置账号或密码
    login_status: Mapped[str] = mapped_column(String(32), default="failed", comment="登录状态：success/failed/skipped_cooldown/no_credentials")
    # 失败大类标签（便于聚合统计），具体含义见 failure_reason 枚举
    failure_reason: Mapped[str | None] = mapped_column(String(64), comment="失败大类：bad_credentials/baxia_punish_captcha/account_info_missing/exception/...")
    # 详细错误消息（完整异常信息或风控提示文案）
    error_message: Mapped[str | None] = mapped_column(Text, comment="详细错误消息")
    # 接口续期时更新的Cookie字段名列表（逗号分隔，如 havana_lgc2_77,_hvn_lgc_,havana_lgc_exp）
    updated_cookie_names: Mapped[str | None] = mapped_column(String(500), comment="接口续期更新的Cookie字段名（逗号分隔）")
    # 整个登录流程耗时（毫秒），从函数进入到返回为止
    duration_ms: Mapped[int | None] = mapped_column(Integer, comment="整个登录流程耗时（毫秒）")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间",
    )
