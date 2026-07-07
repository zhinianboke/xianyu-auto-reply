"""
滑块验证编排：主引擎 + DrissionPage 兜底

对外提供与 run_slider_verification 一致的返回契约 (是否成功, cookies 字典 | None)：
1. 先用 Playwright 主引擎（run_slider_verification）；
2. 主引擎成功且取得 x5sec cookie → 直接返回；
3. 否则（失败或无 x5sec）且兜底开关开启 → 调用 DrissionPage 兜底引擎重试一次。

调用方只需把目标函数从 run_slider_verification 换成本函数即可，无需关心引擎细节。
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from loguru import logger

from common.services.captcha.slider_stealth import run_slider_verification, CAPTCHA_NOT_REQUIRED, URL_EXPIRED
from common.services.captcha.drissionpage_slider import (
    run_drissionpage_verification,
    DRISSIONPAGE_AVAILABLE,
)


def _has_x5sec(cookies: Optional[Dict[str, str]]) -> bool:
    """判断 cookie 字典中是否包含 x5/x5sec 相关 cookie（与上层放行判定一致）。"""
    if not cookies:
        return False
    for name in cookies:
        name_lower = str(name).lower()
        if name_lower.startswith("x5") or "x5sec" in name_lower:
            return True
    return False


def _load_fallback_config() -> Tuple[bool, bool, int]:
    """读取兜底配置 (是否启用, 是否无头, 超时秒)。

    兼容从 websocket 的 app.core.config 或 common.core.config 读取。
    """
    enabled, headless, timeout = True, True, 25
    settings = None
    try:
        from app.core.config import get_settings
        settings = get_settings()
    except Exception:
        try:
            from common.core.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None
    if settings is not None:
        enabled = bool(getattr(settings, "captcha_drissionpage_fallback_enabled", True))
        headless = bool(getattr(settings, "captcha_drissionpage_headless", True))
        timeout = int(getattr(settings, "captcha_drissionpage_timeout", 25))
    return enabled, headless, timeout


def _real_mouse_enabled() -> bool:
    """读取「真实鼠标模式」开关（默认 False；Docker/无头默认关闭）。"""
    settings = None
    try:
        from app.core.config import get_settings
        settings = get_settings()
    except Exception:
        try:
            from common.core.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None
    if settings is None:
        return False
    return bool(getattr(settings, "captcha_real_mouse_enabled", False))


def _call_remote_solve(
    remote_url: str,
    remote_secret: str,
    user_id: str,
    url: str,
    browser_timeout: int,
    cookies_str: str = "",
    device_id: str = "",
) -> Tuple[str, Optional[Dict[str, str]]]:
    """调用远程过滑块接口。

    Args:
        cookies_str: 账号 Cookie（仅当"传递Cookie"开关开启时非空）。传入后远程端在
            遇到"抱歉，页面访问出现了问题"（链接过期）时，可凭此 Cookie 重取新链接继续处理。
        device_id: 设备 ID，配合 cookies_str 供远程端重新请求 token 接口使用。

    Returns:
        (status, cookies)
        status: 'ok'（远程通过，cookies 为 x5*）/ 'fail'（远程有返回但未通过）/
                'url_expired'（远程反馈验证链接已过期，调用方应刷新URL后重试）/
                'fallback'（超时或网络不可用，应回退本机逻辑）
    """
    import requests

    payload = {
        "secret_key": remote_secret,
        "account_id": str(user_id),
        "url": url,
        "browser_timeout": int(browser_timeout),
    }
    # 仅在开启"传递Cookie"开关时携带账号 Cookie / 设备 ID（默认不传，保护账号隐私）
    if cookies_str:
        payload["cookies"] = cookies_str
        payload["device_id"] = device_id or ""

    try:
        resp = requests.post(
            remote_url,
            json=payload,
            # 连接 8s 内必须建立，读取给足远程求解时间；超时/连不上 → 回退本机
            timeout=(8, max(90, int(browser_timeout) + 60)),
        )
    except requests.exceptions.RequestException as e:
        logger.warning(f"【{user_id}】远程过滑块超时/不可用，回退本机逻辑: {e}")
        return "fallback", None

    try:
        data = resp.json()
    except Exception as e:
        # 远程有响应但响应体异常：视为远程未通过（非超时 → 不回退）
        logger.warning(f"【{user_id}】远程过滑块响应解析失败，判失败（不回退）: {e}")
        return "fail", None

    if isinstance(data, dict) and data.get("success"):
        cookies = (data.get("data") or {}).get("cookies") or {}
        if cookies:
            return "ok", cookies
    # 远程明确反馈"验证链接已过期"：调用方需刷新URL后重试（老版本远程端无此字段，自然走 fail）
    if isinstance(data, dict) and (data.get("data") or {}).get("url_expired"):
        logger.info(f"【{user_id}】远程反馈验证链接已过期(url_expired)")
        return "url_expired", None
    return "fail", None


def run_slider_verification_with_fallback(
    user_id: str,
    url: str,
    enable_learning: bool = True,
    headless: bool = False,
    browser_timeout: int = 20,
    existing_cookies_str: str = "",
    url_provider: Optional[Callable[[], Optional[str]]] = None,
    remote_config: Optional[dict] = None,
    weight_class: str = "local",
) -> Tuple[bool, Optional[Dict[str, str]], Optional[str]]:
    """主引擎 + DrissionPage 兜底的滑块验证编排。

    Args:
        user_id: 用户/账号 ID
        url: 验证页面 URL
        enable_learning: 主引擎是否启用轨迹学习
        headless: 主引擎是否无头
        browser_timeout: 主引擎单次超时（秒）
        existing_cookies_str: 现有 cookie 字符串，供兜底引擎注入
        url_provider: 可选回调，浏览器就绪后用于重新获取新鲜验证链接，规避等待槽位导致的链接过期
        remote_config: 远程过滑块配置 dict {url, secret, pass_cookies, device_id} | None。
            pass_cookies 为 True 时，会把 existing_cookies_str 与 device_id 一并传给远程端，
            供其在链接过期时重取新链接继续处理。
        weight_class: 排队来源类别（"local"=本地Token刷新 / "remote"=远程过滑块接口），
            仅 real_mouse 引擎排队时按权重放行使用；默认 "local"。

    Returns:
        (是否成功, cookies 字典 | None, 通过引擎 | None)
        通过引擎取值：'playwright'（主引擎）/ 'drissionpage'（兜底引擎）/ 'real_mouse'（真实鼠标）/ 'remote'（远程接口）/ None（未成功）
    """
    # -1. 远程过滑块（可选，由全局配置 remote_config 触发）：
    #     已配置则优先调远程接口求解；超时/网络不可用 → 回退本机逻辑；
    #     非超时（远程有返回，无论成败）→ 直接采用远程结果，不回退。
    #     注意：远程接口自身（/internal/captcha/solve）调用本函数时不传 remote_config，
    #     从而避免“远程地址指回本机”造成的无限递归。
    if remote_config:
        r_url = (remote_config.get("url") or "").strip()
        r_secret = (remote_config.get("secret") or "").strip()
        if r_url and r_secret:
            # 仅在开启"传递Cookie"开关时携带账号 Cookie / 设备 ID（默认不传）
            if remote_config.get("pass_cookies"):
                r_cookies = existing_cookies_str or ""
                r_device_id = (remote_config.get("device_id") or "")
            else:
                r_cookies = ""
                r_device_id = ""
            status, r_cookies_out = _call_remote_solve(
                r_url, r_secret, user_id, url, browser_timeout, r_cookies, r_device_id
            )
            if status == "ok" and _has_x5sec(r_cookies_out):
                logger.info(f"【{user_id}】远程过滑块成功，采用远程结果")
                return True, r_cookies_out, "remote"
            # 远程反馈验证链接已过期：本端用 url_provider 重取新鲜链接后再调远程（最多 2 次），
            # 与本机处理链接过期保持一致；无 url_provider 或重试用尽则按失败处理（不回退）。
            remote_url_refreshes = 0
            max_remote_url_refreshes = 2 if url_provider is not None else 0
            while status == "url_expired" and remote_url_refreshes < max_remote_url_refreshes:
                remote_url_refreshes += 1
                logger.warning(
                    f"【{user_id}】远程反馈验证链接已过期，第{remote_url_refreshes}次重取新链接后重试远程"
                )
                try:
                    fresh = url_provider()
                except Exception as up_e:
                    logger.warning(f"【{user_id}】重取验证链接异常: {up_e}")
                    fresh = None
                if fresh == CAPTCHA_NOT_REQUIRED:
                    logger.info(f"【{user_id}】重取链接时检测到 token 已可用，无需滑块，结束远程流程")
                    return True, None, "remote"
                if not (fresh and isinstance(fresh, str)):
                    logger.info(f"【{user_id}】重取验证链接失败，远程过滑块按失败处理（不回退）")
                    return False, None, "remote"
                status, r_cookies_out = _call_remote_solve(
                    r_url, r_secret, user_id, fresh, browser_timeout, r_cookies, r_device_id
                )
                if status == "ok" and _has_x5sec(r_cookies_out):
                    logger.info(f"【{user_id}】远程过滑块成功（刷新链接后），采用远程结果")
                    return True, r_cookies_out, "remote"
            if status in ("fail", "url_expired"):
                logger.info(f"【{user_id}】远程过滑块未通过（非超时），按配置不回退本机，返回失败")
                return False, None, "remote"
            # status == 'fallback' → 落到下面的本机逻辑

    # 0. 真实鼠标模式（可选，环境变量 CAPTCHA_REAL_MOUSE=true 开启）：
    #    用物理光标回放真人轨迹，成功率高但会占用桌面鼠标，仅限有桌面的 Windows。
    #    一旦开启且引擎可用：真实鼠标即为唯一引擎——成功返回成功；失败也【直接返回失败、不回退】
    #    原 CDP/DrissionPage 逻辑（避免低效且会被风控识破的 CDP 滑动；下次重试仍走真实鼠标）。
    #    仅当“开启了但引擎不可用”（非 Windows / 未装 pyautogui，属误配置）时，才回退原逻辑兜底。
    if _real_mouse_enabled():
        real_mouse_available = False
        run_real_mouse_verification = None
        try:
            from common.services.captcha.real_mouse_slider import (
                run_real_mouse_verification as _rm_run,
                REAL_MOUSE_AVAILABLE as _rm_avail,
            )
            run_real_mouse_verification = _rm_run
            real_mouse_available = bool(_rm_avail)
        except Exception as imp_e:
            logger.warning(f"【{user_id}】真实鼠标引擎导入失败: {imp_e}")

        if real_mouse_available and run_real_mouse_verification is not None:
            logger.info(f"【{user_id}】启用真实鼠标滑块引擎（失败不回退，重试仍用真实鼠标）")
            try:
                rm_ok, rm_cookies = run_real_mouse_verification(
                    user_id, url,
                    existing_cookies_str=existing_cookies_str,
                    browser_timeout=max(browser_timeout, 40),
                    url_provider=url_provider,
                    weight_class=weight_class,
                )
            except Exception as rm_e:
                logger.warning(f"【{user_id}】真实鼠标引擎执行异常: {rm_e}")
                rm_ok, rm_cookies = False, None
            if rm_ok and _has_x5sec(rm_cookies):
                return True, rm_cookies, "real_mouse"
            # 验证链接已过期且无法自助重取：上报 url_expired，供远程调用方刷新URL后重试
            if rm_cookies == URL_EXPIRED:
                logger.info(f"【{user_id}】真实鼠标引擎检测到验证链接已过期，返回 url_expired")
                return False, None, "url_expired"
            # 按配置：真实鼠标失败不回退原引擎，直接返回失败
            logger.info(f"【{user_id}】真实鼠标未通过，按配置不回退，返回失败（下次重试仍用真实鼠标）")
            return False, None, None
        else:
            logger.error(
                f"【{user_id}】CAPTCHA_REAL_MOUSE 已开启但引擎不可用"
                f"（需 Windows 桌面 + pyautogui），本次回退原有滑块逻辑"
            )

    # 1. Playwright 主引擎
    ok, cookies = run_slider_verification(
        user_id, url, enable_learning, headless, browser_timeout,
        url_provider=url_provider,
    )
    if ok and _has_x5sec(cookies):
        return True, cookies, "playwright"

    # 验证链接已过期且无法自助重取：上报 url_expired，供远程调用方刷新URL后重试
    # （过期页无需再走兜底引擎，兜底同样会命中过期页，直接返回让调用方刷新链接更高效）
    if cookies == URL_EXPIRED:
        logger.info(f"【{user_id}】主引擎检测到验证链接已过期，返回 url_expired")
        return False, None, "url_expired"

    # 2. 判断是否需要兜底
    fallback_enabled, fb_headless, fb_timeout = _load_fallback_config()
    if not fallback_enabled or not DRISSIONPAGE_AVAILABLE:
        if not fallback_enabled:
            logger.info(f"【{user_id}】DrissionPage 兜底未启用，返回主引擎结果")
        return ok, cookies, ("playwright" if (ok and cookies) else None)

    # 3. DrissionPage 兜底
    # 兜底前同样尝试刷新链接，避免主引擎耗时后链接再次过期
    fb_url = url
    if url_provider is not None:
        try:
            fresh = url_provider()
            if fresh == CAPTCHA_NOT_REQUIRED:
                # token 已可用、风控已解除，无需滑块，跳过兜底引擎（由上层采用新 token）
                logger.info(f"【{user_id}】检测到 token 已可用，跳过 DrissionPage 兜底引擎")
                return ok, cookies, ("playwright" if (ok and cookies) else None)
            if fresh and isinstance(fresh, str):
                fb_url = fresh
                logger.info(f"【{user_id}】兜底引擎使用刷新后的验证链接")
        except Exception as up_e:
            logger.warning(f"【{user_id}】兜底前刷新验证链接失败，沿用原链接: {up_e}")

    logger.info(f"【{user_id}】主引擎滑块未通过，启用 DrissionPage 兜底引擎重试")
    ok2, cookies2 = run_drissionpage_verification(
        user_id, fb_url, existing_cookies_str=existing_cookies_str,
        headless=fb_headless, browser_timeout=fb_timeout,
    )
    if ok2 and _has_x5sec(cookies2):
        return True, cookies2, "drissionpage"

    # 4. 兜底也未取得 x5sec：优先保留主引擎"成功但无 x5sec"的结果，
    #    以维持上层原有的"无 x5sec 不计入禁用"语义。
    if ok and cookies:
        return ok, cookies, "playwright"
    return ok2, cookies2, None
