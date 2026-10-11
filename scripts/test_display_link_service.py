"""
display_link_service 校验/合并纯函数测试

覆盖 image 类型校验、字段白名单收敛、长度上限、``..`` 路径段拦截、默认模板合并去重、
以及提货页读取侧「先规范化再合并」（非法商品条目不得遮蔽同名默认模板）。
运行：python scripts/test_display_link_service.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend-web"))

from app.services.agree_pickup_service import AgreePickupService
from app.services.display_link_service import (
    merge_display_links,
    normalize_display_links,
    template_row_to_entry,
    validate_display_link_entry,
    validate_display_links,
)
from common.utils.local_image_upload import build_unique_filename


def test_image_relative_url_ok() -> None:
    ok, message, entry = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "/static/uploads/display_links/a.png", "note": "扫码进群"}
    )
    assert ok, message
    assert entry == {
        "name": "QQ群", "type": "image",
        "url": "/static/uploads/display_links/a.png", "note": "扫码进群",
    }


def test_image_external_url_ok_and_extra_keys_dropped() -> None:
    """字段白名单：多余键（如 cookie/headers）必须被丢弃，防泄漏给买家"""
    ok, message, entry = validate_display_link_entry(
        {"name": "微信群", "type": "image", "url": "https://img.example.com/qr.png", "cookie": "secret"}
    )
    assert ok, message
    assert entry == {"name": "微信群", "type": "image", "url": "https://img.example.com/qr.png"}
    assert "cookie" not in entry


def test_link_extra_keys_dropped() -> None:
    """字段白名单：link 条目误拷的 headers/cookie/method 必须被丢弃"""
    ok, message, entry = validate_display_link_entry(
        {
            "name": "网盘下载",
            "type": "link",
            "url": "https://pan.example.com/s/abc",
            "headers": {"Cookie": "secret"},
            "cookie": "secret",
            "method": "POST",
        }
    )
    assert ok, message
    assert entry == {"name": "网盘下载", "type": "link", "url": "https://pan.example.com/s/abc"}


def test_text_extra_keys_dropped() -> None:
    """字段白名单：text 条目不适用字段（url/note）与多余键必须被丢弃"""
    ok, message, entry = validate_display_link_entry(
        {
            "name": "查看账号",
            "type": "text",
            "title": "发货信息",
            "content": "正文",
            "url": "https://pan.example.com/s/abc",
            "note": "备注",
            "headers": {"Cookie": "secret"},
        }
    )
    assert ok, message
    assert entry == {"name": "查看账号", "type": "text", "title": "发货信息", "content": "正文"}


def test_length_caps_rejected() -> None:
    """长度上限与 DB 列宽一致（name/note/title 255、url 512），超长写入会被数据库拒绝"""
    ok, message, _ = validate_display_link_entry(
        {"name": "名" * 256, "type": "image", "url": "/static/a.png"}
    )
    assert not ok and "按钮名称" in message and "255" in message, message

    ok, message, _ = validate_display_link_entry(
        {"name": "下载", "type": "link", "url": "https://pan.example.com/" + "a" * 600}
    )
    assert not ok and "链接地址" in message and "512" in message, message

    ok, message, _ = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "/static/" + "a" * 600}
    )
    assert not ok and "图片地址" in message and "512" in message, message

    ok, message, _ = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "/static/a.png", "note": "备" * 256}
    )
    assert not ok and "备注" in message and "255" in message, message

    ok, message, _ = validate_display_link_entry(
        {"name": "查看账号", "type": "text", "title": "标" * 256, "content": "正文"}
    )
    assert not ok and "弹窗标题" in message and "255" in message, message


def test_length_caps_boundary_accepted() -> None:
    """恰好等于列宽上限的条目仍然合法（边界不误杀）"""
    ok, message, _ = validate_display_link_entry(
        {
            "name": "名" * 255,
            "type": "image",
            "url": "/static/" + "a" * (512 - len("/static/")),
            "note": "备" * 255,
        }
    )
    assert ok, message

    ok, message, _ = validate_display_link_entry(
        {"name": "查看账号", "type": "text", "title": "标" * 255, "content": "正文"}
    )
    assert ok, message


def test_url_dotdot_segment_rejected() -> None:
    """URL 含 ``..`` 路径段：/static/../x.png 不得绕过 /static/ 前缀检查"""
    ok, message, _ = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "/static/../x.png"}
    )
    assert not ok and ".." in message, message

    for bad_url in ("https://pan.example.com/../etc/passwd", "https://pan.example.com/a/../b"):
        ok, message, _ = validate_display_link_entry({"name": "下载", "type": "link", "url": bad_url})
        assert not ok and ".." in message, bad_url

    # 文件名/查询串里的 ".." 不是独立路径段，不误伤
    ok, message, _ = validate_display_link_entry(
        {"name": "下载", "type": "link", "url": "https://pan.example.com/x..y/z?k=a..b"}
    )
    assert ok, message


def test_template_row_to_entry_field_convergence() -> None:
    """类型切换收敛：text 行不下发 url/note，link/image 行不下发 title/content"""
    # 模拟类型切换后 DB 行仍残留上一类型的列值
    text_row = SimpleNamespace(
        name="查看账号", type="text", title="发货信息", content="正文",
        url="/static/old.png", note="旧备注",
    )
    entry = template_row_to_entry(text_row)
    assert entry == {"name": "查看账号", "type": "text", "title": "发货信息", "content": "正文"}
    assert "url" not in entry and "note" not in entry

    image_row = SimpleNamespace(
        name="QQ群", type="image", url="/static/a.png", note="扫码进群",
        title="旧标题", content="旧正文",
    )
    entry = template_row_to_entry(image_row)
    assert entry == {"name": "QQ群", "type": "image", "url": "/static/a.png", "note": "扫码进群"}
    assert "title" not in entry and "content" not in entry

    link_row = SimpleNamespace(
        name="下载", type="link", url="https://a.com", note=None, title=None, content=None
    )
    assert template_row_to_entry(link_row) == {"name": "下载", "type": "link", "url": "https://a.com"}


def test_normalize_display_links_drops_invalid_and_extra_keys() -> None:
    """读取侧规范化：逐条丢弃非法项与多余键，非数组输入按空处理"""
    raw = [
        {"name": "下载", "type": "link", "url": "https://pan.example.com/s/abc",
         "headers": {"Cookie": "secret"}},
        "不是对象",
        {"name": "QQ群", "type": "image"},  # 缺 url
    ]
    assert normalize_display_links(raw) == [
        {"name": "下载", "type": "link", "url": "https://pan.example.com/s/abc"}
    ]
    assert normalize_display_links(None) == []
    assert normalize_display_links({"name": "x", "type": "image", "url": "/static/a.png"}) == []


def test_image_missing_url_rejected() -> None:
    ok, message, _ = validate_display_link_entry({"name": "QQ群", "type": "image"})
    assert not ok and "图片地址" in message


def test_image_invalid_protocol_rejected() -> None:
    ok, message, _ = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "ftp://x/a.png"}
    )
    assert not ok and "/static/" in message


def test_image_missing_name_rejected() -> None:
    ok, message, _ = validate_display_link_entry({"name": "  ", "type": "image", "url": "/static/a.png"})
    assert not ok and "名称" in message


def test_batch_validate_error_position() -> None:
    ok, message, _ = validate_display_links([
        {"name": "A", "type": "link", "url": "https://a.com"},
        {"name": "B", "type": "image"},
    ])
    assert not ok and message.startswith("第 2 个入口")


def test_merge_item_first_and_dedup_by_name() -> None:
    item = [{"name": "QQ群", "type": "image", "url": "/static/own.png"}]
    templates = [
        {"name": " qq群 ", "type": "image", "url": "/static/tpl.png"},  # 同名（忽略大小写/空白）→ 去重
        {"name": "微信群", "type": "image", "url": "/static/wx.png"},
    ]
    merged = merge_display_links(item, templates)
    assert merged == [
        {"name": "QQ群", "type": "image", "url": "/static/own.png"},
        {"name": "微信群", "type": "image", "url": "/static/wx.png"},
    ]


def test_merge_empty_template_name_skipped() -> None:
    merged = merge_display_links([], [{"name": "  ", "type": "image", "url": "/static/a.png"}])
    assert merged == []


def test_invalid_item_entry_does_not_shadow_default_template() -> None:
    """规范化必须先于合并：非法商品条目不得按名称遮蔽同名默认模板。

    旧实现「先合并去重、后过滤」时，缺 url 的 "QQ群" 会占住名称，模板被丢弃 → 买家看不到入口。
    """
    item_links = [{"name": "QQ群", "type": "image", "cookie": "secret"}]
    template_links = [{"name": "QQ群", "type": "image", "url": "/static/tpl.png"}]
    merged = merge_display_links(
        normalize_display_links(item_links), normalize_display_links(template_links)
    )
    assert merged == [{"name": "QQ群", "type": "image", "url": "/static/tpl.png"}]


class _FakeScalarResult:
    """只实现 _load_display_links 用到的 scalars()/first()/all()"""

    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def scalars(self) -> "_FakeScalarResult":
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self) -> list:
        return list(self._rows)


class _FakeSession:
    """按 execute 调用顺序返回预置结果（第 1 次商品行，第 2 次默认模板行）"""

    def __init__(self, *results: list) -> None:
        self._results = [_FakeScalarResult(rows) for rows in results]

    async def execute(self, _stmt):
        return self._results.pop(0)


def test_load_display_links_normalize_then_merge() -> None:
    """提货页读取侧：多余键被丢弃 + 非法商品条目不遮蔽同名默认模板"""
    order = SimpleNamespace(order_no="O1", owner_id=1, item_id="1084757003552")
    item = SimpleNamespace(
        metadata_json={
            "display_links": [
                # 缺 url 的非法条目，名称与默认模板相同 → 不得遮蔽模板
                {"name": "QQ群", "type": "image", "cookie": "secret"},
                # 合法条目：passthrough 写入的 headers 必须被丢弃
                {"name": "网盘下载", "type": "link", "url": "https://pan.example.com/s/abc",
                 "headers": {"Cookie": "secret"}},
            ]
        }
    )
    template = SimpleNamespace(
        name="QQ群", type="image", url="/static/tpl.png", note=None, title=None, content=None
    )
    service = AgreePickupService(_FakeSession([item], [template]))
    links = asyncio.run(service._load_display_links(order))
    assert links == [
        {"name": "网盘下载", "type": "link", "url": "https://pan.example.com/s/abc"},
        {"name": "QQ群", "type": "image", "url": "/static/tpl.png"},
    ]


def test_load_display_links_without_item_or_template() -> None:
    """商品不存在 / metadata 无 display_links / 无默认模板 → 空数组，不抛异常"""
    order = SimpleNamespace(order_no="O1", owner_id=1, item_id="1084757003552")
    service = AgreePickupService(_FakeSession([None], []))
    assert asyncio.run(service._load_display_links(order)) == []

    service = AgreePickupService(_FakeSession([SimpleNamespace(metadata_json={})], []))
    assert asyncio.run(service._load_display_links(order)) == []

    # item_id 缺失时直接返回空数组，不查库
    service = AgreePickupService(_FakeSession())
    assert asyncio.run(service._load_display_links(SimpleNamespace(order_no="O1", owner_id=1, item_id=None))) == []


def test_upload_filename_prefix_sanitized() -> None:
    """展示入口图片上传以 item_id 作前缀（URL 路径参数 + DB 自由字符串），必须防路径穿越"""
    filename = build_unique_filename("a.png", prefix="../../x")
    assert filename.startswith(".._.._x_")
    assert "/" not in filename and "\\" not in filename
    # 落盘后仍在上传目录内（filename 不含目录分隔符即无法逃出）
    upload_dir = Path(_REPO_ROOT) / "backend-web" / "static" / "uploads" / "display_links"
    assert (upload_dir / filename).resolve().parent == upload_dir.resolve()

    assert build_unique_filename("a.png", prefix="..\\..\\x").startswith(".._.._x_")
    assert build_unique_filename("a.png", prefix="C:\\tmp\\x").startswith("C__tmp_x_")

    # 现有调用方前缀（tpl / ai / 数字账号 id / cookie_id_item_id）不受影响
    for prefix in ("tpl", "ai", "1234567", "unb1234567", "unb1234567_1084757003552"):
        assert build_unique_filename("a.png", prefix=prefix).startswith(f"{prefix}_")

    # 空前缀保持无前缀命名
    bare = build_unique_filename("a.png", prefix="")
    assert bare.endswith(".png") and not bare.startswith("_")


if __name__ == "__main__":
    test_image_relative_url_ok()
    test_image_external_url_ok_and_extra_keys_dropped()
    test_link_extra_keys_dropped()
    test_text_extra_keys_dropped()
    test_length_caps_rejected()
    test_length_caps_boundary_accepted()
    test_url_dotdot_segment_rejected()
    test_template_row_to_entry_field_convergence()
    test_normalize_display_links_drops_invalid_and_extra_keys()
    test_image_missing_url_rejected()
    test_image_invalid_protocol_rejected()
    test_image_missing_name_rejected()
    test_batch_validate_error_position()
    test_merge_item_first_and_dedup_by_name()
    test_merge_empty_template_name_skipped()
    test_invalid_item_entry_does_not_shadow_default_template()
    test_load_display_links_normalize_then_merge()
    test_load_display_links_without_item_or_template()
    test_upload_filename_prefix_sanitized()
    print("全部测试通过")
