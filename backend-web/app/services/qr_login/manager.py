"""
闲鱼扫码登录管理器

基于API接口实现二维码生成和Cookie获取
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
import uuid
from io import BytesIO
from random import random
from typing import Any, Dict, Optional

import httpx
import qrcode
import qrcode.constants
from loguru import logger

from app.services.qr_login.face_verification import run_face_verification


def generate_headers() -> Dict[str, str]:
    """生成请求头"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Referer": "https://passport.goofish.com/",
        "Origin": "https://passport.goofish.com",
    }


class GetLoginParamsError(Exception):
    """获取登录参数错误"""


class GetLoginQRCodeError(Exception):
    """获取登录二维码失败"""


class NotLoginError(Exception):
    """未登录错误"""


class QRLoginSession:
    """二维码登录会话"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.status = "waiting"  # waiting, scanned, success, expired, cancelled, verification_required
        self.qr_code_url: Optional[str] = None
        self.qr_content: Optional[str] = None
        self.cookies: Dict[str, str] = {}
        self.unb: Optional[str] = None
        self.created_time = time.time()
        self.expire_time = 300  # 5分钟过期
        self.params: Dict[str, Any] = {}
        self.verification_url: Optional[str] = None
        # 人脸验证：二维码渲染后的 base64 PNG data-url 及原始验证 URL
        self.face_qr_url: Optional[str] = None
        self.face_qr_content: Optional[str] = None

    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.created_time > self.expire_time

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "qr_code_url": self.qr_code_url,
            "created_time": self.created_time,
            "is_expired": self.is_expired(),
        }


class QRLoginManager:
    """二维码登录管理器"""

    def __init__(self):
        self.sessions: Dict[str, QRLoginSession] = {}
        # 人脸验证后台任务的强引用集合，防止 asyncio 只持弱引用导致任务被 GC
        self._face_tasks: set = set()
        self.headers = generate_headers()
        self.host = "https://passport.goofish.com"
        self.api_mini_login = f"{self.host}/mini_login.htm"
        self.api_generate_qr = f"{self.host}/newlogin/qrcode/generate.do"
        self.api_scan_status = f"{self.host}/newlogin/qrcode/query.do"
        self.api_face_check = f"{self.host}/iv/photoVerify/check.do"
        self.api_h5_tk = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"
        self.proxy: Optional[str] = None
        self.timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=60.0)

    def _cookie_marshal(self, cookies: Dict[str, str]) -> str:
        """将Cookie字典转换为字符串"""
        return "; ".join([f"{k}={v}" for k, v in cookies.items()])

    async def _get_mh5tk(self, session: QRLoginSession) -> Dict[str, str]:
        """获取m_h5_tk和m_h5_tk_enc"""
        data = {"bizScene": "home"}
        data_str = json.dumps(data, separators=(",", ":"))
        t = str(int(time.time() * 1000))
        app_key = "34839810"

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, proxy=self.proxy
        ) as client:
            try:
                resp = await client.get(self.api_h5_tk, headers=self.headers)
                cookies = {k: v for k, v in resp.cookies.items()}
                session.cookies.update(cookies)

                m_h5_tk = cookies.get("m_h5_tk", "")
                token = m_h5_tk.split("_")[0] if "_" in m_h5_tk else ""

                sign_input = f"{token}&{t}&{app_key}&{data_str}"
                sign = hashlib.md5(sign_input.encode()).hexdigest()

                params = {
                    "jsv": "2.7.2",
                    "appKey": app_key,
                    "t": t,
                    "sign": sign,
                    "v": "1.0",
                    "type": "originaljson",
                    "dataType": "json",
                    "timeout": 20000,
                    "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
                    "data": data_str,
                }

                await client.post(
                    self.api_h5_tk,
                    params=params,
                    headers=self.headers,
                    cookies=session.cookies,
                )
                return cookies
            except httpx.ConnectTimeout:
                logger.error("获取m_h5_tk时连接超时")
                raise
            except httpx.ReadTimeout:
                logger.error("获取m_h5_tk时读取超时")
                raise
            except httpx.ConnectError:
                logger.error("获取m_h5_tk时连接错误")
                raise

    async def _get_login_params(self, session: QRLoginSession) -> Dict[str, Any]:
        """获取二维码登录时需要的表单参数"""
        params = {
            "lang": "zh_cn",
            "appName": "xianyu",
            "appEntrance": "web",
            "styleType": "vertical",
            "bizParams": "",
            "notLoadSsoView": False,
            "notKeepLogin": False,
            "isMobile": False,
            "qrCodeFirst": False,
            "stie": 77,
            "rnd": random(),
        }

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.timeout, proxy=self.proxy
        ) as client:
            try:
                resp = await client.get(
                    self.api_mini_login,
                    params=params,
                    cookies=session.cookies,
                    headers=self.headers,
                )

                pattern = r"window\.viewData\s*=\s*(\{.*?\});"
                match = re.search(pattern, resp.text)
                if match:
                    json_string = match.group(1)
                    view_data = json.loads(json_string)
                    data = view_data.get("loginFormData")
                    if data:
                        data["umidTag"] = "SERVER"
                        session.params.update(data)
                        return data
                    else:
                        raise GetLoginParamsError("未找到loginFormData")
                else:
                    raise GetLoginParamsError("获取登录参数失败")
            except httpx.ConnectTimeout:
                logger.error("获取登录参数时连接超时")
                raise
            except httpx.ReadTimeout:
                logger.error("获取登录参数时读取超时")
                raise
            except httpx.ConnectError:
                logger.error("获取登录参数时连接错误")
                raise

    async def generate_qr_code(self) -> Dict[str, Any]:
        """生成二维码"""
        try:
            session_id = str(uuid.uuid4())
            session = QRLoginSession(session_id)

            await self._get_mh5tk(session)
            logger.info(f"获取m_h5_tk成功: {session_id}")

            await self._get_login_params(session)
            logger.info(f"获取登录参数成功: {session_id}")

            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self.timeout, proxy=self.proxy
            ) as client:
                resp = await client.get(
                    self.api_generate_qr, params=session.params, headers=self.headers
                )

                try:
                    results = resp.json()
                except Exception:
                    logger.exception("二维码接口返回不是JSON")
                    raise GetLoginQRCodeError(f"二维码接口返回异常: {resp.text}")

                if results.get("content", {}).get("success") is True:
                    session.params.update(
                        {
                            "t": results["content"]["data"]["t"],
                            "ck": results["content"]["data"]["ck"],
                        }
                    )

                    qr_content = results["content"]["data"]["codeContent"]
                    session.qr_content = qr_content

                    qr = qrcode.QRCode(
                        version=5,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=2,
                    )
                    qr.add_data(qr_content)
                    qr.make()

                    qr_img = qr.make_image()
                    buffer = BytesIO()
                    qr_img.save(buffer, format="PNG")
                    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
                    qr_data_url = f"data:image/png;base64,{qr_base64}"

                    session.qr_code_url = qr_data_url
                    session.status = "waiting"

                    self.sessions[session_id] = session
                    asyncio.create_task(self._monitor_qr_status(session_id))

                    logger.info(f"二维码生成成功: {session_id}")
                    return {
                        "success": True,
                        "session_id": session_id,
                        "qr_code_url": qr_data_url,
                    }
                else:
                    raise GetLoginQRCodeError("获取登录二维码失败")

        except httpx.ConnectTimeout as e:
            logger.error(f"连接超时: {e}")
            return {"success": False, "message": "连接超时，请检查网络或尝试使用代理"}
        except httpx.ReadTimeout as e:
            logger.error(f"读取超时: {e}")
            return {"success": False, "message": "读取超时，服务器响应过慢"}
        except httpx.ConnectError as e:
            logger.error(f"连接错误: {e}")
            return {"success": False, "message": "连接错误，请检查网络或代理设置"}
        except Exception as e:
            logger.exception("二维码生成过程中发生异常")
            return {"success": False, "message": f"生成二维码失败: {str(e)}"}

    async def _poll_qrcode_status(self, session: QRLoginSession) -> httpx.Response:
        """获取二维码扫描状态"""
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.timeout, proxy=self.proxy
        ) as client:
            resp = await client.post(
                self.api_scan_status,
                data=session.params,
                cookies=session.cookies,
                headers=self.headers,
            )
            return resp

    async def _monitor_qr_status(self, session_id: str):
        """监控二维码状态"""
        try:
            session = self.sessions.get(session_id)
            if not session:
                return

            logger.info(f"开始监控二维码状态: {session_id}")
            max_wait_time = 300
            start_time = time.time()

            while time.time() - start_time < max_wait_time:
                try:
                    if session_id not in self.sessions:
                        break

                    resp = await self._poll_qrcode_status(session)
                    qrcode_status = (
                        resp.json()
                        .get("content", {})
                        .get("data", {})
                        .get("qrCodeStatus")
                    )

                    if qrcode_status == "CONFIRMED":
                        if (
                            resp.json()
                            .get("content", {})
                            .get("data", {})
                            .get("iframeRedirect")
                            is True
                        ):
                            session.status = "verification_required"
                            iframe_url = (
                                resp.json()
                                .get("content", {})
                                .get("data", {})
                                .get("iframeRedirectUrl")
                            )
                            session.verification_url = iframe_url
                            # 保留本次 query.do 响应的 Cookie(身份锚点)，供人脸验证链路复用
                            for k, v in resp.cookies.items():
                                session.cookies[k] = v
                            # 人脸验证需要额外时间(手机端操作)，在启动异步任务【前】同步重置
                            # 会话有效期窗口，避免 get_session_status 在调度间隙将其误判为过期
                            session.created_time = time.time()
                            session.expire_time = 300
                            logger.warning(
                                f"账号触发人脸验证，开始自动抓取人脸二维码: {session_id}, URL: {iframe_url}"
                            )
                            # 不再终止：交给人脸验证处理协程完成后续链路
                            # 保存任务强引用，防止被 asyncio 垃圾回收(完成后自动移除)
                            task = asyncio.create_task(
                                run_face_verification(self, session_id, iframe_url)
                            )
                            self._face_tasks.add(task)
                            task.add_done_callback(self._face_tasks.discard)
                            break
                        else:
                            session.status = "success"
                            for k, v in resp.cookies.items():
                                session.cookies[k] = v
                                if k == "unb":
                                    session.unb = v
                            logger.info(f"扫码登录成功: {session_id}, UNB: {session.unb}")
                            break

                    elif qrcode_status == "NEW":
                        pass
                    elif qrcode_status == "EXPIRED":
                        session.status = "expired"
                        logger.info(f"二维码已过期: {session_id}")
                        break
                    elif qrcode_status == "SCANED":
                        if session.status == "waiting":
                            session.status = "scanned"
                            logger.info(f"二维码已扫描，等待确认: {session_id}")
                    else:
                        session.status = "cancelled"
                        logger.info(f"用户取消登录: {session_id}")
                        break

                    await asyncio.sleep(0.8)

                except Exception as e:
                    logger.error(f"监控二维码状态异常: {e}")
                    await asyncio.sleep(2)

            if session.status not in [
                "success",
                "expired",
                "cancelled",
                "verification_required",
            ]:
                session.status = "expired"
                logger.info(f"二维码监控超时，标记为过期: {session_id}")

        except Exception as e:
            logger.error(f"监控二维码状态失败: {e}")
            if session_id in self.sessions:
                self.sessions[session_id].status = "expired"

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        session = self.sessions.get(session_id)
        if not session:
            return {"status": "not_found"}

        if session.is_expired() and session.status != "success":
            session.status = "expired"

        result: Dict[str, Any] = {"status": session.status, "session_id": session_id}

        if session.status == "verification_required":
            result["verification_url"] = session.verification_url
            result["face_qr_url"] = session.face_qr_url
            result["message"] = "需要人脸验证，请使用手机闲鱼扫描二维码"

        if session.status == "success" and session.cookies and session.unb:
            result["cookies"] = self._cookie_marshal(session.cookies)
            result["unb"] = session.unb

        return result

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        expired_sessions = [
            sid for sid, sess in self.sessions.items() if sess.is_expired()
        ]
        for session_id in expired_sessions:
            del self.sessions[session_id]
            logger.info(f"清理过期会话: {session_id}")

    def get_session_cookies(self, session_id: str) -> Optional[Dict[str, str]]:
        """获取会话Cookie"""
        session = self.sessions.get(session_id)
        if session and session.status == "success":
            return {"cookies": self._cookie_marshal(session.cookies), "unb": session.unb}
        return None


# 全局二维码登录管理器实例
qr_login_manager = QRLoginManager()
