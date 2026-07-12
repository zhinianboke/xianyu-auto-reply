"""
闲鱼账号密码登录接口（login.do）请求与响应分类

功能：
1. 构造 login.do 表单（含 RSA 加密 password2；故意不发 ua 风控指纹，用滑块换 x5sec）
2. 发起 login.do 请求（共享 httpx.AsyncClient 的 cookie jar）
3. 对响应做四分支分类：滑块 / 直接成功 / 触发人脸 / 登录失败

响应分支判据（抓包实证）：
- 滑块：ret 含 FAIL_SYS_USER_VALIDATE + data.url（punish 验证链接）
- 直接成功：content.data.loginResult == "success"（st==success，无 titleMsg / iframeRedirect）
- 触发人脸：content.data.iframeRedirect == true + iframeRedirectUrl（含 mini_login_check）
- 登录失败：content.data.titleMsg（如"密码错误"），无成功标志与跳转
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import httpx

from common.services.xianyu_login.password2 import generate_password2

# login.do 接口地址（含固定查询参数）
LOGIN_DO_URL = "https://passport.goofish.com/newlogin/login.do?appName=xianyu&fromSite=77"

# 请求头（照搬登录页真实请求；不含动态 ua/bx-ua）
LOGIN_HEADERS: Dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="146", "Not=A?Brand";v="8", "Chromium";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Win32"',
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "Origin": "https://passport.goofish.com",
    "Referer": "https://passport.goofish.com/",
}

# login.do 固定表单字段（loginId/password2 运行期填充；不含 ua）
FORM_FIXED: Dict[str, str] = {
    "keepLogin": "false",
    "isIframe": "true",
    "documentReferer": "https://www.goofish.com/",
    "defaultView": "password",
    "appName": "xianyu",
    "appEntrance": "web",
    "bizParams": "taobaoBizLoginFrom=web&renderRefer=https%3A%2F%2Fwww.goofish.com%2F",
    "mainPage": "false",
    "isMobile": "false",
    "lang": "zh_CN",
    "returnUrl": "",
    "fromSite": "77",
    "weiBoMpBridge": "",
    "jsVersion": "0.10.36",
    "screenPixel": "1920x1080",
    "navlanguage": "zh-CN",
    "navUserAgent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "navPlatform": "Win32",
    "umidGetStatusVal": "255",
    "umidTag": "SERVER",
}


class LoginBranch(str, Enum):
    """login.do 响应分支"""

    SLIDER = "slider"      # 需过滑块（拿到 punish 链接）
    SUCCESS = "success"    # 直接登录成功
    FACE = "face"          # 触发人脸验证
    FAIL = "fail"          # 登录失败（密码错误等）
    UNKNOWN = "unknown"    # 无法识别（异常 ret / 结构漂移）


@dataclass
class LoginClassifyResult:
    """login.do 响应分类结果"""

    branch: LoginBranch
    slider_url: Optional[str] = None      # SLIDER：punish 验证链接
    iframe_url: Optional[str] = None      # FACE：iframeRedirectUrl
    fail_message: Optional[str] = None    # FAIL：titleMsg
    raw: Optional[Dict[str, Any]] = None  # 原始响应体（排查用）


def build_login_form(login_id: str, password: str) -> Dict[str, str]:
    """
    构造 login.do 表单

    Args:
        login_id: 登录账号（手机号/邮箱）
        password: 明文密码
    Returns:
        完整表单字典（含加密后的 password2）
    """
    form = dict(FORM_FIXED)
    form["loginId"] = login_id
    form["password2"] = generate_password2(password)
    return form


async def post_login_do(
    client: httpx.AsyncClient,
    form: Dict[str, str],
    extra_cookies: Optional[Dict[str, str]] = None,
) -> httpx.Response:
    """
    发起 login.do 请求

    Args:
        client: 贯穿全流程的 httpx.AsyncClient（携带 cookie jar，滑块后 x5sec 会自动带上）
        form: build_login_form 生成的表单
        extra_cookies: 额外注入的 cookie（如滑块返回的 x5sec）
    Returns:
        httpx.Response
    """
    return await client.post(
        LOGIN_DO_URL,
        data=form,
        headers=LOGIN_HEADERS,
        cookies=extra_cookies or None,
    )


def classify_login_response(resp: httpx.Response) -> LoginClassifyResult:
    """
    对 login.do 响应做四分支分类

    Args:
        resp: login.do 的响应
    Returns:
        LoginClassifyResult
    """
    try:
        body = resp.json()
    except Exception:
        return LoginClassifyResult(branch=LoginBranch.UNKNOWN, raw=None)

    # ① 滑块：ret 含 FAIL_SYS_USER_VALIDATE + data.url
    ret = body.get("ret")
    if isinstance(ret, list) and any("FAIL_SYS_USER_VALIDATE" in str(r) for r in ret):
        slider_url = ((body.get("data") or {}).get("url")) or ""
        if slider_url:
            return LoginClassifyResult(
                branch=LoginBranch.SLIDER, slider_url=slider_url, raw=body
            )

    data = ((body.get("content") or {}).get("data")) or {}

    # ③ 触发人脸：iframeRedirect + iframeRedirectUrl（含 mini_login_check）
    if data.get("iframeRedirect") and data.get("iframeRedirectUrl"):
        return LoginClassifyResult(
            branch=LoginBranch.FACE, iframe_url=data.get("iframeRedirectUrl"), raw=body
        )

    # ② 直接成功：loginResult == success（或 st == success）
    if data.get("loginResult") == "success" or data.get("st") == "success":
        return LoginClassifyResult(branch=LoginBranch.SUCCESS, raw=body)

    # ④ 登录失败：titleMsg（无成功标志、无跳转）
    if data.get("titleMsg"):
        return LoginClassifyResult(
            branch=LoginBranch.FAIL, fail_message=str(data.get("titleMsg")), raw=body
        )

    return LoginClassifyResult(branch=LoginBranch.UNKNOWN, raw=body)
