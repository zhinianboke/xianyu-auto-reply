"""账号 Excel 回复及配置导入：所有写入留在调用方事务中，不独立提交。"""
from __future__ import annotations

from sqlalchemy import select, text

from app.services.account_import_parsing import _parse_bool, _parse_int, _parse_str, _read_sheet_rows
from common.models.auto_rate_config import AutoRateConfig
from common.models.confirm_receipt_message import ConfirmReceiptMessage
from common.models.default_reply import DefaultReply


class AccountSettingsImportMixin:
    """回复、过滤及评价配置导入辅助，使用入口提供的会话和映射。"""

    async def _import_default_replies(self, wb) -> None:
        """导入默认回复"""
        rows = _read_sheet_rows(wb, "默认回复")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            if not account_id:
                continue
            item_id = _parse_str(row.get("商品ID")) or None

            stmt = select(DefaultReply).where(DefaultReply.account_id == account_id)
            if item_id:
                stmt = stmt.where(DefaultReply.item_id == item_id)
            else:
                stmt = stmt.where((DefaultReply.item_id.is_(None)) | (DefaultReply.item_id == ""))

            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.enabled = _parse_bool(row.get("启用"))
                existing.reply_content = _parse_str(row.get("回复内容")) or existing.reply_content
                existing.reply_image = _parse_str(row.get("回复图片")) or existing.reply_image
                existing.reply_once = _parse_bool(row.get("仅回复一次"))
                existing.reply_type = _parse_str(row.get("回复类型")) or existing.reply_type or "text"
                existing.api_url = _parse_str(row.get("API地址")) or existing.api_url
                api_timeout = _parse_int(row.get("API超时"))
                if api_timeout:
                    existing.api_timeout = api_timeout
                existing.location_name = _parse_str(row.get("\u5b9a\u4f4d\u540d\u79f0")) or existing.location_name
                existing.location_longitude = _parse_str(row.get("\u7ecf\u5ea6")) or existing.location_longitude
                existing.location_latitude = _parse_str(row.get("\u7eac\u5ea6")) or existing.location_latitude
                existing.location_title = _parse_str(row.get("\u4f4d\u7f6e\u6807\u9898")) or existing.location_title
                existing.location_subtitle = _parse_str(row.get("\u4f4d\u7f6e\u526f\u6807\u9898")) or existing.location_subtitle
            else:
                reply = DefaultReply(
                    account_id=account_id,
                    item_id=item_id,
                    enabled=_parse_bool(row.get("启用")),
                    reply_content=_parse_str(row.get("回复内容")) or None,
                    reply_image=_parse_str(row.get("回复图片")) or None,
                    reply_once=_parse_bool(row.get("仅回复一次")),
                    reply_type=_parse_str(row.get("回复类型")) or "text",
                    api_url=_parse_str(row.get("API地址")) or None,
                    api_timeout=_parse_int(row.get("API超时")) or 80,
                )
                reply.location_name = _parse_str(row.get("\u5b9a\u4f4d\u540d\u79f0")) or None
                reply.location_longitude = _parse_str(row.get("\u7ecf\u5ea6")) or None
                reply.location_latitude = _parse_str(row.get("\u7eac\u5ea6")) or None
                reply.location_title = _parse_str(row.get("\u4f4d\u7f6e\u6807\u9898")) or None
                reply.location_subtitle = _parse_str(row.get("\u4f4d\u7f6e\u526f\u6807\u9898")) or None
                self.session.add(reply)

        await self.session.flush()

    async def _import_message_filters(self, wb) -> None:
        """导入消息过滤规则"""
        rows = _read_sheet_rows(wb, "消息过滤规则")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            keyword = _parse_str(row.get("关键词"))
            filter_type = _parse_str(row.get("过滤类型"))
            if not account_id or not keyword or not filter_type:
                continue

            # 检查唯一约束
            check_sql = text("""
                SELECT id FROM xy_message_filters
                WHERE account_id = :account_id AND keyword = :keyword AND filter_type = :filter_type
                LIMIT 1
            """)
            result = await self.session.execute(check_sql, {
                "account_id": account_id, "keyword": keyword, "filter_type": filter_type
            })
            if result.scalar_one_or_none():
                continue  # 已存在，跳过

            enabled = _parse_bool(row.get("启用"))
            insert_sql = text("""
                INSERT INTO xy_message_filters (account_id, keyword, filter_type, enabled)
                VALUES (:account_id, :keyword, :filter_type, :enabled)
            """)
            await self.session.execute(insert_sql, {
                "account_id": account_id, "keyword": keyword,
                "filter_type": filter_type, "enabled": 1 if enabled else 0,
            })

        await self.session.flush()

    async def _import_confirm_receipt(self, wb) -> None:
        """导入确认收货消息"""
        rows = _read_sheet_rows(wb, "确认收货消息")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            if not account_id:
                continue

            stmt = select(ConfirmReceiptMessage).where(ConfirmReceiptMessage.account_id == account_id)
            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.enabled = _parse_bool(row.get("启用"))
                existing.message_content = _parse_str(row.get("消息内容")) or existing.message_content
                existing.message_image = _parse_str(row.get("消息图片")) or existing.message_image
            else:
                msg = ConfirmReceiptMessage(
                    account_id=account_id,
                    enabled=_parse_bool(row.get("启用")),
                    message_content=_parse_str(row.get("消息内容")) or None,
                    message_image=_parse_str(row.get("消息图片")) or None,
                )
                self.session.add(msg)

        await self.session.flush()

    async def _import_auto_rate(self, wb) -> None:
        """导入自动评价配置"""
        rows = _read_sheet_rows(wb, "自动评价配置")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            if not account_id:
                continue

            stmt = select(AutoRateConfig).where(AutoRateConfig.account_id == account_id)
            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.enabled = _parse_bool(row.get("启用"))
                existing.rate_type = _parse_str(row.get("评价类型")) or existing.rate_type
                existing.text_content = _parse_str(row.get("评价内容")) or existing.text_content
                existing.api_url = _parse_str(row.get("API地址")) or existing.api_url
            else:
                cfg = AutoRateConfig(
                    account_id=account_id,
                    enabled=_parse_bool(row.get("启用")),
                    rate_type=_parse_str(row.get("评价类型")) or "text",
                    text_content=_parse_str(row.get("评价内容")) or None,
                    api_url=_parse_str(row.get("API地址")) or None,
                )
                self.session.add(cfg)

        await self.session.flush()
