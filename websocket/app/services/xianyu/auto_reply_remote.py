"""远程默认回复。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user_setting import UserSetting
from common.services.remote_location_message_api import (
    RemoteLocationMessageError,
    fetch_remote_location_message,
)
from common.utils.default_reply_api import call_reply_api
from common.utils.default_reply_location import validate_external_contact_fields


class AutoReplyRemoteMixin:
    """封装自动回复remote相关处理。"""

    async def _do_api_default_reply(
        self,
        session: AsyncSession,
        send_message: str,
        api_url: str,
        api_timeout,
        settings: dict,
        settings_item_id: Optional[str],
        chat_id: str,
        send_user_id: str,
        send_user_name: str,
        item_id: Optional[str],
        msg_time: str,
        reply_trace: Optional[dict],
    ) -> Optional[str]:
        """调用外部 API 获取默认回复内容并处理结果。

        由 get_default_reply 在持有会话级去重锁（或降级无锁）时调用：
        - 调用失败/超时/无有效内容：返回 None，不回复，且不记录 reply_once（便于下次重试）；
        - 调用成功：按需记录 reply_once，返回回复文本（下游按 ###### 分段发送）。
        """
        api_reply = await call_reply_api(
            account_id=self.cookie_id,
            message=send_message,
            api_url=api_url,
            timeout=api_timeout,
            chat_id=chat_id,
            item_id=item_id or "",
            send_user_id=send_user_id,
            send_user_name=send_user_name,
            msg_time=msg_time,
        )

        # 失败/无有效内容：不回复（不记录 reply_once，便于下次重试）
        if not api_reply or not api_reply.strip():
            logger.info(f"【{self.cookie_id}】默认回复API未返回有效内容,不进行回复")
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "no_rule_matched"
                reply_trace.setdefault("context_snapshot", {})["default_reply_api_url"] = api_url
            return None

        # 调用成功后再记录 reply_once
        if settings.get("reply_once", False) and chat_id:
            await self._record_user_replied(session, self.cookie_id, chat_id, settings_item_id)
            logger.info(f"【{self.cookie_id}】记录默认回复(API): chat_id={chat_id}, item_id={settings_item_id}")

        logger.info(f"【{self.cookie_id}】使用API默认回复: {api_reply[:50]}")
        if reply_trace is not None:
            reply_trace["reply_mode"] = "text"
            reply_trace["reply_text"] = api_reply
            reply_trace["reply_segments"] = self._build_text_reply_segments(api_reply)
            reply_trace.setdefault("context_snapshot", {})["default_reply_api_url"] = api_url
        return api_reply

    async def _get_location_chat_settings(self, session: AsyncSession) -> dict[str, str]:
        """读取当前账号所属用户的远程位置聊天配置。"""
        account = await self._get_account(session)
        owner_id = getattr(account, "owner_id", None) or getattr(self.xianyu_instance, "user_id", None)
        if owner_id is None:
            return {}
        stmt = select(UserSetting.key, UserSetting.value).where(
            UserSetting.user_id == owner_id,
            UserSetting.key.in_(("location_chat.remote_url", "location_chat.remote_secret_key")),
        )
        result = await session.execute(stmt)
        return {str(key): str(value or "") for key, value in result.all()}

    async def _do_external_contact_default_reply(
        self,
        session: AsyncSession,
        settings: dict,
        settings_item_id: Optional[str],
        chat_id: str,
        send_user_id: str,
        reply_trace: Optional[dict],
    ) -> Optional[dict]:
        """通过远程接口获取完整位置 LWP 报文，不在本地生成报文。"""
        location_settings = await self._get_location_chat_settings(session)
        remote_url = location_settings.get("location_chat.remote_url", "").strip()
        remote_secret_key = location_settings.get("location_chat.remote_secret_key", "").strip()
        location_name = str(settings.get("location_name") or "").strip()
        longitude = str(settings.get("location_longitude") or "").strip()
        latitude = str(settings.get("location_latitude") or "").strip()
        title = str(settings.get("location_title") or "").strip()
        subtitle = str(settings.get("location_subtitle") or "").strip()
        sender_user_id = str(getattr(self.xianyu_instance, "myid", self.cookie_id) or "").strip()

        if not chat_id or not send_user_id or not sender_user_id:
            error = "位置消息缺少会话或用户标识"
            logger.warning(f"【{self.cookie_id}】{error}")
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "external_contact_config_invalid"
                reply_trace.setdefault("context_snapshot", {})["external_contact_error"] = error
            return None

        validation_error = validate_external_contact_fields(
            remote_url=remote_url,
            location_name=location_name,
            longitude=longitude,
            latitude=latitude,
            title=title,
            subtitle=subtitle,
        )
        if validation_error:
            logger.warning(f"【{self.cookie_id}】站外联系方式默认回复配置无效: {validation_error}")
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "external_contact_config_invalid"
                reply_trace.setdefault("context_snapshot", {})["external_contact_error"] = validation_error
            return None
        if not remote_secret_key:
            error = "个人设置中未配置位置聊天秘钥"
            logger.warning(f"【{self.cookie_id}】{error}")
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "external_contact_config_invalid"
                reply_trace.setdefault("context_snapshot", {})["external_contact_error"] = error
            return None

        try:
            result = await fetch_remote_location_message(
                url=remote_url,
                secret_key=remote_secret_key,
                chat_id=chat_id,
                send_user_id=send_user_id,
                sender_user_id=sender_user_id,
                longitude=longitude,
                latitude=latitude,
                title=title,
                subtitle=subtitle,
            )
        except RemoteLocationMessageError as exc:
            logger.warning(f"【{self.cookie_id}】获取站外联系方式位置报文失败: {exc}")
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "external_contact_remote_failed"
                reply_trace.setdefault("context_snapshot", {})["external_contact_error"] = str(exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"【{self.cookie_id}】获取站外联系方式位置报文异常")
            if reply_trace is not None:
                reply_trace["process_status"] = "failed"
                reply_trace["decision_reason"] = "external_contact_remote_failed"
                reply_trace.setdefault("context_snapshot", {})["external_contact_error"] = str(exc)
            return None

        message = result.get("message") if isinstance(result, dict) else None
        if not isinstance(message, dict):
            logger.warning(f"【{self.cookie_id}】远程位置接口未返回有效 data.message")
            return None
        if reply_trace is not None:
            reply_trace["reply_mode"] = "external_contact"
            reply_trace["reply_segments"] = [{"mode": "external_contact", "content": title}]
            reply_trace.setdefault("context_snapshot", {})["external_contact_remote_url"] = remote_url
        return {
            "_reply_mode": "external_contact",
            "message": message,
            "reply_once": bool(settings.get("reply_once", False)),
            "settings_item_id": settings_item_id,
        }
