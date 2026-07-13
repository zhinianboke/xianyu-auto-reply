"""
闲鱼登录人脸验证（纯 API 链路）

功能：
1. 从各中转页服务端渲染的 HTML 中提取 htoken、下一跳链接、人脸验证二维码
2. 渲染人脸二维码供前台展示
3. 轮询 photoVerify/check.do 直到用户手机完成人脸（code=3）
4. 跟随 ivCheckLogin.htm 收集登录 Cookie 与 unb

本模块从 backend-web/app/services/qr_login/face_verification.py 抽取为通用实现，
与具体会话/管理器解耦（通过回调与参数注入），供协议密码登录复用；
扫码登录后续可改为调用本模块以去重（见改造方案 P6）。
"""
from __future__ import annotations

import asyncio
import base64
import re
from io import BytesIO
from typing import Callable, Dict, Optional, Tuple

import httpx
import qrcode
import qrcode.constants
from loguru import logger

# 人脸验证相关接口
PASSPORT_HOST = "https://passport.goofish.com"
API_FACE_CHECK = f"{PASSPORT_HOST}/iv/photoVerify/check.do"

# 默认请求头（不含动态风控字段）
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{PASSPORT_HOST}/",
    "Origin": PASSPORT_HOST,
}


class FaceVerificationError(Exception):
    """人脸验证链路异常"""


def render_qr_base64(content: str) -> str:
    """将文本内容渲染为二维码 PNG 的 base64 data-url"""
    qr = qrcode.QRCode(
        version=5,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(content)
    qr.make()
    qr_img = qr.make_image()
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{qr_base64}"


async def run_face_verification_flow(
    client: httpx.AsyncClient,
    iframe_url: str,
    on_qr_ready: Callable[[str], None],
    should_continue: Callable[[], bool],
    headers: Optional[Dict[str, str]] = None,
    poll_interval: float = 2.0,
) -> Tuple[Dict[str, str], str]:
    """
    执行纯 API 人脸验证链路

    Args:
        client: 贯穿登录全流程的 httpx.AsyncClient（携带 login.do 的 cookie jar）
        iframe_url: login.do 返回的 iframeRedirectUrl（风控跳转地址）
        on_qr_ready: 二维码就绪回调，入参为二维码 base64 data-url（供前台展示）
        should_continue: 是否继续轮询的回调（返回 False 则中止，如会话超时/取消）
        headers: 请求头（默认使用 DEFAULT_HEADERS）
        poll_interval: 轮询间隔（秒）
    Returns:
        (cookies, unb)：登录成功后的 Cookie 字典与 unb
    Raises:
        FaceVerificationError: 提取失败 / 超时 / 未拿到 unb
    """
    base_headers = dict(headers or DEFAULT_HEADERS)

    # 步骤1：跟随风控跳转，落到 normal_validate.htm
    resp = await client.get(iframe_url, headers=base_headers, follow_redirects=True)
    normal_html = resp.text

    # 步骤2：提取 htoken 与下一跳 verify_modes.htm 链接
    htoken_match = re.search(r"htoken=([A-Za-z0-9_\-]+)", normal_html)
    if not htoken_match:
        raise FaceVerificationError("人脸验证：未能提取 htoken")
    htoken = htoken_match.group(1)

    verify_modes_match = re.search(
        r"window\.location\.href\s*=\s*\"(https://[^\"]*?/iv/mini/verify_modes\.htm\?[^\"]*)\"",
        normal_html,
    )
    if not verify_modes_match:
        raise FaceVerificationError("人脸验证：未能提取 verify_modes 链接")
    verify_modes_url = verify_modes_match.group(1)
    # 页面里该链接以 _umidfg= 结尾，后接 JS 变量 window._iv_umidfg(值为1)
    if verify_modes_url.endswith("_umidfg="):
        verify_modes_url += "1"

    # 步骤3：请求 verify_modes.htm，跟随 302 落到 identity_verify.htm
    resp = await client.get(verify_modes_url, headers=base_headers, follow_redirects=True)
    identity_html = resp.text

    # 步骤4：提取人脸验证二维码内容并渲染
    face_qr_match = re.search(r"new\s+Qrcode\(\{\s*text:\s*\"([^\"]+)\"", identity_html)
    if not face_qr_match:
        raise FaceVerificationError("人脸验证：未能提取人脸验证二维码 URL")
    face_qr_content = face_qr_match.group(1)
    on_qr_ready(render_qr_base64(face_qr_content))
    logger.info("人脸验证二维码已生成，等待用户扫码")

    # 步骤5：轮询 check.do 等待用户手机完成人脸验证
    check_headers = dict(base_headers)
    check_headers.update(
        {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{PASSPORT_HOST}/iv/mini/identity_verify.htm?htoken={htoken}",
        }
    )
    iv_check_url: Optional[str] = None
    while should_continue():
        try:
            check_resp = await client.get(
                API_FACE_CHECK, params={"htoken": htoken}, headers=check_headers
            )
            content = check_resp.json().get("content", {})
            code = str(content.get("code", ""))
            if code == "3":
                iv_check_url = content.get("url")
                logger.info("人脸验证通过")
                break
            elif code == "0":
                pass  # 等待用户在手机上完成
            else:
                logger.warning(
                    f"人脸验证 check.do 返回异常 code={code}, resp={check_resp.text[:200]}"
                )
        except Exception as check_e:
            logger.warning(f"人脸验证轮询异常: {check_e}")
        await asyncio.sleep(poll_interval)

    if not iv_check_url:
        raise FaceVerificationError("人脸验证超时或未完成")

    # 步骤6：跟随 ivCheckLogin.htm 完成登录，收集 Cookie 与 unb
    await client.get(iv_check_url, headers=check_headers, follow_redirects=True)
    cookies: Dict[str, str] = {}
    unb = ""
    for cookie_name, cookie_value in client.cookies.items():
        cookies[cookie_name] = cookie_value
        if cookie_name == "unb":
            unb = cookie_value

    if not unb:
        raise FaceVerificationError("人脸验证完成但未获取到 unb")
    logger.info(f"人脸验证登录成功, UNB: {unb}")
    return cookies, unb
