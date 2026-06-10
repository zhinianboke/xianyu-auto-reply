from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_reply_stats_service import AutoReplyStatsService
from common.models.auto_reply_message_log import XYAutoReplyMessageLog


from common.utils.time_utils import safe_isoformat
class AutoReplyLogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _serialize_log_row(row) -> dict:
        return {
            "id": row["id"],
            "owner_id": row["owner_id"],
            "owner_username": row["owner_username"],
            "account_pk": row["account_pk"],
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "chat_id": row["chat_id"],
            "item_id": row["item_id"],
            "item_title": row["item_title"],
            "source_message_id": row["source_message_id"],
            "sender_user_id": row["sender_user_id"],
            "sender_user_name": row["sender_user_name"],
            "source_message": row["source_message"],
            "source_message_time": safe_isoformat(row["source_message_time"]),
            "process_status": row["process_status"],
            "decision_reason": row["decision_reason"],
            "reply_strategy": row["reply_strategy"],
            "reply_mode": row["reply_mode"],
            "matched_keyword": row["matched_keyword"],
            "matched_rule_type": row["matched_rule_type"],
            "default_reply_scope": row["default_reply_scope"],
            "default_reply_once": bool(row["default_reply_once"]),
            "ai_model_name": row["ai_model_name"],
            "ai_provider_name": row["ai_provider_name"],
            "reply_text": row["reply_text"],
            "reply_image_url": row["reply_image_url"],
            "error_message": row["error_message"],
            "send_status": row["send_status"],
            "send_fail_reason": row["send_fail_reason"],
            "created_at": safe_isoformat(row["created_at"]),
            "updated_at": safe_isoformat(row["updated_at"]),
        }

    @staticmethod
    def _build_auto_delivery_conditions(
        *,
        owner_id: int | None = None,
        account_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        """构建自动发货明细查询条件（reply_strategy == 'auto_delivery'）

        与自动回复不同：成功/失败均展示，不限制 process_status。
        """
        conditions = [XYAutoReplyMessageLog.reply_strategy == "auto_delivery"]
        if owner_id is not None:
            conditions.append(XYAutoReplyMessageLog.owner_id == owner_id)
        if account_id and account_id.strip():
            conditions.append(XYAutoReplyMessageLog.account_id == account_id.strip())
        if start_time is not None:
            conditions.append(XYAutoReplyMessageLog.created_at >= start_time)
        if end_time is not None:
            conditions.append(XYAutoReplyMessageLog.created_at < end_time)
        return conditions

    def _parse_start_time(self, start_date: str | None) -> datetime | None:
        if not start_date:
            return None
        try:
            return datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("开始日期格式错误，应为 YYYY-MM-DD") from exc

    def _parse_end_time(self, end_date: str | None) -> datetime | None:
        if not end_date:
            return None
        try:
            return datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        except ValueError as exc:
            raise ValueError("结束日期格式错误，应为 YYYY-MM-DD") from exc

    async def list_logs(
        self,
        *,
        owner_id: int | None = None,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        matched_rule_type: str | None = None,
        send_status: str | None = None,
        message_type: str = "auto_reply",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        start_time = self._parse_start_time(start_date)
        end_time = self._parse_end_time(end_date)
        if start_time is not None and end_time is not None and start_time >= end_time:
            raise ValueError("开始日期不能大于结束日期")

        if message_type == "auto_delivery":
            # 自动发货明细：reply_strategy == 'auto_delivery'，成功/失败都展示
            branch_conditions = [
                self._build_auto_delivery_conditions(
                    owner_id=owner_id,
                    account_id=account_id,
                    start_time=start_time,
                    end_time=end_time,
                )
            ]
        else:
            branch_conditions = AutoReplyStatsService.build_success_reply_branch_conditions(
                owner_id=owner_id,
                account_ids=[account_id] if account_id else None,
                start_time=start_time,
                end_time=end_time,
            )

            # 追加 matched_rule_type 筛选条件（仅自动回复支持规则类型筛选）
            if matched_rule_type:
                branch_conditions = [
                    [*conds, XYAutoReplyMessageLog.matched_rule_type == matched_rule_type]
                    for conds in branch_conditions
                ]

        # 追加发送状态筛选条件（自动回复、自动发货均支持）
        if send_status and send_status.strip():
            branch_conditions = [
                [*conds, XYAutoReplyMessageLog.send_status == send_status.strip()]
                for conds in branch_conditions
            ]

        total = 0
        for current_conditions in branch_conditions:
            count_stmt = select(func.count()).select_from(XYAutoReplyMessageLog).where(*current_conditions)
            total += int((await self.session.execute(count_stmt)).scalar() or 0)

        page_source_subquery = union_all(
            *[
                select(
                    XYAutoReplyMessageLog.id.label("id"),
                    XYAutoReplyMessageLog.created_at.label("created_at"),
                ).where(*current_conditions)
                for current_conditions in branch_conditions
            ]
        ).subquery()

        page_ids_stmt = (
            select(page_source_subquery.c.id)
            .order_by(
                page_source_subquery.c.created_at.desc(),
                page_source_subquery.c.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        page_id_rows = (await self.session.execute(page_ids_stmt)).all()
        log_ids = [int(row[0]) for row in page_id_rows]
        if not log_ids:
            return [], int(total)

        stmt = (
            select(
                XYAutoReplyMessageLog.id.label("id"),
                XYAutoReplyMessageLog.owner_id.label("owner_id"),
                XYAutoReplyMessageLog.owner_username.label("owner_username"),
                XYAutoReplyMessageLog.account_pk.label("account_pk"),
                XYAutoReplyMessageLog.account_id.label("account_id"),
                XYAutoReplyMessageLog.account_name.label("account_name"),
                XYAutoReplyMessageLog.chat_id.label("chat_id"),
                XYAutoReplyMessageLog.item_id.label("item_id"),
                XYAutoReplyMessageLog.item_title.label("item_title"),
                XYAutoReplyMessageLog.source_message_id.label("source_message_id"),
                XYAutoReplyMessageLog.sender_user_id.label("sender_user_id"),
                XYAutoReplyMessageLog.sender_user_name.label("sender_user_name"),
                XYAutoReplyMessageLog.source_message.label("source_message"),
                XYAutoReplyMessageLog.source_message_time.label("source_message_time"),
                XYAutoReplyMessageLog.process_status.label("process_status"),
                XYAutoReplyMessageLog.decision_reason.label("decision_reason"),
                XYAutoReplyMessageLog.reply_strategy.label("reply_strategy"),
                XYAutoReplyMessageLog.reply_mode.label("reply_mode"),
                XYAutoReplyMessageLog.matched_keyword.label("matched_keyword"),
                XYAutoReplyMessageLog.matched_rule_type.label("matched_rule_type"),
                XYAutoReplyMessageLog.default_reply_scope.label("default_reply_scope"),
                XYAutoReplyMessageLog.default_reply_once.label("default_reply_once"),
                XYAutoReplyMessageLog.ai_model_name.label("ai_model_name"),
                XYAutoReplyMessageLog.ai_provider_name.label("ai_provider_name"),
                XYAutoReplyMessageLog.reply_text.label("reply_text"),
                XYAutoReplyMessageLog.reply_image_url.label("reply_image_url"),
                XYAutoReplyMessageLog.error_message.label("error_message"),
                XYAutoReplyMessageLog.send_status.label("send_status"),
                XYAutoReplyMessageLog.send_fail_reason.label("send_fail_reason"),
                XYAutoReplyMessageLog.created_at.label("created_at"),
                XYAutoReplyMessageLog.updated_at.label("updated_at"),
            )
            .where(XYAutoReplyMessageLog.id.in_(log_ids))
            .order_by(
                XYAutoReplyMessageLog.created_at.desc(),
                XYAutoReplyMessageLog.id.desc(),
            )
        )
        logs = (await self.session.execute(stmt)).mappings().all()

        items = [self._serialize_log_row(log) for log in logs]
        return items, int(total)
