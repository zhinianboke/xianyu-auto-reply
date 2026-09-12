import unittest

from common.utils.notification_template import (
    render_notification_template,
    validate_notification_template,
)


class NotificationTemplateTest(unittest.TestCase):
    def test_renders_multiline_template_and_repeated_variables(self):
        message = render_notification_template(
            {"delivery_template": "买家: {{buyer_nick}}\n订单: {{order_id}}\n再次确认: {{buyer_nick}}"},
            "delivery",
            {"buyer_nick": "金鱼小姐21", "order_id": "123"},
            "默认正文",
        )

        self.assertEqual(message, "买家: 金鱼小姐21\n订单: 123\n再次确认: 金鱼小姐21")

    def test_empty_template_uses_default_message(self):
        self.assertEqual(
            render_notification_template(
                {"chat_template": "   "},
                "chat",
                {"buyer_nick": "买家"},
                "默认聊天正文",
            ),
            "默认聊天正文",
        )

    def test_unknown_variable_falls_back_to_default_message(self):
        self.assertEqual(
            render_notification_template(
                {"delivery_template": "订单 {{unknown_field}}"},
                "delivery",
                {},
                "默认发货正文",
            ),
            "默认发货正文",
        )

    def test_invalid_placeholder_syntax_falls_back_to_default_message(self):
        self.assertEqual(
            render_notification_template(
                {"account_template": "{{title"},
                "account",
                {"title": "账号异常"},
                "默认账号正文",
            ),
            "默认账号正文",
        )

    def test_missing_context_value_is_rendered_as_unknown(self):
        self.assertEqual(
            render_notification_template(
                {"account_template": "{{title}}\n{{verification_info}}"},
                "account",
                {"title": "需要验证"},
                "默认账号正文",
            ),
            "需要验证\n未知",
        )

    def test_validation_rejects_variables_not_available_to_template_type(self):
        self.assertEqual(
            validate_notification_template("{{result}}", "chat"),
            "不支持的占位符: result",
        )


if __name__ == "__main__":
    unittest.main()
