#!/usr/bin/env python3
"""Local Agent Ops CLI.

This CLI intentionally wraps a small allow-list of local operations instead of
automating the web UI. Read-only commands can use health endpoints and the local
Docker MySQL container. Write commands go through backend APIs and require
either --yes or --dry-run.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_BASE_URL = "http://localhost:8089"
DEFAULT_FRONTEND_URL = "http://localhost:9000"
DEFAULT_ENV_PATH = Path(".env")
DEFAULT_MYSQL_CONTAINER = "xianyu-mysql"
DEFAULT_MYSQL_DATABASE = "xianyu_data"
DEFAULT_MYSQL_USER = "xianyu"
DEFAULT_MYSQL_PASSWORD = ""

API_PREFIX = "/api/v1"
SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "auth_token",
    "authorization",
    "cookie",
    "cookie_value",
    "jwt",
    "login_password",
    "password",
    "proxy_pass",
    "refresh_token",
    "secret_key",
    "token",
    "value",
}


class AgentOpsError(RuntimeError):
    """User-facing CLI error."""


@dataclass
class WriteGuard:
    yes: bool = False
    dry_run: bool = False

    def require_confirmation(self, message: str) -> dict[str, Any] | None:
        if self.dry_run:
            return {"success": True, "dry_run": True, "message": message}
        if self.yes:
            return None
        raise AgentOpsError(f"{message}. Re-run with --yes to execute or --dry-run to preview.")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def coerce_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "enabled", "enable"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "disabled", "disable"}:
        return False
    raise AgentOpsError(f"Invalid boolean value: {value}")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_hs256_jwt(
    *,
    secret: str,
    subject: str,
    username: str,
    role: str,
    expires_minutes: int,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "username": username,
        "role": role,
        "exp": int(time.time()) + expires_minutes * 60,
    }
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


class ApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout: int = 30,
        transport: Callable[[urllib.request.Request, int], Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport = transport or default_transport

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=payload, headers=headers, method=method.upper())
        try:
            with self.transport(request, self.timeout) as response:
                data = response.read()
                return _decode_response(data)
        except urllib.error.HTTPError as exc:
            detail = _decode_response(exc.read())
            raise AgentOpsError(f"HTTP {exc.code} {method.upper()} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AgentOpsError(f"Cannot reach {url}: {exc.reason}") from exc
        except OSError as exc:
            raise AgentOpsError(f"Cannot reach {url}: {exc}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Any | None = None) -> Any:
        return self.request("POST", path, body)

    def put(self, path: str, body: Any | None = None) -> Any:
        return self.request("PUT", path, body)


def _decode_response(data: bytes) -> Any:
    text = data.decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def default_transport(request: urllib.request.Request, timeout: int, opener: Any = urllib.request.urlopen) -> Any:
    return opener(request, timeout=timeout)


def redact_sensitive(data: Any) -> Any:
    if isinstance(data, dict):
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            key_name = key.lower()
            if key_name == "value" and not isinstance(value, str):
                redacted[key] = redact_sensitive(value)
            elif key_name in SENSITIVE_KEYS and value not in {None, ""}:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_sensitive(value)
        return redacted
    if isinstance(data, list):
        return [redact_sensitive(item) for item in data]
    return data


def docker_env() -> dict[str, str]:
    env = os.environ.copy()
    raw_sock = Path.home() / "Library/Containers/com.docker.docker/Data/docker.raw.sock"
    if "DOCKER_HOST" not in env and raw_sock.exists():
        env["DOCKER_HOST"] = f"unix://{raw_sock}"
    return env


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, env=env)


def mysql_defaults(env_path: Path) -> dict[str, str]:
    env_values = parse_env_file(env_path)
    return {
        "container": os.environ.get("XIANYU_MYSQL_CONTAINER", DEFAULT_MYSQL_CONTAINER),
        "database": env_values.get("MYSQL_DATABASE", DEFAULT_MYSQL_DATABASE),
        "user": env_values.get("MYSQL_USER", DEFAULT_MYSQL_USER),
        "password": os.environ.get("XIANYU_MYSQL_PASSWORD", env_values.get("MYSQL_PASSWORD", DEFAULT_MYSQL_PASSWORD)),
    }


def mysql_query(sql: str, *, env_path: Path = DEFAULT_ENV_PATH) -> list[list[str]]:
    cfg = mysql_defaults(env_path)
    command = [
        "docker",
        "exec",
        "-e",
        f"MYSQL_PWD={cfg['password']}",
        cfg["container"],
        "mysql",
        "--default-character-set=utf8mb4",
        "-N",
        "-B",
        "-u",
        cfg["user"],
        cfg["database"],
        "-e",
        sql,
    ]
    result = run_command(command, env=docker_env())
    if result.returncode != 0:
        raise AgentOpsError(result.stderr.strip() or result.stdout.strip() or "mysql query failed")
    rows: list[list[str]] = []
    for line in result.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def mysql_scalar(sql: str, *, env_path: Path = DEFAULT_ENV_PATH) -> str:
    rows = mysql_query(sql, env_path=env_path)
    if not rows or not rows[0]:
        raise AgentOpsError("mysql query returned no rows")
    return rows[0][0]


def resolve_token(args: argparse.Namespace, *, required: bool = True) -> str | None:
    token = args.token or os.environ.get("XIANYU_AUTH_TOKEN")
    token_file = args.token_file or os.environ.get("XIANYU_AUTH_TOKEN_FILE")
    if not token and token_file:
        path = Path(token_file).expanduser()
        if path.exists():
            token = path.read_text(encoding="utf-8").strip()
    if required and not token:
        raise AgentOpsError(
            "This command needs an auth token. Use --token, XIANYU_AUTH_TOKEN, "
            "or generate one with: ./agent-ops auth local-token --write-token-file .agent-ops-token"
        )
    return token


def build_client(args: argparse.Namespace, *, required_token: bool = True) -> ApiClient:
    token = resolve_token(args, required=required_token)
    return ApiClient(base_url=args.base_url, token=token, timeout=args.timeout)


def output(data: Any, *, show_sensitive: bool = False) -> None:
    if not show_sensitive:
        data = redact_sensitive(data)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def command_status(args: argparse.Namespace) -> Any:
    health: dict[str, Any] = {}
    for name, url in {
        "frontend": DEFAULT_FRONTEND_URL,
        "backend": args.base_url,
        "websocket": "http://localhost:8090",
        "scheduler": "http://localhost:8091",
    }.items():
        path = "/health" if name != "frontend" else ""
        try:
            probe = ApiClient(base_url=url, timeout=args.timeout)
            health[name] = probe.get(path) if path else {"http_status": _head_status(url, args.timeout)}
        except AgentOpsError as exc:
            health[name] = {"success": False, "error": str(exc)}

    containers = list_xianyu_containers()
    counts = table_counts(
        [
            "xy_users",
            "xy_accounts",
            "xy_keyword_rules",
            "xy_cards",
            "xy_orders",
            "xy_catalog_items",
            "xy_auto_reply_message_logs",
            "xy_risk_control_logs",
        ],
        env_path=args.env_file,
    )
    return {"health": health, "containers": containers, "counts": counts}


def _head_status(url: str, timeout: int) -> int:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = _decode_response(exc.read())
        raise AgentOpsError(f"HTTP {exc.code} HEAD {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AgentOpsError(f"Cannot reach {url}: {exc.reason}") from exc
    except OSError as exc:
        raise AgentOpsError(f"Cannot reach {url}: {exc}") from exc


def write_private_text(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, 0o600)


def list_xianyu_containers() -> list[dict[str, Any]]:
    result = run_command(
        ["docker", "ps", "-a", "--filter", "name=xianyu-", "--format", "{{json .}}"],
        env=docker_env(),
    )
    if result.returncode != 0:
        return [{"error": result.stderr.strip() or "docker ps failed"}]
    containers: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if line.strip():
            raw = json.loads(line)
            containers.append(
                {
                    "name": raw.get("Names"),
                    "image": raw.get("Image"),
                    "state": raw.get("State"),
                    "status": raw.get("Status"),
                    "ports": raw.get("Ports"),
                }
            )
    return containers


def table_counts(tables: list[str], *, env_path: Path) -> dict[str, Any]:
    statements = " ".join(f"SELECT '{table}', COUNT(*) FROM {table};" for table in tables)
    try:
        rows = mysql_query(statements, env_path=env_path)
    except AgentOpsError as exc:
        return {"error": str(exc)}
    return {row[0]: int(row[1]) for row in rows if len(row) >= 2}


def command_auth_local_token(args: argparse.Namespace) -> Any:
    user_id = int(args.user_id)
    secret_sql = "SELECT value FROM xy_system_settings WHERE `key`='security.jwt_secret_key' LIMIT 1"
    user_sql = (
        "SELECT id, username, role FROM xy_users "
        f"WHERE id={user_id} AND status='ACTIVE' LIMIT 1"
    )
    secret = mysql_scalar(secret_sql, env_path=args.env_file)
    rows = mysql_query(user_sql, env_path=args.env_file)
    if not rows:
        raise AgentOpsError(f"Active user not found: {user_id}")
    subject, username, role = rows[0][0], rows[0][1], rows[0][2]
    token = make_hs256_jwt(
        secret=secret,
        subject=subject,
        username=username,
        role=role,
        expires_minutes=args.expires_minutes,
    )
    if args.write_token_file:
        path = Path(args.write_token_file).expanduser()
        try:
            write_private_text(path, token)
        except OSError as exc:
            raise AgentOpsError(f"Cannot write token file {path}: {exc}") from exc
        return {"success": True, "token_file": str(path), "user_id": user_id, "expires_minutes": args.expires_minutes}
    return {"success": True, "token": token, "user_id": user_id, "expires_minutes": args.expires_minutes}


def command_accounts_list(args: argparse.Namespace) -> Any:
    client = build_client(args)
    params = {"page": str(args.page), "page_size": str(args.page_size)}
    if args.status:
        params["status"] = args.status
    query = urllib.parse.urlencode(params)
    return client.get(f"{API_PREFIX}/cookies/details/paginated?{query}")


def command_accounts_set_reply_delay(args: argparse.Namespace) -> Any:
    guard = WriteGuard(args.yes, args.dry_run)
    message = f"set account {args.account_id} reply delay to {args.seconds}s"
    dry = guard.require_confirmation(message)
    if dry:
        return dry | {"account_id": args.account_id, "reply_delay_seconds": args.seconds}
    client = build_client(args)
    return client.put(
        f"{API_PREFIX}/cookies/{urllib.parse.quote(args.account_id)}/reply-delay",
        {"reply_delay_seconds": args.seconds},
    )


ACCOUNT_SWITCHES = {
    "status": ("status", "enabled"),
    "auto-confirm": ("auto-confirm", "auto_confirm"),
    "scheduled-redelivery": ("scheduled-redelivery", "scheduled_redelivery"),
    "scheduled-rate": ("scheduled-rate", "scheduled_rate"),
    "auto-polish": ("auto-polish", "auto_polish"),
    "auto-red-flower": ("auto-red-flower", "auto_red_flower"),
}


def command_accounts_set_switch(args: argparse.Namespace) -> Any:
    if args.switch not in ACCOUNT_SWITCHES:
        raise AgentOpsError(f"Unknown account switch: {args.switch}")
    endpoint, field = ACCOUNT_SWITCHES[args.switch]
    enabled = coerce_bool(args.value)
    guard = WriteGuard(args.yes, args.dry_run)
    message = f"set account {args.account_id} {args.switch} to {enabled}"
    dry = guard.require_confirmation(message)
    if dry:
        return dry | {"account_id": args.account_id, "switch": args.switch, "value": enabled}
    client = build_client(args)
    return client.put(
        f"{API_PREFIX}/cookies/{urllib.parse.quote(args.account_id)}/{endpoint}",
        {field: enabled},
    )


def command_tasks_list(args: argparse.Namespace) -> Any:
    token = resolve_token(args, required=False)
    if token:
        return build_client(args).get(f"{API_PREFIX}/admin/scheduled-tasks")
    rows = mysql_query(
        "SELECT task_code, task_name, interval_seconds, enabled FROM xy_scheduled_tasks ORDER BY task_code",
        env_path=args.env_file,
    )
    return {
        "success": True,
        "data": [
            {
                "task_code": row[0],
                "task_name": row[1],
                "interval_seconds": int(row[2]),
                "enabled": row[3] in {"1", "true", "True"},
            }
            for row in rows
        ],
        "source": "mysql",
    }


def command_tasks_set(args: argparse.Namespace) -> Any:
    params: dict[str, str] = {}
    if args.interval_seconds is not None:
        params["interval_seconds"] = str(args.interval_seconds)
    if args.enabled is not None:
        params["enabled"] = str(coerce_bool(args.enabled)).lower()
    if not params:
        raise AgentOpsError("Provide --enabled and/or --interval-seconds")
    guard = WriteGuard(args.yes, args.dry_run)
    message = f"update scheduled task {args.task_code}: {params}"
    dry = guard.require_confirmation(message)
    if dry:
        return dry | {"task_code": args.task_code, "params": params}
    client = build_client(args)
    query = urllib.parse.urlencode(params)
    return client.put(f"{API_PREFIX}/admin/scheduled-tasks/{urllib.parse.quote(args.task_code)}?{query}")


def command_tasks_trigger(args: argparse.Namespace) -> Any:
    guard = WriteGuard(args.yes, args.dry_run)
    message = f"trigger scheduled task {args.task_code}"
    dry = guard.require_confirmation(message)
    if dry:
        return dry | {"task_code": args.task_code}
    client = build_client(args)
    return client.post(f"{API_PREFIX}/admin/scheduled-tasks/{urllib.parse.quote(args.task_code)}/trigger")


def command_keywords_list(args: argparse.Namespace) -> Any:
    client = build_client(args)
    return client.get(f"{API_PREFIX}/keywords-with-item-id/{urllib.parse.quote(args.account_id)}")


def command_keywords_add(args: argparse.Namespace) -> Any:
    client = build_client(args)
    existing = client.get(f"{API_PREFIX}/keywords-with-item-id/{urllib.parse.quote(args.account_id)}")
    if not isinstance(existing, list):
        raise AgentOpsError(f"Unexpected keyword response: {existing}")
    item_id = args.item_id or ""
    if any(row.get("keyword") == args.keyword and (row.get("item_id") or "") == item_id for row in existing):
        return {"success": False, "message": "keyword already exists", "keyword": args.keyword, "item_id": item_id}
    keywords = [
        {"keyword": row.get("keyword", ""), "reply": row.get("reply", ""), "item_id": row.get("item_id") or ""}
        for row in existing
        if row.get("type") != "image"
    ]
    keywords.append({"keyword": args.keyword, "reply": args.reply, "item_id": item_id})
    guard = WriteGuard(args.yes, args.dry_run)
    message = f"add keyword {args.keyword!r} to account {args.account_id}"
    dry = guard.require_confirmation(message)
    if dry:
        return dry | {"account_id": args.account_id, "keyword": args.keyword, "item_id": item_id}
    return client.post(f"{API_PREFIX}/keywords-with-item-id/{urllib.parse.quote(args.account_id)}", {"keywords": keywords})


def command_orders_list(args: argparse.Namespace) -> Any:
    client = build_client(args)
    params = {"page": str(args.page), "page_size": str(args.page_size)}
    if args.account_id:
        params["cookie_id"] = args.account_id
    if args.status:
        params["status"] = args.status
    if args.search:
        params["search"] = args.search
    return client.get(f"{API_PREFIX}/orders?{urllib.parse.urlencode(params)}")


def command_orders_fetch(args: argparse.Namespace) -> Any:
    guard = WriteGuard(args.yes, args.dry_run)
    message = f"fetch xianyu orders for {args.account_id or 'all accessible accounts'}"
    dry = guard.require_confirmation(message)
    if dry:
        return dry | {"account_id": args.account_id}
    client = build_client(args)
    return client.post(f"{API_PREFIX}/orders/fetch-xianyu", {"cookie_id": args.account_id or None})


def command_logs_risk(args: argparse.Namespace) -> Any:
    client = build_client(args)
    params = {"limit": str(args.limit), "offset": str((args.page - 1) * args.limit)}
    if args.account_id:
        params["cookie_id"] = args.account_id
    return client.get(f"{API_PREFIX}/risk-control-logs?{urllib.parse.urlencode(params)}")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=os.environ.get("XIANYU_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token", default=None)
    parser.add_argument("--token-file", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--show-sensitive", action="store_true", help="Do not redact sensitive output fields.")


def set_write_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", action="store_true", help="Execute a write operation.")
    parser.add_argument("--dry-run", action="store_true", help="Preview a write operation without sending it.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-ops", description="Local Agent Ops CLI for xianyu-auto-reply.")
    add_common_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Summarize local runtime state.")
    status.set_defaults(func=command_status)

    auth = subparsers.add_parser("auth", help="Local auth helpers.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    local_token = auth_sub.add_parser("local-token", help="Create a local admin JWT from the Docker MySQL database.")
    local_token.add_argument("--user-id", default="1")
    local_token.add_argument("--expires-minutes", type=int, default=1440)
    local_token.add_argument("--write-token-file")
    local_token.set_defaults(func=command_auth_local_token)

    accounts = subparsers.add_parser("accounts", help="Account operations.")
    accounts_sub = accounts.add_subparsers(dest="accounts_command", required=True)
    accounts_list = accounts_sub.add_parser("list")
    accounts_list.add_argument("--page", type=int, default=1)
    accounts_list.add_argument("--page-size", type=int, default=20)
    accounts_list.add_argument("--status", choices=["active", "inactive"])
    accounts_list.set_defaults(func=command_accounts_list)
    reply_delay = accounts_sub.add_parser("set-reply-delay")
    reply_delay.add_argument("account_id")
    reply_delay.add_argument("seconds", type=int)
    set_write_arguments(reply_delay)
    reply_delay.set_defaults(func=command_accounts_set_reply_delay)
    set_switch = accounts_sub.add_parser("set-switch")
    set_switch.add_argument("account_id")
    set_switch.add_argument("switch", choices=sorted(ACCOUNT_SWITCHES))
    set_switch.add_argument("value")
    set_write_arguments(set_switch)
    set_switch.set_defaults(func=command_accounts_set_switch)

    tasks = subparsers.add_parser("tasks", help="Scheduled task operations.")
    tasks_sub = tasks.add_subparsers(dest="tasks_command", required=True)
    tasks_list = tasks_sub.add_parser("list")
    tasks_list.set_defaults(func=command_tasks_list)
    tasks_set = tasks_sub.add_parser("set")
    tasks_set.add_argument("task_code")
    tasks_set.add_argument("--enabled")
    tasks_set.add_argument("--interval-seconds", type=int)
    set_write_arguments(tasks_set)
    tasks_set.set_defaults(func=command_tasks_set)
    tasks_trigger = tasks_sub.add_parser("trigger")
    tasks_trigger.add_argument("task_code")
    set_write_arguments(tasks_trigger)
    tasks_trigger.set_defaults(func=command_tasks_trigger)

    keywords = subparsers.add_parser("keywords", help="Keyword reply operations.")
    keywords_sub = keywords.add_subparsers(dest="keywords_command", required=True)
    keywords_list = keywords_sub.add_parser("list")
    keywords_list.add_argument("account_id")
    keywords_list.set_defaults(func=command_keywords_list)
    keywords_add = keywords_sub.add_parser("add")
    keywords_add.add_argument("account_id")
    keywords_add.add_argument("--keyword", required=True)
    keywords_add.add_argument("--reply", required=True)
    keywords_add.add_argument("--item-id", default="")
    set_write_arguments(keywords_add)
    keywords_add.set_defaults(func=command_keywords_add)

    orders = subparsers.add_parser("orders", help="Order operations.")
    orders_sub = orders.add_subparsers(dest="orders_command", required=True)
    orders_list = orders_sub.add_parser("list")
    orders_list.add_argument("--account-id")
    orders_list.add_argument("--status")
    orders_list.add_argument("--search")
    orders_list.add_argument("--page", type=int, default=1)
    orders_list.add_argument("--page-size", type=int, default=20)
    orders_list.set_defaults(func=command_orders_list)
    orders_fetch = orders_sub.add_parser("fetch")
    orders_fetch.add_argument("--account-id")
    set_write_arguments(orders_fetch)
    orders_fetch.set_defaults(func=command_orders_fetch)

    logs = subparsers.add_parser("logs", help="Log operations.")
    logs_sub = logs.add_subparsers(dest="logs_command", required=True)
    risk = logs_sub.add_parser("risk")
    risk.add_argument("--account-id")
    risk.add_argument("--page", type=int, default=1)
    risk.add_argument("--limit", type=int, default=20)
    risk.set_defaults(func=command_logs_risk)

    return parser


GLOBAL_VALUE_OPTIONS = {"--base-url", "--token", "--token-file", "--timeout", "--env-file"}
GLOBAL_FLAG_OPTIONS = {"--show-sensitive"}


def normalize_global_args(argv: list[str]) -> list[str]:
    globals_seen: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in GLOBAL_VALUE_OPTIONS:
            if index + 1 >= len(argv):
                rest.append(arg)
                index += 1
                continue
            globals_seen.extend([arg, argv[index + 1]])
            index += 2
            continue
        if any(arg.startswith(f"{option}=") for option in GLOBAL_VALUE_OPTIONS):
            globals_seen.append(arg)
            index += 1
            continue
        if arg in GLOBAL_FLAG_OPTIONS:
            globals_seen.append(arg)
            index += 1
            continue
        rest.append(arg)
        index += 1
    return globals_seen + rest


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    normalized_argv = normalize_global_args(list(argv if argv is not None else sys.argv[1:]))
    args = parser.parse_args(normalized_argv)
    try:
        result = args.func(args)
        output(result, show_sensitive=args.show_sensitive)
        return 0
    except AgentOpsError as exc:
        output({"success": False, "error": str(exc)}, show_sensitive=args.show_sensitive)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
