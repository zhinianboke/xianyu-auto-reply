"""
推送消息解析器

功能：
1. 解密 IM WebSocket 主动推送的消息（base64/MessagePack）
2. 解析标准聊天消息、卡片消息、卡片更新消息
3. 提取文本/图片/语音等消息内容
4. 格式化为前端可消费的统一格式

参照自动回复 websocket/app/services/xianyu/message_handler.py 的解密和解析逻辑
"""
import base64
import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from common.utils.xianyu_utils import decrypt


class PushMessageParser:
    """推送消息解析器，负责解密和解析 IM 主动推送的消息"""

    def __init__(self, account_id: str, myid: str):
        """
        初始化解析器

        Args:
            account_id: 账号标识（用于日志）
            myid: 当前登录用户 ID（用于判断是否自己发出）
        """
        self.account_id = account_id
        self.myid = myid

    def decrypt_push_data(self, data: str) -> Optional[dict]:
        """
        解密推送消息数据

        参照自动回复 message_handler._decrypt_message：
        先尝试 base64 -> JSON，失败则用 decrypt() 解密 MessagePack

        Args:
            data: 原始推送数据字符串

        Returns:
            解密后的消息字典，失败返回 None
        """
        try:
            try:
                decoded_str = base64.b64decode(data).decode("utf-8")
                parsed = json.loads(decoded_str)
                if isinstance(parsed, dict) and "chatType" in parsed:
                    return None  # 系统提示消息，跳过
                return parsed
            except Exception:
                decrypted = json.loads(decrypt(data))
                return decrypted
        except Exception:
            return None

    def parse(self, msg: dict) -> Optional[dict]:
        """
        解析解密后的推送消息，提取聊天内容并打印日志

        Returns:
            解析后的消息字典（event/cid/message），无法解析返回 None
        """
        try:
            # 标准聊天消息：msg["1"] 为 dict 且有 msg["1"]["10"]["reminderContent"]
            msg_1 = msg.get("1")
            if isinstance(msg_1, dict):
                msg_10 = msg_1.get("10", {})
                if isinstance(msg_10, dict) and msg_10.get("reminderContent") is not None:
                    return self._parse_standard_chat(msg_1, msg_10)
                # 卡片消息（msg["1"]["6"]["3"] 存在）
                msg_6 = msg_1.get("6", {})
                if isinstance(msg_6, dict) and "3" in msg_6:
                    return self._parse_card_chat(msg_1, msg_6)

            # 卡片更新消息：msg["1"] 为字符串, msg["4"]["reminderContent"]
            if isinstance(msg.get("1"), str) and isinstance(msg.get("4"), dict):
                msg_4 = msg["4"]
                if "reminderContent" in msg_4:
                    return self._parse_card_update(msg, msg_4)

            return None
        except Exception as e:
            logger.warning(f"【{self.account_id}】解析推送消息失败: {e}")
            return None

    # ==================== 内部解析方法 ====================

    def _parse_standard_chat(self, msg_1: dict, msg_10: dict) -> Optional[dict]:
        """解析标准聊天推送消息"""
        try:
            sender_id_raw = str(msg_10.get("senderUserId", "") or "")
            # 去掉 @goofish 后缀，保证前端显示和对比一致
            sender_id = sender_id_raw.split("@")[0] if "@" in sender_id_raw else sender_id_raw
            sender_name = str(
                msg_10.get("senderNick") or msg_10.get("reminderTitle") or ""
            )
            reminder = msg_10.get("reminderContent", "")
            cid_raw = str(msg_1.get("2", ""))
            cid = cid_raw.split("@")[0] if "@" in cid_raw else cid_raw
            msg_time = msg_1.get("5", 0)

            # 解析 base64 内容
            text_content, images, msg_type = self._decode_content(msg_1)
            if not text_content and not images:
                text_content = reminder
                msg_type = "text"

            is_self = sender_id == self.myid

            if is_self:
                logger.info(
                    f"【{self.account_id}】[推送-发出] cid={cid}, "
                    f"内容: {text_content or '[图片]'}"
                )
            else:
                logger.info(
                    f"【{self.account_id}】[推送-收到] cid={cid}, "
                    f"发送者={sender_name}({sender_id}), "
                    f"内容: {text_content or '[图片]'}"
                )

            return {
                "event": "new_message",
                "cid": cid,
                "message": {
                    "messageId": str(msg_1.get("3", "") or ""),
                    "senderId": sender_id,
                    "senderName": sender_name,
                    "isSelf": is_self,
                    "type": msg_type,
                    "text": text_content,
                    "images": images,
                    "time": msg_time,
                },
            }
        except Exception as e:
            logger.warning(f"【{self.account_id}】解析标准聊天推送失败: {e}")
            return None

    def _parse_card_chat(self, msg_1: dict, msg_6: dict) -> Optional[dict]:
        """解析卡片类型聊天推送消息"""
        try:
            msg_6_3 = msg_6.get("3", {})
            text_content = msg_6_3.get("2", "[卡片消息]")
            cid_raw = str(msg_1.get("2", ""))
            cid = cid_raw.split("@")[0] if "@" in cid_raw else cid_raw
            msg_time = msg_1.get("5", 0)

            msg_1_1 = msg_1.get("1", {})
            sender_raw = msg_1_1.get("1", "") if isinstance(msg_1_1, dict) else ""
            sender_id = (
                sender_raw.split("@")[0]
                if "@" in str(sender_raw)
                else str(sender_raw)
            )

            logger.info(
                f"【{self.account_id}】[推送-卡片] cid={cid}, 内容: {text_content}"
            )

            return {
                "event": "new_message",
                "cid": cid,
                "message": {
                    "messageId": str(msg_1.get("3", "") or ""),
                    "senderId": sender_id,
                    "senderName": "系统",
                    "isSelf": sender_id == self.myid,
                    "type": "card",
                    "text": str(text_content),
                    "images": [],
                    "time": msg_time,
                },
            }
        except Exception as e:
            logger.warning(f"【{self.account_id}】解析卡片推送失败: {e}")
            return None

    def _parse_card_update(self, msg: dict, msg_4: dict) -> Optional[dict]:
        """解析卡片更新推送消息（如付款状态变更）"""
        try:
            reminder = msg_4.get("reminderContent", "")
            sender_id_raw = str(msg_4.get("senderUserId", "") or "")
            # 去掉 @goofish 后缀
            sender_id = sender_id_raw.split("@")[0] if "@" in sender_id_raw else sender_id_raw
            sender_name = str(msg_4.get("reminderTitle", "") or "系统")
            cid_raw = str(msg.get("2", ""))
            cid = cid_raw.split("@")[0] if "@" in cid_raw else cid_raw
            msg_time = msg.get("5", 0)

            logger.info(
                f"【{self.account_id}】[推送-卡片更新] cid={cid}, "
                f"发送者={sender_name}, 内容: {reminder}"
            )

            return {
                "event": "new_message",
                "cid": cid,
                "message": {
                    "messageId": str(msg.get("3", "") or ""),
                    "senderId": sender_id,
                    "senderName": sender_name,
                    "isSelf": sender_id == self.myid,
                    "type": "text",
                    "text": reminder,
                    "images": [],
                    "time": msg_time,
                },
            }
        except Exception as e:
            logger.warning(f"【{self.account_id}】解析卡片更新推送失败: {e}")
            return None

    def _decode_content(self, msg_1: dict) -> Tuple[str, List[str], str]:
        """
        从推送消息中解码 base64 内容

        参照 chat_new.py 的 _parse_message 逻辑

        Returns:
            (text, images, msg_type) 三元组
        """
        try:
            msg_6 = msg_1.get("6", {})
            if not isinstance(msg_6, dict):
                return ("", [], "text")
            msg_6_3 = msg_6.get("3", {})
            if not isinstance(msg_6_3, dict):
                return ("", [], "text")
            custom_data = msg_6_3.get("1", "")
            if not custom_data or not isinstance(custom_data, str):
                return ("", [], "text")

            decoded = json.loads(base64.b64decode(custom_data).decode("utf-8"))
            content_type = decoded.get("contentType", 0)

            if content_type == 1 and "text" in decoded:
                text_obj = decoded["text"]
                if isinstance(text_obj, dict):
                    return (text_obj.get("text", ""), [], "text")
                return (str(text_obj), [], "text")

            if content_type == 2 and "image" in decoded:
                pics = decoded.get("image", {}).get("pics", [])
                urls = [p.get("url", "") for p in pics if p.get("url")]
                return ("", urls, "image")

            if content_type == 3 and "audio" in decoded:
                return ("[语音消息]", [], "text")

            if "text" in decoded:
                text_obj = decoded["text"]
                if isinstance(text_obj, dict):
                    return (text_obj.get("text", str(text_obj)), [], "text")
                return (str(text_obj), [], "text")

            if "picUrl" in decoded:
                return ("", [decoded["picUrl"]], "image")

            return ("", [], "text")
        except Exception:
            return ("", [], "text")
