import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "websocket"))

from app.services.xianyu.notification_manager import NotificationManager  # noqa: E402
from app.services.xianyu.auto_reply_service import AutoReplyService  # noqa: E402


class NotificationDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_channels_render_their_own_chat_templates(self):
        manager = NotificationManager("seller")
        notifications = [
            {
                "enabled": True,
                "channel_type": "bark",
                "channel_config": {"device_key": "a", "chat_template": "买家={{buyer_nick}}"},
            },
            {
                "enabled": True,
                "channel_type": "feishu",
                "channel_config": {"webhook_url": "https://example.com", "chat_template": "消息={{message}}"},
            },
        ]

        with patch(
            "app.services.xianyu.notification_manager.send_bark_notification",
            new=AsyncMock(return_value=True),
        ) as bark_send, patch(
            "app.services.xianyu.notification_manager.send_feishu_notification",
            new=AsyncMock(return_value=True),
        ) as feishu_send:
            await manager._send_to_channels(
                notifications,
                "系统默认正文",
                template_type="chat",
                template_context={"buyer_nick": "小王", "message": "你好"},
            )

        self.assertEqual(bark_send.await_args.args[1], "买家=小王")
        self.assertEqual(feishu_send.await_args.args[1], "消息=你好")

    async def test_delivery_template_uses_order_nickname_amount_and_quantity(self):
        manager = NotificationManager("seller")
        with patch("common.db.compat.db_manager.get_message_filter_keywords", return_value=[]), patch(
            "common.db.compat.db_manager.get_account_notifications",
            return_value=[
                {
                    "enabled": True,
                    "channel_type": "bark",
                    "channel_config": {
                        "device_key": "a",
                        "delivery_template": "{{buyer_nick}}|{{amount}}|{{quantity}}|{{result}}",
                    },
                }
            ],
        ), patch(
            "common.db.compat.db_manager.get_cookie_details",
            return_value={"remark": "主账号"},
        ), patch(
            "common.db.compat.db_manager.get_order_by_id",
            return_value={"buyer_fish_nick": "金鱼小姐21", "amount": "2", "quantity": 1},
        ), patch(
            "app.services.xianyu.notification_manager.send_bark_notification",
            new=AsyncMock(return_value=True),
        ) as bark_send:
            await manager.send_delivery_failure_notification(
                "等待你发货",
                "342188141",
                "1071626525089",
                "发货成功",
                "chat-1",
                order_id="order-1",
            )

        self.assertEqual(bark_send.await_args.args[1], "金鱼小姐21|¥2.00|1|发货成功")

    async def test_delivery_default_keeps_original_layout_and_adds_amount_and_quantity(self):
        manager = NotificationManager("seller")
        with patch("common.db.compat.db_manager.get_message_filter_keywords", return_value=[]), patch(
            "common.db.compat.db_manager.get_account_notifications",
            return_value=[{"enabled": True, "channel_type": "bark", "channel_config": {"device_key": "a"}}],
        ), patch(
            "common.db.compat.db_manager.get_cookie_details",
            return_value={"remark": "主账号"},
        ), patch(
            "common.db.compat.db_manager.get_order_by_id",
            return_value={"buyer_fish_nick": "金鱼小姐21", "amount": "2", "quantity": 1},
        ), patch(
            "app.services.xianyu.notification_manager.send_bark_notification",
            new=AsyncMock(return_value=True),
        ) as bark_send:
            await manager.send_delivery_failure_notification(
                "等待你发货",
                "342188141",
                "1071626525089",
                "发货成功",
                "chat-1",
                order_id="order-1",
            )

        message = bark_send.await_args.args[1]
        self.assertIn("买家: 金鱼小姐21 (ID: 342188141)", message)
        self.assertIn("订单金额: ¥2.00", message)
        self.assertIn("购买数量: 1", message)
        self.assertNotIn("订单ID:", message)

    async def test_auto_reply_service_uses_chat_template(self):
        service = object.__new__(AutoReplyService)
        service.cookie_id = "seller"
        with patch(
            "common.db.compat.db_manager.get_account_notifications",
            return_value=[
                {
                    "enabled": True,
                    "channel_type": "bark",
                    "channel_config": {"device_key": "a", "chat_template": "{{buyer_nick}}: {{message}}"},
                }
            ],
        ), patch(
            "common.db.compat.db_manager.get_cookie_details",
            return_value={"remark": "主账号"},
        ), patch(
            "common.utils.notification_utils.send_bark_notification",
            new=AsyncMock(return_value=True),
        ) as bark_send:
            await service._send_notification("小王", "buyer-1", "你好", "chat-1", "item-1", "2026-08-11 11:00:00")

        self.assertEqual(bark_send.await_args.args[1], "小王: 你好")

    async def test_account_template_receives_verification_link(self):
        manager = NotificationManager("seller-account-template")
        with patch(
            "common.db.compat.db_manager.get_account_notifications",
            return_value=[
                {
                    "enabled": True,
                    "channel_type": "email",
                    "channel_config": {"account_template": "{{title}}|{{detail}}|{{verification_url}}"},
                }
            ],
        ), patch(
            "common.db.compat.db_manager.get_cookie_details",
            return_value={"remark": "主账号"},
        ), patch(
            "app.services.xianyu.notification_manager.send_email_notification",
            new=AsyncMock(return_value=True),
        ) as email_send:
            await manager.send_token_refresh_notification(
                "请完成人脸验证",
                "face_verification_required",
                verification_url="https://example.com/verify",
            )

        self.assertEqual(
            email_send.await_args.args[1],
            "⚠️ 需要人脸验证|请完成人脸验证|https://example.com/verify",
        )

    async def test_account_template_preserves_email_attachment(self):
        manager = NotificationManager("seller")
        with patch(
            "app.services.xianyu.notification_manager.send_email_notification",
            new=AsyncMock(return_value=True),
        ) as email_send:
            await manager._send_to_channels(
                [
                    {
                        "enabled": True,
                        "channel_type": "email",
                        "channel_config": {"account_template": "{{title}}: {{detail}}"},
                    }
                ],
                "系统默认正文",
                attachment_path="/tmp/captcha.png",
                template_type="account",
                template_context={"title": "需要验证", "detail": "请完成人脸验证"},
            )

        self.assertEqual(email_send.await_args.args[1], "需要验证: 请完成人脸验证")
        self.assertEqual(email_send.await_args.args[2], "/tmp/captcha.png")


if __name__ == "__main__":
    unittest.main()
