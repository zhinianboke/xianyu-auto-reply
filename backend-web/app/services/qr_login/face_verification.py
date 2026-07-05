"""
闲鱼扫码登录 - 人脸验证处理

功能：
1. 参照抓包还原的浏览器端流程，纯 API 复现人脸验证链路
2. 从各中转页服务端渲染的 HTML 中提取 htoken、下一跳链接、人脸验证二维码
3. 轮询人脸验证结果，成功后收集登录 Cookie 与 unb

本模块从 manager.py 拆分而来，保持单文件 500 行以内（见 CLAUDE.md 5.2）。
"""
from __future__ import annotations

import asyncio
import base64
import re
import time
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import httpx
import qrcode
import qrcode.constants
from loguru import logger

if TYPE_CHECKING:
    from app.services.qr_login.manager import QRLoginManager


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


async def run_face_verification(
    manager: "QRLoginManager", session_id: str, iframe_url: str
) -> None:
    """
    自动处理人脸验证链路

    参照抓包还原的浏览器端流程，纯 API 复现：
    1. 跟随 iframe_url(302) 落到 normal_validate.htm，提取 htoken
    2. 从 normal_validate.htm 提取下一跳 verify_modes.htm 链接(含服务端渲染的 umidToken)
    3. 请求 verify_modes.htm(302) 落到 identity_verify.htm
    4. 从 identity_verify.htm 提取人脸验证二维码 URL，渲染成图片供前端展示
    5. 轮询 photoVerify/check.do 直到用户手机完成人脸(code=3)
    6. 跟随返回的 ivCheckLogin.htm，收集登录 Cookie 与 unb，置为登录成功

    调用方(_monitor_qr_status)已在启动本协程前同步保留了 query.do 的 Cookie
    并重置了会话有效期窗口，故本函数不再重复处理。

    Args:
        manager: 二维码登录管理器实例(提供 headers/host/timeout/proxy 等)
        session_id: 二维码会话 ID
        iframe_url: query.do 返回的 iframeRedirectUrl(风控跳转地址)
    """
    session = manager.sessions.get(session_id)
    if not session:
        return

    try:
        # 用带 cookie jar 的单一 client 贯穿整条 302 链路(cookie2 是身份锚点)
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=manager.timeout,
            proxy=manager.proxy,
            cookies=session.cookies,
            headers=manager.headers,
        ) as client:
            # 步骤1：跟随风控跳转，落到 normal_validate.htm
            resp = await client.get(iframe_url)
            normal_html = resp.text

            # 步骤2：提取 htoken 与下一跳 verify_modes.htm 链接
            htoken_match = re.search(r"htoken=([A-Za-z0-9_\-]+)", normal_html)
            if not htoken_match:
                raise ValueError("人脸验证：未能提取 htoken")
            htoken = htoken_match.group(1)

            verify_modes_match = re.search(
                r"window\.location\.href\s*=\s*\"(https://[^\"]*?/iv/mini/verify_modes\.htm\?[^\"]*)\"",
                normal_html,
            )
            if not verify_modes_match:
                raise ValueError("人脸验证：未能提取 verify_modes 链接")
            # 页面里该链接以 _umidfg= 结尾，后接 JS 变量 window._iv_umidfg(值为1)
            verify_modes_url = verify_modes_match.group(1)
            if verify_modes_url.endswith("_umidfg="):
                verify_modes_url += "1"

            # 步骤3：请求 verify_modes.htm，跟随 302 落到 identity_verify.htm
            resp = await client.get(verify_modes_url)
            identity_html = resp.text

            # 步骤4：提取人脸验证二维码内容并渲染
            face_qr_match = re.search(
                r"new\s+Qrcode\(\{\s*text:\s*\"([^\"]+)\"",
                identity_html,
            )
            if not face_qr_match:
                raise ValueError("人脸验证：未能提取人脸验证二维码 URL")
            face_qr_content = face_qr_match.group(1)
            session.face_qr_content = face_qr_content
            session.face_qr_url = render_qr_base64(face_qr_content)
            logger.info(f"人脸验证二维码已生成，等待用户扫码: {session_id}")

            # 步骤5：轮询 check.do 等待用户手机完成人脸验证
            check_headers = dict(manager.headers)
            check_headers.update(
                {
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{manager.host}/iv/mini/identity_verify.htm?htoken={htoken}",
                }
            )
            iv_check_url: Optional[str] = None
            while not session.is_expired():
                if session_id not in manager.sessions:
                    return
                try:
                    check_resp = await client.get(
                        manager.api_face_check,
                        params={"htoken": htoken},
                        headers=check_headers,
                    )
                    content = check_resp.json().get("content", {})
                    code = str(content.get("code", ""))
                    if code == "3":
                        iv_check_url = content.get("url")
                        logger.info(f"人脸验证通过: {session_id}")
                        break
                    elif code == "0":
                        # 等待用户在手机上完成
                        pass
                    else:
                        logger.warning(
                            f"人脸验证 check.do 返回异常 code={code}: {session_id}, resp={check_resp.text[:200]}"
                        )
                except Exception as check_e:
                    logger.warning(f"人脸验证轮询异常: {session_id}, {check_e}")
                await asyncio.sleep(2)

            if not iv_check_url:
                session.status = "expired"
                logger.warning(f"人脸验证超时或未完成: {session_id}")
                return

            # 步骤6：跟随 ivCheckLogin.htm 完成登录，收集 Cookie 与 unb
            await client.get(iv_check_url, headers=check_headers)
            for cookie_name, cookie_value in client.cookies.items():
                session.cookies[cookie_name] = cookie_value
                if cookie_name == "unb":
                    session.unb = cookie_value

            if session.unb:
                session.status = "success"
                logger.info(f"人脸验证登录成功: {session_id}, UNB: {session.unb}")
            else:
                session.status = "expired"
                logger.warning(f"人脸验证完成但未获取到 unb，登录失败: {session_id}")

    except Exception:
        logger.exception(f"人脸验证处理失败: {session_id}")
        if session_id in manager.sessions:
            manager.sessions[session_id].status = "expired"
