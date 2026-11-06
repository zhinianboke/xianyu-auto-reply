from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _PauseManager:
    def is_chat_paused(self, *_args, **_kwargs):
        return False

    def get_remaining_ai_pause_time(self, *_args, **_kwargs):
        return 0

    def is_ai_reply_paused(self, *_args, **_kwargs):
        return False


pause_manager = _PauseManager()


class _Query:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: self


def _module(name: str, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


def _install_import_stubs() -> None:
    _module("loguru", logger=_Logger())

    sqlalchemy = _module(
        "sqlalchemy",
        select=lambda *args, **kwargs: _Query(),
        func=types.SimpleNamespace(count=lambda: _Query()),
        update=lambda *args, **kwargs: _Query(),
        text=lambda *args, **kwargs: None,
        exists=lambda *args, **kwargs: None,
    )
    sqlalchemy_ext = _module("sqlalchemy.ext")
    sqlalchemy_asyncio = _module("sqlalchemy.ext.asyncio", AsyncSession=object)
    sqlalchemy.ext = sqlalchemy_ext
    sqlalchemy_ext.asyncio = sqlalchemy_asyncio

    models_package = _module("common.models")
    models_package.__path__ = []
    for module_name, class_name in (
        ("xy_account", "XYAccount"),
        ("xy_keyword_rule", "XYKeywordRule"),
        ("xy_catalog_item", "XYCatalogItem"),
        ("auto_reply_message_log", "XYAutoReplyMessageLog"),
        ("user_setting", "UserSetting"),
        ("xy_order", "XYOrder"),
        ("ai_chat_message", "AIChatMessage"),
    ):
        model = type(
            class_name,
            (),
            {
                "id": object(),
                "account_id": object(),
                "account_pk": object(),
                "item_id": object(),
                "buyer_id": object(),
            },
        )
        _module(f"common.models.{module_name}", **{class_name: model})
    _module(
        "common.models.default_reply",
        DefaultReply=type("DefaultReply", (), {}),
        DefaultReplyRecord=type("DefaultReplyRecord", (), {}),
    )

    db_package = _module("common.db")
    db_package.__path__ = []
    _module("common.db.session", async_session_maker=lambda: None)
    _module("common.db.redis_client", distributed_lock=None, get_redis_client=None)

    utils_package = _module("common.utils")
    utils_package.__path__ = [str(Path(__file__).resolve().parents[1] / "common/utils")]
    _module("common.utils.default_reply_api", call_reply_api=None)
    _module("common.utils.notification_template", render_notification_template=None)
    _module(
        "common.utils.default_reply_location",
        validate_external_contact_fields=lambda *_args, **_kwargs: None,
    )
    services_package = _module("common.services")
    services_package.__path__ = []
    _module(
        "common.services.remote_location_message_api",
        RemoteLocationMessageError=RuntimeError,
        fetch_remote_location_message=None,
    )
    _module(
        "common.services.ai_provider_service",
        DEFAULT_AI_BASE_URL="https://example.invalid/v1",
        DEFAULT_AI_PROVIDER_TYPE="openai_compatible",
        build_anthropic_url=lambda base, path: f"{base}/{path}",
        build_gemini_url=lambda base, path: f"{base}/{path}",
        clean_ai_text=lambda value: str(value or "").replace("\r", "").replace("\n", "").strip(),
        get_ai_settings_missing_fields=lambda _settings: [],
        get_ai_provider_name=lambda *_args, **_kwargs: "fake",
        normalize_ai_provider_type=lambda *_args, **_kwargs: "openai_compatible",
        normalize_openai_base_url=lambda value: value,
        read_ai_enabled=lambda settings: bool(
            (settings or {}).get("ai_enabled", (settings or {}).get("enabled", False))
        ),
    )

    app = _module("app")
    app.__path__ = []
    app_services = _module("app.services")
    app_services.__path__ = []
    app_xianyu = _module("app.services.xianyu")
    app_xianyu.__path__ = []
    _module("app.services.xianyu.resource_manager", pause_manager=pause_manager)

    class AutoReplyLogService:
        def __init__(self, _cookie_id):
            pass

    _module(
        "app.services.xianyu.auto_reply_log_service",
        AutoReplyLogService=AutoReplyLogService,
    )


def load_auto_reply_module():
    module_name = "tests._auto_reply_service_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    _install_import_stubs()
    source = (
        Path(__file__).resolve().parents[1]
        / "websocket/app/services/xianyu/auto_reply_service.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_ai_reply_settings_service_module():
    module_name = "tests._ai_reply_settings_service_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    _install_import_stubs()
    source = (
        Path(__file__).resolve().parents[1]
        / "backend-web/app/services/ai_reply_service.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_ai_reply_engine_module():
    module_name = "tests._ai_reply_engine_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    _install_import_stubs()
    source = (
        Path(__file__).resolve().parents[1]
        / "websocket/app/services/xianyu/ai_reply_engine.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
