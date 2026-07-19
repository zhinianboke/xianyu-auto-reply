"""
协议化账号密码登录 - 编排流程

功能：
1. 纯 API 调 login.do，对响应做四分支编排（滑块 / 直接成功 / 触发人脸 / 失败）
2. 滑块委托：配了远程→远程直连；否则→委托 WebSocket 使用其配置的滑块引擎
3. 人脸：复用 common 人脸链路，渲染二维码供前台展示，扫码后自动收 Cookie
4. 成功后按 account_id 入库、起 WebSocket；滑块未通过时保持协议链路重试

会话状态：processing / verification_required / success / failed
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.account_service import AccountService
from app.services.websocket_client import websocket_client
from common.db.session import async_session_maker
from common.services.captcha.remote_solver import solve_remote
from common.services.xianyu_login.face_verification import (
    FaceVerificationError,
    run_face_verification_flow,
)
from common.services.xianyu_login.login_do import (
    LoginBranch,
    build_login_form,
    classify_login_response,
    post_login_do,
)
from common.utils.xianyu_utils import trans_cookies

# 最多解几次滑块（每次解完重发 login.do）
_MAX_SLIDER_ROUNDS = 3
# 单账号协议登录总预算（秒）：需覆盖多轮过滑块(每轮可达 ~90s) + 人脸时用户扫码/识别耗时
_LOGIN_BUDGET = 600
_LOGIN_GUARD_COOKIE_NAMES = ("x5secdata", "x5sectag")
_LOGIN_SLIDER_COOKIE_NAMES = ("x5sec", "x5secdata", "x5sectag")


async def _read_remote_config() -> Dict[str, Any]:
    """读取远程过滑块配置（url/secret）。

    注：协议登录是全新登录、此时账号尚无 Cookie，故不涉及"传递账号Cookie"开关。
    """
    from sqlalchemy import select

    from common.models.system_setting import SystemSetting

    keys = [
        "captcha.remote_service_url",
        "captcha.remote_secret_key",
    ]
    async with async_session_maker() as session:
        rows = (
            await session.execute(select(SystemSetting).where(SystemSetting.key.in_(keys)))
        ).scalars().all()
    m = {r.key: (r.value or "") for r in rows}
    return {
        "url": m.get("captcha.remote_service_url", "").strip(),
        "secret": m.get("captcha.remote_secret_key", "").strip(),
    }


async def _solve_slider(
    account_id: str, slider_url: str, remote_config: Dict[str, Any]
) -> Tuple[str, Optional[Dict[str, str]], Optional[str]]:
    """过滑块（登录场景）：配了远程则远程处理，否则委托 WebSocket 滑块引擎。

    WebSocket 服务自行根据系统设置决定使用真实鼠标或其它滑块引擎，
    backend-web 不参与引擎选择。

    协议模式一旦选定过滑块通道（远程 / 本机），满足协议后【不允许跨通道回退】：
    远程超时/不可用（solve_remote 返回 'fallback'，其本意是"回退本机"）在协议语境下
    统一归并为 'fail'，由上层继续重试同一远程通道，不切换到本机真实鼠标。

    Returns:
        (status, cookies, message)  status: 'ok'/'fail'/'url_expired'
    """
    # 配了远程时优先远程
    if remote_config.get("url") and remote_config.get("secret"):
        status, cookies, message = await solve_remote(
            remote_url=remote_config["url"],
            remote_secret=remote_config["secret"],
            user_id=account_id,
            url=slider_url,
        )
        # 协议模式不回退本机：'fallback'（远程超时/不可用）按普通失败处理，交上层重试远程
        if status == "fallback":
            logger.warning(
                f"【{account_id}】远程过滑块超时/不可用，协议模式不回退本机，按失败重试"
            )
            return "fail", None, message
        return status, cookies, message
    # 否则委托 WebSocket 滑块引擎（并发、排队和引擎选择统一在 WebSocket）
    resp = await websocket_client.solve_captcha(
        account_id=account_id, url=slider_url, call_type="local"
    )
    if isinstance(resp, dict) and resp.get("success"):
        cookies = (resp.get("data") or {}).get("cookies") or {}
        if cookies:
            return "ok", cookies, None
    if isinstance(resp, dict) and (resp.get("data") or {}).get("url_expired"):
        return "url_expired", None, resp.get("message")
    return "fail", None, resp.get("message") if isinstance(resp, dict) else "过滑块失败"


async def _collect_login_cookies(client: httpx.AsyncClient) -> Tuple[str, str]:
    """直接成功后收集完整登录 Cookie：先访问首页补齐 cookie2 等，再拼串并提取 unb。"""
    try:
        await client.get("https://www.goofish.com/", follow_redirects=True)
    except Exception as e:
        logger.warning(f"补齐首页 Cookie 失败（继续）: {e}")
    cookies_str = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
    # 空串时 trans_cookies 会抛错，这里安全提取（空 unb 交由调用方按失败处理）
    unb = trans_cookies(cookies_str).get("unb", "") if cookies_str else ""
    return cookies_str, unb


async def _save_and_start(
    *, account_id: str, account: str, password: str, show_browser: bool,
    owner_id: int, cookies_str: str, unb: str,
) -> Tuple[bool, str]:
    """入库（按 account_id upsert）+ 清 token 缓存 + 起/重启 WebSocket。

    Returns:
        (is_new_account, message) 或抛 ValueError（账号被占用）
    """
    async with async_session_maker() as session:
        svc = AccountService(session)
        account_obj, is_new = await svc.upsert_account_from_password(
            owner_id=owner_id,
            account_id=account_id,
            account=account,
            password=password,
            cookies=cookies_str,
            unb=unb or None,
            show_browser=show_browser,
        )
        # 清该账号 token 缓存（可重建派生缓存，新 Cookie 需重新取 token）
        if unb:
            from sqlalchemy import text

            await session.execute(
                text("DELETE FROM xy_token_cache WHERE user_id = :uid"), {"uid": unb}
            )
            await session.commit()

    # 起/重启 WebSocket（与扫码登录同一套 /internal/accounts 接口）
    try:
        settings = get_settings()
        client = get_http_client()
        endpoint = "start" if is_new else "restart"
        await client.post(
            f"{settings.websocket_service_url}/internal/accounts/{account_id}/{endpoint}",
            json={"cookie_value": cookies_str, "user_id": owner_id},
        )
    except Exception as ws_e:
        logger.error(f"【{account_id}】协议登录成功但起 WebSocket 失败: {ws_e}")
    return is_new, ("新账号登录成功" if is_new else "账号登录成功")


def _inject_cookies(client: httpx.AsyncClient, cookies: Dict[str, str]) -> None:
    """把过滑块返回的 x5sec 等 Cookie 注入客户端 jar，供重发 login.do 携带。"""
    for name, value in (cookies or {}).items():
        try:
            client.cookies.set(name, value, domain=".goofish.com")
        except Exception:
            client.cookies.set(name, value)


def _snapshot_cookies(client: httpx.AsyncClient, names: Tuple[str, ...]) -> Dict[str, str]:
    """按名称快照 Cookie 值，供耗时滑块完成后显式带回短期风控 Cookie。"""
    wanted = set(names)
    snapshot: Dict[str, str] = {}
    for cookie in client.cookies.jar:
        if cookie.name in wanted and cookie.value:
            snapshot[cookie.name] = cookie.value
    return snapshot


def _cookie_presence(client: httpx.AsyncClient) -> str:
    """返回风控相关 Cookie 名称存在性（只记录名称，不记录值）。"""
    present = sorted(
        cookie.name for cookie in client.cookies.jar
        if cookie.name in _LOGIN_SLIDER_COOKIE_NAMES and cookie.value
    )
    return ",".join(present) if present else "-"


def _fail_protocol_login(
    session: Dict[str, Any], reason: str,
    *, account_id: str,
) -> None:
    """协议登录最终失败：不回退网页登录，避免协议链路被切到另一套登录逻辑。"""
    session["status"] = "failed"
    session["error"] = f"协议登录未通过（{reason}）"
    logger.warning(f"【{account_id}】协议登录失败：{reason}")


async def run_protocol_login(
    *, session: Dict[str, Any], account_id: str, account: str, password: str,
    show_browser: bool, owner_id: int,
) -> None:
    """协议化密码登录主编排（在后台任务中运行，直接更新传入的 session 字典）。"""
    start = time.time()
    remote_config = await _read_remote_config()

    def should_continue() -> bool:
        return not session.get("cancelled") and (time.time() - start) < _LOGIN_BUDGET

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), follow_redirects=False
        ) as client:
            slider_rounds = 0
            pending_login_cookies: Optional[Dict[str, str]] = None
            while True:
                if not should_continue():
                    session["status"] = "failed"
                    session["error"] = "登录超时，请重试"
                    return

                resp = await post_login_do(
                    client,
                    build_login_form(account, password),
                    extra_cookies=pending_login_cookies,
                )
                pending_login_cookies = None
                result = classify_login_response(resp)
                logger.info(
                    f"【{account_id}】login.do 分支={result.branch.value}, "
                    f"slider_rounds={slider_rounds}, cookies={_cookie_presence(client)}"
                )

                if result.branch == LoginBranch.SLIDER:
                    slider_rounds += 1
                    guard_cookies = _snapshot_cookies(client, _LOGIN_GUARD_COOKIE_NAMES)
                    if slider_rounds > _MAX_SLIDER_ROUNDS:
                        _fail_protocol_login(
                            session, "滑块多次未通过", account_id=account_id
                        )
                        return
                    session["message"] = (
                        f"正在处理登录滑块（第 {slider_rounds}/{_MAX_SLIDER_ROUNDS} 次）"
                    )
                    status, cookies, slider_message = await _solve_slider(
                        account_id, result.slider_url, remote_config
                    )
                    if status == "ok":
                        slider_cookies = cookies or {}
                        _inject_cookies(client, slider_cookies)
                        pending_login_cookies = {**guard_cookies, **slider_cookies}
                        logger.info(
                            f"【{account_id}】登录滑块通过，重发 login.do 将显式携带 "
                            f"{','.join(sorted(pending_login_cookies.keys())) or '-'}"
                        )
                        continue  # 带 x5sec 重发 login.do
                    if status == "url_expired":
                        logger.info(f"【{account_id}】登录滑块链接已过期，重新获取 punish 链接")
                        continue  # 重发 login.do 取新的 punish 链接
                    if slider_rounds < _MAX_SLIDER_ROUNDS:
                        session["message"] = (
                            f"滑块未通过，正在重新打开浏览器重试"
                            f"（第 {slider_rounds + 1}/{_MAX_SLIDER_ROUNDS} 次）"
                        )
                        logger.warning(
                            f"【{account_id}】登录滑块未通过，继续协议链路重试 "
                            f"({slider_rounds}/{_MAX_SLIDER_ROUNDS})"
                        )
                        continue
                    _fail_protocol_login(
                        session,
                        slider_message or f"过滑块{status}",
                        account_id=account_id,
                    )
                    return

                if result.branch == LoginBranch.SUCCESS:
                    cookies_str, unb = await _collect_login_cookies(client)
                    if not unb:
                        session["status"] = "failed"
                        session["error"] = "登录成功但未获取到账号标识(unb)"
                        return
                    await _finish_success(
                        session, account_id=account_id, account=account,
                        password=password, show_browser=show_browser,
                        owner_id=owner_id, cookies_str=cookies_str, unb=unb,
                    )
                    return

                if result.branch == LoginBranch.FACE:
                    session["status"] = "verification_required"

                    def on_qr(qr_b64: str) -> None:
                        session["face_qr_url"] = qr_b64
                        session["status"] = "verification_required"

                    # 人脸链路返回收好的 Cookie 与 unb（内部已保证 unb 非空，否则抛错）
                    face_cookies, unb = await run_face_verification_flow(
                        client, result.iframe_url, on_qr, should_continue
                    )
                    cookies_str = "; ".join(f"{k}={v}" for k, v in face_cookies.items())
                    if not unb:
                        session["status"] = "failed"
                        session["error"] = "人脸验证完成但未获取到账号标识(unb)"
                        return
                    await _finish_success(
                        session, account_id=account_id, account=account,
                        password=password, show_browser=show_browser,
                        owner_id=owner_id, cookies_str=cookies_str, unb=unb,
                    )
                    return

                if result.branch == LoginBranch.FAIL:
                    session["status"] = "failed"
                    session["error"] = result.fail_message or "账号或密码错误"
                    return

                # UNKNOWN：结构漂移/异常 ret
                session["status"] = "failed"
                session["error"] = "登录响应异常，请稍后重试或改用扫码登录"
                logger.warning(f"【{account_id}】login.do 未知分支: {str(result.raw)[:300]}")
                return
    except FaceVerificationError as fe:
        session["status"] = "failed"
        session["error"] = f"人脸验证失败：{fe}"
    except Exception as e:
        logger.exception(f"【{account_id}】协议登录异常")
        session["status"] = "failed"
        session["error"] = f"登录失败：{e}"


async def _finish_success(
    session: Dict[str, Any], *, account_id: str, account: str, password: str,
    show_browser: bool, owner_id: int, cookies_str: str, unb: str,
) -> None:
    """成功收尾：入库 + 起 WS + 置成功态。"""
    try:
        is_new, msg = await _save_and_start(
            account_id=account_id, account=account, password=password,
            show_browser=show_browser, owner_id=owner_id,
            cookies_str=cookies_str, unb=unb,
        )
    except ValueError as ve:
        session["status"] = "failed"
        session["error"] = str(ve)
        return
    session["status"] = "success"
    session["account_id"] = account_id
    session["is_new_account"] = is_new
    session["message"] = msg
