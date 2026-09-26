"""
query_template 纯函数模块测试脚本

直接用 ``python scripts/test_query_template.py`` 运行，全部 assert 通过即成功。
不依赖 fastapi / sqlalchemy / httpx，可用系统 Python 直接执行。
"""
from __future__ import annotations

import os
import sys

# 仓库根目录加入 sys.path，使 common 包可导入（脚本可从任意目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.services.query_template import (
    extract_card_variables,
    mask_account,
    render_template,
    resolve_path,
    template_url_has_variable_host,
)


def test_extract_card_variables() -> None:
    """卡密行四变量提取：全字段行 / 描述行 / 半角冒号行 / 缺失变量"""
    line = "账号：13797782162 API Key：sk_tr_aaa 余额：67.97 Cookie：tr_session=x; Path=/"
    variables = extract_card_variables(line)
    assert variables["account"] == "13797782162"
    assert variables["api_key"] == "sk_tr_aaa"
    assert variables["cookie"] == "tr_session=x; Path=/"
    assert variables["line"] == line

    # 描述前缀行（无账号/Cookie 标记）不干扰：变量全部为空串，line 为整行原文
    desc = extract_card_variables("基元律动68余额号（每行一个账号）")
    assert desc["account"] == ""
    assert desc["api_key"] == ""
    assert desc["cookie"] == ""
    assert desc["line"] == "基元律动68余额号（每行一个账号）"

    # 半角冒号 + API Key 无空格写法均可识别
    half = extract_card_variables("账号:13800001111 APIKey:sk_tr_bbb Cookie:tr_session=y")
    assert half["account"] == "13800001111"
    assert half["api_key"] == "sk_tr_bbb"
    assert half["cookie"] == "tr_session=y"

    # 缺失变量为空串；None 输入不抛异常
    partial = extract_card_variables("账号：13797782162")
    assert partial["cookie"] == "" and partial["api_key"] == ""
    assert extract_card_variables(None)["line"] == ""


def test_render_template() -> None:
    """模板变量替换：已知变量替换、未知变量原样保留、None 原样返回"""
    variables = {"api_key": "sk_tr_aaa", "cookie": "tr_session=x", "account": "13797782162", "line": "L"}
    assert render_template("Bearer {api_key}", variables) == "Bearer sk_tr_aaa"
    assert render_template("key={api_key}&foo={foo}", variables) == "key=sk_tr_aaa&foo={foo}"
    assert render_template(None, variables) is None
    assert render_template("无占位符", variables) == "无占位符"


def test_resolve_path() -> None:
    """点路径取值：嵌套字典+数组下标、错误路径返回 None"""
    payload = {"a": {"b": [{"c": 1}]}}
    assert resolve_path(payload, "a.b.0.c") == 1
    assert resolve_path(payload, "a.b.9.c") is None
    assert resolve_path(payload, "a.x.c") is None
    assert resolve_path(payload, "a.b.0.c.d") is None
    assert resolve_path({"code": 0, "data": {"v": "52.28"}}, "data.v") == "52.28"
    # 空路径返回 payload 本身；非标量按原样返回
    assert resolve_path(payload, "") == payload
    assert resolve_path({"list": [1, 2]}, "list") == [1, 2]


def test_mask_account() -> None:
    """账号脱敏：长账号前3后4、短账号首字符、None 原样返回"""
    assert mask_account("13797782162") == "137****2162"
    assert mask_account("15012346428") == "150****6428"
    assert mask_account("abcdefg") == "abc****defg"
    assert mask_account("abc") == "a***"
    assert mask_account("ab") == "a***"
    assert mask_account("a") == "***"
    assert mask_account("") == "***"
    assert mask_account(None) is None


def test_template_url_has_variable_host() -> None:
    """SSRF 防护：host 段含变量判危险，path/query 含变量放行"""
    assert template_url_has_variable_host("https://{cookie}/api/wallet") is True
    assert template_url_has_variable_host("https://api.example.com/{account}") is False
    assert template_url_has_variable_host("https://api.example.com/summary?k={api_key}") is False
    assert template_url_has_variable_host("https://api.example.com/wallet/summary") is False
    assert template_url_has_variable_host("") is True
    assert template_url_has_variable_host(None) is True


if __name__ == "__main__":
    test_extract_card_variables()
    test_render_template()
    test_resolve_path()
    test_mask_account()
    test_template_url_has_variable_host()
    print("全部断言通过：query_template 纯函数行为符合契约")
