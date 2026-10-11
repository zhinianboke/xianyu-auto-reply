"""
display_links 校验纯函数测试脚本

覆盖 backend-web/app/services/display_link_service.py 的 validate_display_links（item_query.py 以 _validate_display_links 别名引用）：
商品展示入口配置（买家提货页外链按钮 / 文本弹窗 / 图片入口）的字段校验与规范化。

直接用 ``python scripts/test_display_links.py`` 运行，全部 assert 通过即成功。
依赖 fastapi / sqlalchemy（路由模块顶层导入），需先安装 backend-web 依赖。
"""
from __future__ import annotations

import os
import sys

# 仓库根目录（common 包）与 backend-web（app 包）加入 sys.path，脚本可从任意目录运行
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend-web"))

from app.api.routes.item_query import _validate_display_links


def test_valid_link_with_note() -> None:
    """link 类型：name/url 去空白规范化，可选 note 透传"""
    ok, message, links = _validate_display_links([
        {"name": "  网盘下载  ", "type": "link", "url": " https://pan.example.com/s/abc ", "note": "提取码：xE7e"},
    ])
    assert ok, message
    assert links == [
        {"name": "网盘下载", "type": "link", "url": "https://pan.example.com/s/abc", "note": "提取码：xE7e"}
    ]


def test_valid_text_preserves_multiline_content() -> None:
    """text 类型：多行 content 原文保留（含换行与 {cookie} 占位符），title 去空白"""
    content = "账号信息：\n{cookie}\n\n请妥善保管\n"
    ok, message, links = _validate_display_links([
        {"name": "查看账号", "type": "text", "title": " 发货信息 ", "content": content},
    ])
    assert ok, message
    assert links[0]["title"] == "发货信息"
    assert links[0]["content"] == content


def test_empty_list_ok() -> None:
    """空数组合法（清空配置）"""
    ok, message, links = _validate_display_links([])
    assert ok and links == []


def test_non_dict_entry_rejected() -> None:
    ok, message, _ = _validate_display_links(["不是对象"])
    assert not ok and "第 1 个入口配置格式不正确" == message


def test_missing_name_rejected() -> None:
    ok, message, _ = _validate_display_links([
        {"type": "link", "url": "https://example.com"},
    ])
    assert not ok and "第 1 个入口缺少按钮名称" == message


def test_invalid_type_rejected() -> None:
    """type 缺失或不在 link/text/image 枚举内一律拒绝"""
    for link in (
        {"name": "x"},
        {"name": "x", "type": "LINK"},
    ):
        ok, message, _ = _validate_display_links([link])
        assert not ok and "第 1 个入口的类型仅支持 link/text/image" == message, link


def test_link_url_rules() -> None:
    """link 类型：url 必填且必须 http(s) 开头"""
    ok, message, _ = _validate_display_links([{"name": "x", "type": "link"}])
    assert not ok and "第 1 个入口缺少链接地址" == message

    for bad_url in ("ftp://example.com", "www.example.com", "javascript:alert(1)"):
        ok, message, _ = _validate_display_links([{"name": "x", "type": "link", "url": bad_url}])
        assert not ok and "必须以 http:// 或 https:// 开头" in message, bad_url

    ok, _, _ = _validate_display_links([{"name": "x", "type": "link", "url": "http://example.com"}])
    assert ok


def test_text_title_content_required() -> None:
    """text 类型：title/content 必填且去空白后非空"""
    ok, message, _ = _validate_display_links([{"name": "x", "type": "text", "content": "正文"}])
    assert not ok and "第 1 个入口缺少弹窗标题" == message

    for bad_content in (None, "", "   \n  "):
        ok, message, _ = _validate_display_links([{"name": "x", "type": "text", "title": "标题", "content": bad_content}])
        assert not ok and "第 1 个入口缺少弹窗内容" == message, repr(bad_content)


def test_error_message_positions_second_entry() -> None:
    """多条配置时错误信息定位到具体序号"""
    ok, message, _ = _validate_display_links([
        {"name": "a", "type": "link", "url": "https://a.com"},
        {"name": "b", "type": "text", "title": "", "content": "x"},
    ])
    assert not ok and message.startswith("第 2 个入口")


if __name__ == "__main__":
    test_valid_link_with_note()
    test_valid_text_preserves_multiline_content()
    test_empty_list_ok()
    test_non_dict_entry_rejected()
    test_missing_name_rejected()
    test_invalid_type_rejected()
    test_link_url_rules()
    test_text_title_content_required()
    test_error_message_positions_second_entry()
    print("全部测试通过")
