"""定时擦亮任务回归测试：平台侧「已下架」不得删除本地商品目录行。

背景（真实缺陷，已修复）：
    `xy_catalog_items` 是本地商品目录，行上承载了用户配置的 `ai_prompt` 与
    `metadata`（`display_links` 展示入口、`query_buttons`、`is_multi_spec` 等）。
    定时擦亮任务原来把擦亮接口的
        `FAIL_BIZ_UNSUPPORTED_ITEM_STATUS::已下架商品不支持该操作`
    当成「商品已不存在」，直接 `session.delete(item)`。而「已下架」只是商品在平台的
    瞬时状态（卖完自动下架 / 卖家手动下架，补货重新上架后同一 item_id 会回到在售），
    删行会连带丢掉上述本地配置；下次商品同步（`_apply_single_item`）只能新增行，
    行 id 变化且配置无法恢复。

修复后语义：
    1. 命中「已下架」只写退避标记 `metadata.platform_offline_at`，不删行；
    2. 退避窗口（默认 2 小时）内不再重复请求擦亮接口；
    3. 擦亮成功即清除该标记（商品已回到在售）。

运行：
    python scripts/test_polish_task_keeps_catalog_row.py
全部 assert 通过即成功（无需数据库、无需网络）。
"""
from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scheduler")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.services.scheduler import polish_task as pt  # noqa: E402
from common.models.xy_catalog_item import XYCatalogItem  # noqa: E402
from common.services.item_service import ItemService  # noqa: E402

FIXED_NOW = datetime(2026, 9, 26, 0, 30, 0)
OFFLINE_ERROR = "FAIL_BIZ_UNSUPPORTED_ITEM_STATUS::已下架商品不支持该操作"
ITEM_ID = "1000000000001"
ACCOUNT_ID = "1000000000000"
POLISH_SRC = REPO_ROOT / "scheduler" / "app" / "services" / "scheduler" / "polish_task.py"
ITEM_SERVICE_SRC = REPO_ROOT / "common" / "services" / "item_service.py"


class _FakeScalars:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _FakeResult:
    def __init__(self, items=None, rowcount=0):
        self._items = list(items or [])
        self.rowcount = rowcount

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeSession:
    """记录 delete/add/commit，用于断言「有没有删行」。"""

    def __init__(self, items=None):
        self._items = list(items or [])
        self.deleted: list = []
        self.added: list = []
        self.commits = 0

    async def execute(self, stmt, *args, **kwargs):
        return _FakeResult(items=self._items)

    async def delete(self, obj):
        self.deleted.append(obj)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _make_item(**metadata) -> XYCatalogItem:
    return XYCatalogItem(
        owner_id=1,
        account_pk=2,
        item_id=ITEM_ID,
        title="测试商品",
        price="1.75",
        ai_prompt="AI 提示词",
        is_polished=False,
        metadata_json={
            "display_links": [{"name": "官网链接", "type": "link", "url": "https://example.com"}],
            "query_buttons": [{"name": "查余额"}],
            **metadata,
        },
    )


def _fake_account() -> types.SimpleNamespace:
    return types.SimpleNamespace(account_id=ACCOUNT_ID, id=2, cookie="c=1")


def _install(monkeypatch_holder: dict, item: XYCatalogItem, polish_result: dict):
    """替换擦亮请求与当前时间，返回（fake session, 调用记录）。"""
    session = _FakeSession([item])
    calls: list = []

    async def _fake_polish(cookie_str, item_id, retry_count=0):
        calls.append(item_id)
        return dict(polish_result)

    monkeypatch_holder["orig_now"] = pt.get_beijing_now_naive
    monkeypatch_holder["orig_polish"] = pt.polish_task_service._polish_item
    pt.get_beijing_now_naive = lambda: FIXED_NOW  # type: ignore[assignment]
    pt.polish_task_service._polish_item = _fake_polish  # type: ignore[assignment]
    return session, calls


def _restore(monkeypatch_holder: dict) -> None:
    if "orig_now" in monkeypatch_holder:
        pt.get_beijing_now_naive = monkeypatch_holder["orig_now"]  # type: ignore[assignment]
    if "orig_polish" in monkeypatch_holder:
        pt.polish_task_service._polish_item = monkeypatch_holder["orig_polish"]  # type: ignore[assignment]


def _run_process_account(session) -> tuple[int, int]:
    return asyncio.run(
        pt.polish_task_service._process_account(session, _fake_account(), "batch-test")
    )


def test_offline_item_is_not_deleted() -> None:
    """核心断言：擦亮接口报「已下架」时只写标记，绝不删除本地商品行。"""
    holder: dict = {}
    item = _make_item()
    session, calls = _install(holder, item, {"success": False, "message": OFFLINE_ERROR})
    try:
        success, failed = _run_process_account(session)
    finally:
        _restore(holder)

    assert calls == [ITEM_ID], "首次发现下架应仍发起一次擦亮请求"
    assert session.deleted == [], "已下架商品不得删除本地记录（配置会随之丢失）"
    assert (success, failed) == (0, 1)
    assert item.metadata_json[pt.PolishTaskService.PLATFORM_OFFLINE_KEY] == FIXED_NOW.isoformat(
        timespec="seconds"
    )
    assert item.ai_prompt == "AI 提示词", "ai_prompt 必须原样保留"
    assert item.metadata_json["display_links"], "display_links 必须原样保留"
    assert item.is_polished is False, "未擦亮成功不应把 is_polished 置真"


def test_offline_cooldown_skips_request() -> None:
    """退避窗口内：不发请求、不删行。"""
    holder: dict = {}
    item = _make_item(platform_offline_at=FIXED_NOW.isoformat(timespec="seconds"))
    session, calls = _install(holder, item, {"success": False, "message": OFFLINE_ERROR})
    try:
        _run_process_account(session)
    finally:
        _restore(holder)

    assert calls == [], "退避窗口内不应重复请求擦亮接口"
    assert session.deleted == []


def test_cooldown_expires_then_retries() -> None:
    """退避窗口过期后重试：商品补货重新上架后当天仍能擦亮。"""
    holder: dict = {}
    item = _make_item(
        platform_offline_at=datetime(2026, 9, 25, 22, 0, 0).isoformat(timespec="seconds")
    )
    session, calls = _install(holder, item, {"success": False, "message": OFFLINE_ERROR})
    try:
        _run_process_account(session)
    finally:
        _restore(holder)

    assert calls == [ITEM_ID], "超过退避窗口应重试"
    assert session.deleted == []


def test_success_clears_offline_marker() -> None:
    """擦亮成功 = 商品已重新在售 → 清掉退避标记。"""
    holder: dict = {}
    item = _make_item(
        platform_offline_at=datetime(2026, 9, 25, 22, 0, 0).isoformat(timespec="seconds")
    )
    session, calls = _install(holder, item, {"success": True, "message": "擦亮成功"})
    try:
        success, failed = _run_process_account(session)
    finally:
        _restore(holder)

    assert calls == [ITEM_ID]
    assert (success, failed) == (1, 0)
    assert pt.PolishTaskService.PLATFORM_OFFLINE_KEY not in item.metadata_json
    assert item.is_polished is True
    assert item.metadata_json["display_links"], "清标记不得影响其它元数据"


def test_sync_preserves_local_config() -> None:
    """商品同步更新已有行时只刷新平台字段，本地配置（ai_prompt/display_links）原样保留。"""
    item = _make_item()
    item.title = "旧标题"
    session = _FakeSession([item])
    service = ItemService(session)
    account = types.SimpleNamespace(owner_id=1, id=2, account_id=ACCOUNT_ID)

    changed = asyncio.run(
        service._apply_single_item(
            account,
            ITEM_ID,
            {"title": "测试商品", "price_text": "1.99", "category_id": "201404604"},
        )
    )

    assert changed is True
    assert item.title == "测试商品"
    assert item.price == "1.99"
    assert item.ai_prompt == "AI 提示词", "同步不得清空 ai_prompt"
    assert item.metadata_json["display_links"], "同步不得清空 metadata.display_links"
    assert item.metadata_json["query_buttons"], "同步不得清空 metadata.query_buttons"
    assert item.metadata_json["category"] == "201404604"
    assert item.metadata_json["detail"], "detail 应随同步刷新"
    assert session.deleted == [], "同步对已存在行只更新，不删行"


def test_source_level_no_catalog_delete() -> None:
    """源码级证据：擦亮任务不得出现删行语句（防回退）。"""
    polish_src = POLISH_SRC.read_text(encoding="utf-8-sig")
    assert "session.delete(item)" not in polish_src, "擦亮任务不得删除商品目录行"
    assert pt.PolishTaskService.PLATFORM_OFFLINE_KEY in polish_src
    assert "已下架，已删除商品记录" not in polish_src

    item_src = ITEM_SERVICE_SRC.read_text(encoding="utf-8-sig")
    assert "if existing_item:" in item_src
    assert "existing_item.title = new_title" in item_src


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # pragma: no cover
            failed += 1
            print(f"[ERROR] {fn.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"[ OK ] {fn.__name__}")
    print(f"\n总计: {len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
