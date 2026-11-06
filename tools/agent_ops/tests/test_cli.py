import base64
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request as urllib_request

from tools.agent_ops.cli import (
    AgentOpsError,
    ApiClient,
    WriteGuard,
    _head_status,
    coerce_bool,
    default_transport,
    list_xianyu_containers,
    make_hs256_jwt,
    normalize_global_args,
    parse_env_file,
    redact_sensitive,
    write_private_text,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AgentOpsCoreTests(unittest.TestCase):
    def test_parse_env_file_ignores_comments_and_empty_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n# comment\nMYSQL_USER=xianyu\nMYSQL_PASSWORD='example-password'\nEMPTY=\n",
                encoding="utf-8",
            )

            parsed = parse_env_file(env_path)

        self.assertEqual(parsed["MYSQL_USER"], "xianyu")
        self.assertEqual(parsed["MYSQL_PASSWORD"], "example-password")
        self.assertEqual(parsed["EMPTY"], "")

    def test_make_hs256_jwt_encodes_expected_payload(self):
        token = make_hs256_jwt(
            secret="secret-value",
            subject="1",
            username="admin",
            role="ADMIN",
            expires_minutes=60,
        )

        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))

        self.assertEqual(header["alg"], "HS256")
        self.assertEqual(payload["sub"], "1")
        self.assertEqual(payload["username"], "admin")
        self.assertEqual(payload["role"], "ADMIN")
        self.assertIsInstance(payload["exp"], int)
        self.assertGreater(len(signature_b64), 10)

    def test_api_client_sends_bearer_token_and_json_body(self):
        seen = {}

        def fake_transport(request, timeout):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["headers"] = dict(request.header_items())
            seen["body"] = request.data
            seen["timeout"] = timeout
            return FakeResponse({"success": True})

        client = ApiClient(
            base_url="http://localhost:8089",
            token="abc123",
            timeout=12,
            transport=fake_transport,
        )

        result = client.request("PUT", "/api/v1/demo", {"enabled": True})

        self.assertEqual(result, {"success": True})
        self.assertEqual(seen["url"], "http://localhost:8089/api/v1/demo")
        self.assertEqual(seen["method"], "PUT")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer abc123")
        self.assertEqual(seen["headers"]["Content-type"], "application/json")
        self.assertEqual(json.loads(seen["body"].decode("utf-8")), {"enabled": True})
        self.assertEqual(seen["timeout"], 12)

    def test_default_transport_passes_timeout_as_keyword(self):
        seen = {}

        def opener(request, **kwargs):
            seen["url"] = request.full_url
            seen["timeout"] = kwargs.get("timeout")
            return FakeResponse({"ok": True})

        response = default_transport(
            urllib_request("http://localhost:8089/health"),
            timeout=7,
            opener=opener,
        )

        self.assertEqual(response.read(), b'{"ok": true}')
        self.assertEqual(seen["timeout"], 7)

    def test_head_status_wraps_connection_errors(self):
        with mock.patch("tools.agent_ops.cli.urllib.request.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(AgentOpsError, "Cannot reach http://localhost:9000"):
                _head_status("http://localhost:9000", timeout=1)

        with mock.patch("tools.agent_ops.cli.urllib.request.urlopen", side_effect=ConnectionResetError("reset")):
            with self.assertRaisesRegex(AgentOpsError, "Cannot reach http://localhost:9000"):
                _head_status("http://localhost:9000", timeout=1)

    def test_write_private_text_uses_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / ".agent-ops-token"
            token_path.write_text("old-token", encoding="utf-8")
            token_path.chmod(0o644)

            write_private_text(token_path, "new-token")

            self.assertEqual(token_path.read_text(encoding="utf-8"), "new-token")
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    def test_list_xianyu_containers_includes_stopped_containers(self):
        result = mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("tools.agent_ops.cli.run_command", return_value=result) as run:
            self.assertEqual(list_xianyu_containers(), [])

        command = run.call_args.args[0]
        self.assertIn("-a", command)

    def test_write_guard_requires_yes_or_dry_run(self):
        guard = WriteGuard(yes=False, dry_run=False)

        with self.assertRaises(AgentOpsError):
            guard.require_confirmation("update task")

        dry_run_guard = WriteGuard(yes=False, dry_run=True)
        self.assertEqual(
            dry_run_guard.require_confirmation("update task"),
            {"success": True, "dry_run": True, "message": "update task"},
        )

    def test_coerce_bool_accepts_human_values(self):
        self.assertTrue(coerce_bool("true"))
        self.assertTrue(coerce_bool("on"))
        self.assertFalse(coerce_bool("false"))
        self.assertFalse(coerce_bool("0"))

        with self.assertRaises(AgentOpsError):
            coerce_bool("maybe")

    def test_redact_sensitive_masks_nested_cookie_like_fields(self):
        data = {
            "id": "demo-account-id",
            "value": "cookie=secret",
            "cookie_value": "cookie=secret",
            "access_token": "secret-token",
            "token_file": ".agent-ops-token",
            "nested": {"login_password": "secret-password", "safe": "ok"},
        }

        redacted = redact_sensitive(data)

        self.assertEqual(redacted["value"], "<redacted>")
        self.assertEqual(redacted["cookie_value"], "<redacted>")
        self.assertEqual(redacted["access_token"], "<redacted>")
        self.assertEqual(redacted["token_file"], ".agent-ops-token")
        self.assertEqual(redacted["nested"]["login_password"], "<redacted>")
        self.assertEqual(redacted["nested"]["safe"], "ok")

    def test_normalize_global_args_moves_common_options_before_subcommands(self):
        normalized = normalize_global_args(
            ["accounts", "list", "--page-size", "5", "--token-file", "/tmp/token", "--show-sensitive"]
        )

        self.assertEqual(
            normalized,
            ["--token-file", "/tmp/token", "--show-sensitive", "accounts", "list", "--page-size", "5"],
        )


if __name__ == "__main__":
    unittest.main()
