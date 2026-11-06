from __future__ import annotations

import inspect
import asyncio
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.auto_reply_test_harness import (
    load_ai_reply_engine_module,
    load_auto_reply_module,
)


class _FakeXianyu:
    def __init__(self, events: list[str]):
        self.events = events

    async def send_msg(self, **kwargs):
        self.events.append(f"send:{kwargs['content']}")
        return {"success": True}


class _FailingXianyu(_FakeXianyu):
    async def send_msg(self, **kwargs):
        self.events.append(f"send-attempt:{kwargs['content']}")
        raise RuntimeError("offline send failure")


class _FakeAIEngine:
    def __init__(self, events: list[str], settings: dict):
        self.events = events
        self.settings = settings

    async def is_ai_enabled(self, _cookie_id, _session):
        return True

    async def get_ai_settings(self, _cookie_id, _session):
        return self.settings

    def _get_api_provider_name(self, _settings):
        return "fake"

    async def generate_reply(self, **kwargs):
        callback = kwargs.get("pre_generation_callback")
        if callback is not None and await callback() is False:
            return None
        self.events.append("generate")
        return "最终AI回复"


class _DisabledAIEngine(_FakeAIEngine):
    async def is_ai_enabled(self, _cookie_id, _session):
        return False


class _FakeRedis:
    def __init__(self):
        self.values: dict[str, tuple[str, int]] = {}
        self._lock = asyncio.Lock()

    async def set(self, key, value, *, nx=False, ex=None):
        async with self._lock:
            if nx and key in self.values:
                return False
            self.values[key] = (value, ex)
            return True


class _PausingRedis(_FakeRedis):
    def __init__(self, activate_pause):
        super().__init__()
        self.activate_pause = activate_pause

    async def set(self, key, value, *, nx=False, ex=None):
        result = await super().set(key, value, nx=nx, ex=ex)
        self.activate_pause()
        return result


class _ReceiptXianyu(_FakeXianyu):
    def __init__(self, events: list[str]):
        super().__init__(events)
        self.pending: dict[str, asyncio.Future] = {}
        self.tasks: list[asyncio.Task] = []

    async def send_msg(self, **kwargs):
        self.events.append(f"send:{kwargs['content']}")
        mid = "pre-reply-mid"
        future = asyncio.get_running_loop().create_future()
        self.pending[mid] = future
        asyncio.get_running_loop().call_soon(
            future.set_result, {"reason": "CSI_FORBID: 内容被拦截"}
        )
        return {"success": True, "mid": mid, "send_future": future}

    def _create_tracked_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    async def wait_send_reject_reason(self, send_future, mid, timeout=10.0):
        try:
            response = await asyncio.wait_for(send_future, timeout=timeout)
            return response.get("reason")
        finally:
            self.pending.pop(mid, None)


class _FakeScalarResult:
    def first(self):
        return None


class _FakeResult:
    def scalars(self):
        return _FakeScalarResult()


class _FakeSession:
    async def execute(self, _statement):
        return _FakeResult()


class _SessionContext:
    async def __aenter__(self):
        return _FakeSession()

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class _PausingItemSession(_FakeSession):
    def __init__(self, activate_pause):
        self.activate_pause = activate_pause

    async def execute(self, _statement):
        self.activate_pause()
        return _FakeResult()


class _EngineColumn:
    def __eq__(self, other):
        return True

    def __ge__(self, other):
        return self

    def asc(self):
        return self

    def desc(self):
        return self


class _EngineMessage:
    content = created_at = chat_id = cookie_id = role = intent = _EngineColumn()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _EngineResult:
    def __init__(self, *, rows=None, scalar_value=0):
        self.rows = list(rows or [])
        self.scalar_value = scalar_value

    def all(self):
        return self.rows

    def scalar(self):
        return self.scalar_value


class _EngineSession:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def execute(self, _statement):
        return self.results.pop(0)


class AIReplyPreAcknowledgementRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def _service(self, module, events: list[str], account_id: str = "account-a", *, xianyu_cls=_FakeXianyu):
        service = module.AutoReplyService(account_id, xianyu_cls(events))
        service._get_account = AsyncMock(
            return_value=SimpleNamespace(id=1, ai_reply_block_ordered_users=False)
        )
        return service

    async def test_enabled_acknowledgement_is_sent_before_generation(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        service = module.AutoReplyService("account-a", _FakeXianyu(events))
        service._get_account = AsyncMock(
            return_value=SimpleNamespace(id=1, ai_reply_block_ordered_users=False)
        )
        module.get_redis_client = AsyncMock(return_value=_FakeRedis())

        kwargs = {
            "session": object(),
            "send_user_name": "buyer",
            "send_user_id": "buyer-a",
            "send_message": "你好",
            "item_id": None,
            "chat_id": "chat-a",
        }
        if "websocket" in inspect.signature(service.get_ai_reply).parameters:
            kwargs["websocket"] = object()

        reply = await service.get_ai_reply(**kwargs)

        self.assertEqual(reply, "最终AI回复")
        self.assertEqual(events, ["send:收到，稍等一下", "generate"])

    async def test_disabled_acknowledgement_does_not_send(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": False,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        module.get_redis_client = AsyncMock(return_value=_FakeRedis())
        service = self._service(module, events)

        reply = await service.get_ai_reply(
            session=object(),
            send_user_name="buyer",
            send_user_id="buyer-a",
            send_message="你好",
            item_id=None,
            chat_id="chat-a",
            websocket=object(),
        )

        self.assertEqual(reply, "最终AI回复")
        self.assertEqual(events, ["generate"])
        module.get_redis_client.assert_not_awaited()

    async def test_cooldown_is_scoped_by_account_buyer_and_item(self) -> None:
        module = load_auto_reply_module()
        redis = _FakeRedis()
        module.get_redis_client = AsyncMock(return_value=redis)
        settings = {
            "ai_pre_reply_enabled": True,
            "ai_pre_reply_text": "收到，稍等一下",
            "ai_pre_reply_cooldown_minutes": 30,
            "model_name": "fake-model",
        }

        async def run(account_id: str, buyer_id: str, item_id: str) -> list[str]:
            events: list[str] = []
            engine = _FakeAIEngine(events, settings)
            sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
                get_ai_reply_engine=lambda: engine
            )
            service = module.AutoReplyService(account_id, _FakeXianyu(events))
            service._get_account = AsyncMock(
                return_value=SimpleNamespace(id=1, ai_reply_block_ordered_users=False)
            )
            for _ in range(2):
                await service.get_ai_reply(
                    session=_FakeSession(),
                    send_user_name="buyer",
                    send_user_id=buyer_id,
                    send_message="你好",
                    item_id=item_id,
                    chat_id=f"chat-{buyer_id}",
                    websocket=object(),
                )
            return events

        account_a_item_1 = await run("account-a", "buyer-a", "item-1")
        account_a_item_2 = await run("account-a", "buyer-a", "item-2")
        account_a_buyer_b_item_1 = await run("account-a", "buyer-b", "item-1")
        account_b_item_1 = await run("account-b", "buyer-a", "item-1")

        for events in (
            account_a_item_1,
            account_a_item_2,
            account_a_buyer_b_item_1,
            account_b_item_1,
        ):
            self.assertEqual(events.count("send:收到，稍等一下"), 1)
            self.assertEqual(events.count("generate"), 2)
        self.assertEqual(len(redis.values), 4)
        self.assertTrue(all(ttl == 30 * 60 for _value, ttl in redis.values.values()))

    async def test_concurrent_messages_send_only_one_acknowledgement(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        redis = _FakeRedis()
        module.get_redis_client = AsyncMock(return_value=redis)
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        service = self._service(module, events)

        await asyncio.gather(*(
            service.get_ai_reply(
                session=object(),
                send_user_name="buyer",
                send_user_id="buyer-a",
                send_message=f"消息-{index}",
                item_id=None,
                chat_id="chat-a",
                websocket=object(),
            )
            for index in range(12)
        ))

        self.assertEqual(events.count("send:收到，稍等一下"), 1)
        self.assertEqual(events.count("generate"), 12)

    async def test_send_failure_keeps_cooldown_and_does_not_block_ai(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        module.get_redis_client = AsyncMock(return_value=_FakeRedis())
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        service = self._service(module, events, xianyu_cls=_FailingXianyu)

        for _ in range(2):
            reply = await service.get_ai_reply(
                session=object(),
                send_user_name="buyer",
                send_user_id="buyer-a",
                send_message="你好",
                item_id=None,
                chat_id="chat-a",
                websocket=object(),
            )
            self.assertEqual(reply, "最终AI回复")

        self.assertEqual(events.count("send-attempt:收到，稍等一下"), 1)
        self.assertEqual(events.count("generate"), 2)

    async def test_existing_ai_blocking_gates_never_send_acknowledgement(self) -> None:
        module = load_auto_reply_module()

        async def run_case(*, ordered=False, ai_enabled=True, manual_paused=False):
            events: list[str] = []
            settings = {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "manual_reply_ai_pause_enabled": manual_paused,
                "manual_reply_ai_pause_minutes": 10,
                "model_name": "fake-model",
            }
            engine_cls = _FakeAIEngine if ai_enabled else _DisabledAIEngine
            engine = engine_cls(events, settings)
            sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
                get_ai_reply_engine=lambda: engine
            )
            module.get_redis_client = AsyncMock(return_value=_FakeRedis())
            service = self._service(module, events)
            service._account = None
            service._get_account = AsyncMock(
                return_value=SimpleNamespace(
                    id=1,
                    ai_reply_block_ordered_users=ordered,
                )
            )
            service._check_user_has_orders = AsyncMock(return_value=ordered)
            original_remaining = module.pause_manager.get_remaining_ai_pause_time
            module.pause_manager.get_remaining_ai_pause_time = (
                (lambda *_args, **_kwargs: 120)
                if manual_paused
                else (lambda *_args, **_kwargs: 0)
            )
            try:
                reply = await service.get_ai_reply(
                    session=object(),
                    send_user_name="buyer",
                    send_user_id="buyer-a",
                    send_message="你好",
                    item_id=None,
                    chat_id="chat-a",
                    websocket=object(),
                )
            finally:
                module.pause_manager.get_remaining_ai_pause_time = original_remaining
            self.assertIsNone(reply)
            self.assertEqual(events, [])
            module.get_redis_client.assert_not_awaited()

        await run_case(ordered=True)
        await run_case(ai_enabled=False)
        await run_case(manual_paused=True)

    async def test_item_lookup_takeover_recheck_suppresses_model_and_acknowledgement(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        module.get_redis_client = AsyncMock(return_value=_FakeRedis())
        service = self._service(module, events)
        takeover = False
        original_is_chat_paused = module.pause_manager.is_chat_paused
        module.pause_manager.is_chat_paused = lambda *_args, **_kwargs: takeover

        def activate_pause():
            nonlocal takeover
            takeover = True

        try:
            reply = await service.get_ai_reply(
                session=_PausingItemSession(activate_pause),
                send_user_name="buyer",
                send_user_id="buyer-a",
                send_message="你好",
                item_id="item-a",
                chat_id="chat-a",
                websocket=object(),
            )
        finally:
            module.pause_manager.is_chat_paused = original_is_chat_paused

        self.assertIsNone(reply)
        self.assertEqual(events, [])
        module.get_redis_client.assert_not_awaited()

    async def test_redis_await_takeover_recheck_suppresses_send_and_model(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "manual_reply_ai_pause_enabled": True,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        service = self._service(module, events)
        takeover = False
        module.get_redis_client = AsyncMock(
            return_value=_PausingRedis(lambda: activate_pause())
        )
        original_remaining = module.pause_manager.get_remaining_ai_pause_time
        original_is_ai_paused = module.pause_manager.is_ai_reply_paused
        module.pause_manager.get_remaining_ai_pause_time = lambda *_args, **_kwargs: 0
        module.pause_manager.is_ai_reply_paused = lambda *_args, **_kwargs: takeover

        def activate_pause():
            nonlocal takeover
            takeover = True

        try:
            reply = await service.get_ai_reply(
                session=object(),
                send_user_name="buyer",
                send_user_id="buyer-a",
                send_message="你好",
                item_id=None,
                chat_id="chat-a",
                websocket=object(),
            )
        finally:
            module.pause_manager.get_remaining_ai_pause_time = original_remaining
            module.pause_manager.is_ai_reply_paused = original_is_ai_paused

        self.assertIsNone(reply)
        self.assertEqual(events, [])

    async def test_pre_reply_future_is_consumed_and_rejection_enters_trace(self) -> None:
        module = load_auto_reply_module()
        events: list[str] = []
        engine = _FakeAIEngine(
            events,
            {
                "ai_pre_reply_enabled": True,
                "ai_pre_reply_text": "收到，稍等一下",
                "ai_pre_reply_cooldown_minutes": 30,
                "model_name": "fake-model",
            },
        )
        sys.modules["app.services.xianyu.ai_reply_engine"] = types.SimpleNamespace(
            get_ai_reply_engine=lambda: engine
        )
        module.get_redis_client = AsyncMock(return_value=_FakeRedis())
        xianyu = _ReceiptXianyu(events)
        service = module.AutoReplyService("account-a", xianyu)
        service._get_account = AsyncMock(
            return_value=SimpleNamespace(id=1, ai_reply_block_ordered_users=False)
        )
        trace = {"context_snapshot": {}}
        token = service._reply_trace_var.set(trace)
        try:
            reply = await service.get_ai_reply(
                session=object(),
                send_user_name="buyer",
                send_user_id="buyer-a",
                send_message="你好",
                item_id=None,
                chat_id="chat-a",
                websocket=object(),
            )
            await asyncio.gather(*xianyu.tasks)
        finally:
            service._reply_trace_var.reset(token)

        self.assertEqual(reply, "最终AI回复")
        self.assertEqual(events, ["send:收到，稍等一下", "generate"])
        self.assertEqual(xianyu.pending, {})
        pre_reply_trace = trace["context_snapshot"]["ai_pre_reply"]
        self.assertEqual(pre_reply_trace["send_status"], "failed")
        self.assertIn("CSI_FORBID", pre_reply_trace["reject_reason"])

    async def test_keyword_and_default_reply_paths_do_not_enter_ai_acknowledgement(self) -> None:
        module = load_auto_reply_module()
        module.async_session_maker = lambda: _SessionContext()
        service = self._service(module, [])
        service.get_keyword_reply = AsyncMock(return_value="关键词回复")
        service.get_ai_reply = AsyncMock(return_value=None)
        service.get_default_reply = AsyncMock(return_value="默认回复")

        keyword_reply = await service.get_reply(
            "buyer", "buyer-a", "命中关键词", "chat-a", websocket=object()
        )
        self.assertEqual(keyword_reply, "关键词回复")
        service.get_ai_reply.assert_not_awaited()
        service.get_default_reply.assert_not_awaited()


        service.get_keyword_reply.reset_mock(return_value=True)
        service.get_keyword_reply.return_value = None
        default_reply = await service.get_reply(
            "buyer", "buyer-a", "普通消息", "chat-a", websocket=object()
        )
        self.assertEqual(default_reply, "默认回复")
        service.get_ai_reply.assert_awaited_once()
        service.get_default_reply.assert_awaited_once()


class AIReplyEnginePreGenerationCallbackTest(unittest.IsolatedAsyncioTestCase):
    def _engine_and_session(self, *, bargain_count=0, intent="default", settings=None):
        module = load_ai_reply_engine_module()
        module.AIChatMessage = _EngineMessage
        engine = module.AIReplyEngine()
        engine.is_ai_enabled = AsyncMock(return_value=True)
        engine.detect_intent = lambda *_args, **_kwargs: intent
        engine.get_ai_settings = AsyncMock(
            return_value=settings
            or {
                "ai_enabled": True,
                "api_key": "offline-key",
                "provider_type": "openai_compatible",
                "model_name": "offline-model",
            }
        )
        session = _EngineSession(
            [
                _EngineResult(rows=[]),
                _EngineResult(rows=[]),
                _EngineResult(scalar_value=bargain_count),
            ]
        )
        return module, engine, session

    async def test_bargain_limit_real_engine_skips_callback_and_provider(self) -> None:
        _module, engine, session = self._engine_and_session(
            bargain_count=3,
            intent="price",
            settings={
                "ai_enabled": True,
                "api_key": "offline-key",
                "max_bargain_rounds": 3,
            },
        )
        callback = AsyncMock(return_value=True)
        engine._call_openai_api = AsyncMock(return_value="不应调用")

        reply = await engine.generate_reply(
            message="再便宜点",
            item_info={"title": "测试商品", "price": 10, "desc": "离线测试"},
            chat_id="chat-a",
            cookie_id="account-a",
            user_id="buyer-a",
            item_id="item-a",
            db_session=session,
            skip_wait=True,
            pre_generation_callback=callback,
        )

        self.assertIn("不能再便宜", reply)
        callback.assert_not_awaited()
        engine._call_openai_api.assert_not_awaited()

    async def test_callback_exception_does_not_block_real_engine_provider(self) -> None:
        _module, engine, session = self._engine_and_session()
        callback = AsyncMock(side_effect=RuntimeError("offline callback failure"))
        engine._call_openai_api = AsyncMock(return_value="最终回复")
        engine._save_ai_message_with_retry = AsyncMock(return_value=True)

        reply = await engine.generate_reply(
            message="你好",
            item_info={"title": "测试商品", "price": 10, "desc": "离线测试"},
            chat_id="chat-a",
            cookie_id="account-a",
            user_id="buyer-a",
            item_id="item-a",
            db_session=session,
            skip_wait=True,
            pre_generation_callback=callback,
        )

        self.assertEqual(reply, "最终回复")
        callback.assert_awaited_once()
        engine._call_openai_api.assert_awaited_once()

    async def test_takeover_during_callback_suppresses_real_engine_provider(self) -> None:
        module, engine, session = self._engine_and_session()
        engine._call_openai_api = AsyncMock(return_value="不应调用")
        takeover = False
        original_is_chat_paused = module.pause_manager.is_chat_paused
        module.pause_manager.is_chat_paused = lambda *_args, **_kwargs: takeover

        async def activate_takeover():
            nonlocal takeover
            takeover = True
            return True

        try:
            reply = await engine.generate_reply(
                message="你好",
                item_info={"title": "测试商品", "price": 10, "desc": "离线测试"},
                chat_id="chat-a",
                cookie_id="account-a",
                user_id="buyer-a",
                item_id="item-a",
                db_session=session,
                skip_wait=True,
                pre_generation_callback=activate_takeover,
            )
        finally:
            module.pause_manager.is_chat_paused = original_is_chat_paused

        self.assertIsNone(reply)
        engine._call_openai_api.assert_not_awaited()


    async def test_chat_manual_takeover_gate_runs_before_all_reply_rules(self) -> None:
        module = load_auto_reply_module()
        service = module.AutoReplyService("account-a", _FakeXianyu([]))
        service._get_account = AsyncMock(
            return_value=SimpleNamespace(id=1, ai_reply_block_ordered_users=False)
        )
        service.get_keyword_reply = AsyncMock()
        service.get_ai_reply = AsyncMock()
        service.get_default_reply = AsyncMock()
        original_is_paused = module.pause_manager.is_chat_paused
        module.pause_manager.is_chat_paused = lambda *_args, **_kwargs: True
        module.pause_manager.get_remaining_pause_time = lambda *_args, **_kwargs: 60
        try:
            reply = await service.get_reply(
                "buyer", "buyer-a", "你好", "chat-a", websocket=object()
            )
        finally:
            module.pause_manager.is_chat_paused = original_is_paused

        self.assertIsNone(reply)
        service.get_keyword_reply.assert_not_awaited()
        service.get_ai_reply.assert_not_awaited()
        service.get_default_reply.assert_not_awaited()


class TextSendCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def _send(self, error):
        import ast
        import json
        from pathlib import Path
        from unittest.mock import patch

        source = Path(__file__).resolve().parents[1] / "websocket/app/services/xianyu/xianyu_async.py"
        tree = ast.parse(source.read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "send_msg")
        namespace = {
            "asyncio": asyncio,
            "json": json,
            "logger": SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None),
            "is_xianyu_official_robot_user": lambda value: False,
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        fake_utils = types.ModuleType("common.utils.xianyu_utils")
        fake_utils.generate_mid = lambda: "offline-mid"
        fake_utils.generate_uuid = lambda: "offline-uuid"
        client = SimpleNamespace(cookie_id="offline", myid="self", _pending_mid_futures={}, _safe_str=str)
        socket = SimpleNamespace(send=AsyncMock(side_effect=error))
        with patch.dict(sys.modules, {"common.utils.xianyu_utils": fake_utils}):
            if isinstance(error, asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await namespace["send_msg"](client, socket, "chat", "buyer", "收到")
            else:
                result = await namespace["send_msg"](client, socket, "chat", "buyer", "收到")
                self.assertFalse(result["success"])
        self.assertEqual(client._pending_mid_futures, {})

    async def test_socket_error_cleans_pending_future(self):
        await self._send(RuntimeError("offline socket failure"))

    async def test_socket_cancellation_cleans_pending_future(self):
        await self._send(asyncio.CancelledError())


if __name__ == "__main__":
    unittest.main()
