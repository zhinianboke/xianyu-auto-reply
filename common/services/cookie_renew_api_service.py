"""
Cookie续期共通服务（接口续期 + 浏览器续期）

功能：
1. 调用 hasLogin.do 接口续期登录Cookie（sgcookie、tracknick、csg、unb等）
2. 调用 silentHasLogin.do 接口续期短登录Cookie
3. 调用 setLoginSettings.do 接口续期长登录Cookie（havana_lgc2_77）
4. 按顺序合并三个接口返回的 Set-Cookie 到原始Cookie字符串
5. 接口续期失败时，自动尝试浏览器续期（打开页面点击"快速进入"按钮）
6. 浏览器续期也失败时，标记需要执行账号密码登录
7. 返回合并后的新Cookie字符串、更新字段列表、续期方式、各步骤执行状态

续期优先级：接口续期 > 浏览器续期 > 账号密码登录

本模块为纯工具服务，不依赖数据库、不依赖定时任务框架，
任何需要通过接口续期Cookie的场景都可以直接调用。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import trans_cookies


# hasLogin.do 接口地址（登录态确认续期，返回 sgcookie/tracknick/csg/unb 等）
_HAS_LOGIN_URL_WEB = "https://passport.goofish.com/newlogin/hasLogin.do"
# silentHasLogin.do 接口地址
_HAS_LOGIN_URL = "https://passport.goofish.com/newlogin/silentHasLogin.do"
# setLoginSettings.do 接口地址（长登录续期）
_SET_LOGIN_SETTINGS_URL = "https://passport.goofish.com/ac/account/setLoginSettings.do"
# 接口请求超时（秒）
_REQUEST_TIMEOUT_SECONDS = 20


@dataclass(slots=True)
class CookieRenewApiResult:
    """续期结果（支持接口续期、浏览器续期、账号密码登录三种方式）。

    Attributes:
        success: 最终是否续期成功（接口续期成功 或 浏览器续期成功）
        new_cookies_str: 合并后的完整Cookie字符串（无变化时与传入值相同）
        updated_cookie_names: 实际发生变化的Cookie字段名列表
        api_message: 业务层消息或错误描述
        response_text: silentHasLogin.do 的原始响应文本（用于失败排查）
        renew_method: 最终成功的续期方式（api/browser/none）
        need_password_login: 是否需要执行账号密码登录（接口和浏览器都失败时为True）
        step_details: 各步骤执行详情，记录每一步的状态
    """

    success: bool
    new_cookies_str: str
    updated_cookie_names: list[str] = field(default_factory=list)
    api_message: str = ""
    response_text: str = ""
    renew_method: str = "none"  # api / browser / none
    need_password_login: bool = False
    step_details: str = ""


class CookieRenewApiService:
    """Cookie接口续期共通服务。

    使用方式：
        from common.services.cookie_renew_api_service import cookie_renew_api_service

        result = await cookie_renew_api_service.renew(cookies_str, account_id)
        if result.updated_cookie_names:
            # Cookie有更新，保存到数据库
            ...
    """

    async def renew(self, cookies_str: str, account_id: str = "", source: str = "") -> CookieRenewApiResult:
        """执行续期，根据来源和 havana_lgc2_77 字段决定续期顺序。

        流程：
        - source="scheduled_task"（定时任务触发）：接口续期 → 浏览器续期 → 密码登录
        - 有 havana_lgc2_77：浏览器续期 → 接口续期 → 密码登录
        - 无 havana_lgc2_77：接口续期 → 浏览器续期 → 密码登录

        Args:
            cookies_str: 当前完整的Cookie字符串
            account_id: 账号ID（仅用于日志标识，可为空）
            source: 调用来源标识（"scheduled_task"表示定时任务触发）

        Returns:
            CookieRenewApiResult: 续期结果
        """
        log_prefix = f"【Cookie续期】账号 {account_id}" if account_id else "【Cookie续期】"

        if not cookies_str or not cookies_str.strip():
            return CookieRenewApiResult(
                success=False,
                new_cookies_str=cookies_str or "",
                api_message="Cookie为空，无法调用续期接口",
                renew_method="none",
                need_password_login=True,
                step_details="Cookie为空，跳过所有续期",
            )

        # 定时任务触发：固定走 接口续期 → 浏览器续期 → 密码登录
        if source == "scheduled_task":
            logger.info(f"{log_prefix} 定时任务触发，按顺序: 接口续期 → 浏览器续期 → 密码登录")
            return await self._renew_api_first(cookies_str, account_id, log_prefix)

        # 非定时任务：根据 havana_lgc2_77 判断
        has_long_login_token = False
        try:
            cookie_dict = trans_cookies(cookies_str)
            lgc2_value = cookie_dict.get("havana_lgc2_77", "").strip()
            has_long_login_token = bool(lgc2_value)
        except Exception:
            pass

        if has_long_login_token:
            logger.info(f"{log_prefix} 检测到 havana_lgc2_77，优先使用浏览器续期")
            return await self._renew_browser_first(cookies_str, account_id, log_prefix)
        else:
            logger.info(f"{log_prefix} 未检测到 havana_lgc2_77，优先使用接口续期")
            return await self._renew_api_first(cookies_str, account_id, log_prefix)

    async def _renew_browser_first(
        self, cookies_str: str, account_id: str, log_prefix: str
    ) -> CookieRenewApiResult:
        """浏览器续期优先流程：浏览器续期 → 接口续期（必须） → 密码登录"""
        step_details_parts: list[str] = []

        # ========== 第1步：浏览器续期 ==========
        browser_cookies_str = cookies_str
        try:
            from common.services.cookie_renew_browser_service import cookie_renew_browser_service

            logger.info(f"{log_prefix} 开始浏览器续期...")
            browser_result = await cookie_renew_browser_service.renew(cookies_str, account_id)

            if browser_result.success:
                step_details_parts.append(f"第1步-浏览器续期: 成功（{browser_result.message}）")
                logger.info(f"{log_prefix} 浏览器续期成功: {browser_result.message}")
                # 使用浏览器续期后的cookies继续执行接口续期
                browser_cookies_str = browser_result.new_cookies_str
            else:
                browser_fail_reason = browser_result.message
                step_details_parts.append(f"第1步-浏览器续期: 失败（{browser_fail_reason}）")
                logger.warning(f"{log_prefix} 浏览器续期失败: {browser_fail_reason}，尝试接口续期...")

        except Exception as exc:
            step_details_parts.append(f"第1步-浏览器续期: 异常（{exc}）")
            logger.error(f"{log_prefix} 浏览器续期异常: {exc}")

        # ========== 第2步：接口续期（浏览器续期成功后也必须执行，确保长登录token刷新） ==========
        result = await self._do_api_renew_with_retry(browser_cookies_str, log_prefix)

        if result["long_login_has_cookies"]:
            step_details_parts.append("第2步-接口续期: 成功（setLoginSettings返回了Set-Cookie）")
            final_cookies_str = result["new_cookies_str"]
            final_updated_names = self._calc_updated_names(cookies_str, final_cookies_str)
            return CookieRenewApiResult(
                success=True,
                new_cookies_str=final_cookies_str,
                updated_cookie_names=final_updated_names,
                api_message=result["api_message"],
                response_text=result["response_text"],
                renew_method="browser+api",
                need_password_login=False,
                step_details=" → ".join(step_details_parts),
            )

        # 接口续期失败
        api_fail_reason = result["api_message"] or "setLoginSettings未返回Set-Cookie"
        step_details_parts.append(f"第2步-接口续期: 失败（{api_fail_reason}）")
        logger.warning(f"{log_prefix} 接口续期失败: {api_fail_reason}")

        # 浏览器续期结果仅作记录，不影响最终判断
        # 只有 setLoginSettings 返回 Set-Cookie 才算续期成功
        if browser_cookies_str != cookies_str:
            # 浏览器续期有更新Cookie，记录但不视为成功
            step_details_parts.append("浏览器续期已刷新Cookie，但接口续期未成功，需要密码登录")
            logger.info(f"{log_prefix} 浏览器续期已刷新Cookie，但setLoginSettings未返回Set-Cookie，仍需密码登录")

        # ========== 接口续期失败，标记需要密码登录 ==========
        step_details_parts.append("第3步-需要账号密码登录")
        # 使用浏览器续期后的cookies（如果有更新的话），即使接口续期失败也保留浏览器刷新的部分
        final_cookies_str = browser_cookies_str if browser_cookies_str != cookies_str else result["new_cookies_str"]
        final_updated_names = self._calc_updated_names(cookies_str, final_cookies_str)

        return CookieRenewApiResult(
            success=False,
            new_cookies_str=final_cookies_str,
            updated_cookie_names=final_updated_names,
            api_message=f"浏览器续期和接口续期均失败，需要账号密码登录。{api_fail_reason}",
            response_text=result["response_text"],
            renew_method="none",
            need_password_login=True,
            step_details=" → ".join(step_details_parts),
        )

    async def _renew_api_first(
        self, cookies_str: str, account_id: str, log_prefix: str
    ) -> CookieRenewApiResult:
        """接口续期优先流程：接口续期 → 浏览器续期 → 密码登录"""
        step_details_parts: list[str] = []

        # ========== 第1步：接口续期 ==========
        result = await self._do_api_renew_with_retry(cookies_str, log_prefix)

        if result["long_login_has_cookies"]:
            step_details_parts.append("第1步-接口续期: 成功（setLoginSettings返回了Set-Cookie）")
            final_cookies_str = result["new_cookies_str"]
            final_updated_names = self._calc_updated_names(cookies_str, final_cookies_str)
            return CookieRenewApiResult(
                success=True,
                new_cookies_str=final_cookies_str,
                updated_cookie_names=final_updated_names,
                api_message=result["api_message"],
                response_text=result["response_text"],
                renew_method="api",
                need_password_login=False,
                step_details=" → ".join(step_details_parts),
            )

        # 接口续期失败
        api_fail_reason = result["api_message"] or "setLoginSettings未返回Set-Cookie"
        step_details_parts.append(f"第1步-接口续期: 失败（{api_fail_reason}）")
        logger.warning(f"{log_prefix} 接口续期失败: {api_fail_reason}，尝试浏览器续期...")

        # ========== 第2步：浏览器续期 ==========
        browser_renewed_cookies_str: str | None = None
        try:
            from common.services.cookie_renew_browser_service import cookie_renew_browser_service

            browser_cookies_str = result["new_cookies_str"] or cookies_str
            browser_result = await cookie_renew_browser_service.renew(
                browser_cookies_str, account_id
            )

            if browser_result.success:
                step_details_parts.append(f"第2步-浏览器续期: 成功（{browser_result.message}）")
                logger.info(f"{log_prefix} 浏览器续期成功: {browser_result.message}，继续调用setLoginSettings验证...")
                browser_renewed_cookies_str = browser_result.new_cookies_str

                # 浏览器续期成功后，必须再调用 setLoginSettings.do 验证长登录token
                # 只有 setLoginSettings 返回 Set-Cookie 才算真正续期成功
                api_verify_result = await self._do_api_renew_with_retry(
                    browser_renewed_cookies_str, f"{log_prefix}[浏览器后验证]"
                )

                if api_verify_result["long_login_has_cookies"]:
                    step_details_parts.append("第3步-接口验证: 成功（setLoginSettings返回了Set-Cookie）")
                    final_cookies_str = api_verify_result["new_cookies_str"]
                    final_updated_names = self._calc_updated_names(cookies_str, final_cookies_str)
                    return CookieRenewApiResult(
                        success=True,
                        new_cookies_str=final_cookies_str,
                        updated_cookie_names=final_updated_names,
                        api_message=f"接口续期失败，浏览器续期成功，setLoginSettings验证通过",
                        response_text=api_verify_result["response_text"],
                        renew_method="browser+api",
                        need_password_login=False,
                        step_details=" → ".join(step_details_parts),
                    )

                # setLoginSettings 未返回 Set-Cookie，浏览器续期不算成功
                step_details_parts.append("第3步-接口验证: 失败（setLoginSettings未返回Set-Cookie，浏览器续期不算成功）")
                logger.warning(
                    f"{log_prefix} 浏览器续期已刷新Cookie，但setLoginSettings未返回Set-Cookie，仍需密码登录"
                )
            else:
                # 浏览器续期失败
                browser_fail_reason = browser_result.message
                step_details_parts.append(f"第2步-浏览器续期: 失败（{browser_fail_reason}）")
                logger.warning(f"{log_prefix} 浏览器续期失败: {browser_fail_reason}")

        except Exception as exc:
            step_details_parts.append(f"第2步-浏览器续期: 异常（{exc}）")
            logger.error(f"{log_prefix} 浏览器续期异常: {exc}")

        # ========== 都失败，标记需要密码登录 ==========
        step_details_parts.append("需要账号密码登录")
        # 如果浏览器续期有更新Cookie，保留浏览器刷新的部分
        final_cookies_str = browser_renewed_cookies_str if browser_renewed_cookies_str else result["new_cookies_str"]
        final_updated_names = self._calc_updated_names(cookies_str, final_cookies_str)

        return CookieRenewApiResult(
            success=False,
            new_cookies_str=final_cookies_str,
            updated_cookie_names=final_updated_names,
            api_message=f"接口续期和浏览器续期均失败，需要账号密码登录。{api_fail_reason}",
            response_text=result["response_text"],
            renew_method="none",
            need_password_login=True,
            step_details=" → ".join(step_details_parts),
        )

    async def _do_api_renew_with_retry(self, cookies_str: str, log_prefix: str) -> dict:
        """执行接口续期（含一次重试）。"""
        result = await self._do_renew_once(cookies_str, log_prefix)

        if not result["long_login_has_cookies"]:
            logger.info(f"{log_prefix} setLoginSettings未返回Set-Cookie，2秒后重试...")
            await asyncio.sleep(2)
            retry_cookies_str = result["new_cookies_str"]
            result = await self._do_renew_once(retry_cookies_str, f"{log_prefix}[重试]")

        return result

    def _calc_updated_names(self, original_str: str, new_str: str) -> list[str]:
        """对比原始Cookie和新Cookie，计算更新字段列表。"""
        if new_str == original_str:
            return []
        try:
            original_cookies = trans_cookies(original_str) if original_str else {}
            new_cookies = trans_cookies(new_str) if new_str else {}
            return [
                name for name, value in new_cookies.items()
                if original_cookies.get(name) != value
            ]
        except Exception:
            return []

    async def _do_renew_once(
        self,
        cookies_str: str,
        log_prefix: str,
    ) -> dict:
        """执行一次续期（依次调用三个接口并合并结果）。

        调用顺序：hasLogin.do → silentHasLogin.do → setLoginSettings.do
        每个接口返回的 Set-Cookie 都会合并到 Cookie 中，后续接口使用合并后的 Cookie。

        Returns:
            dict: 包含 new_cookies_str, updated_cookie_names, long_login_has_cookies,
                  api_success, api_message, response_text
        """
        all_set_cookie_headers: list[str] = []
        current_cookies_str = cookies_str

        # 1. 调用 hasLogin.do（登录态确认，返回 sgcookie/tracknick/csg/unb 等）
        has_login_web_result = await self._call_has_login_web_api(current_cookies_str, log_prefix)
        web_set_cookies: list[str] = has_login_web_result["set_cookie_headers"]
        if web_set_cookies:
            all_set_cookie_headers.extend(web_set_cookies)
            # 合并到当前 Cookie，供后续接口使用
            current_cookies_str, _ = self._merge_set_cookies(
                current_cookies_str, web_set_cookies, f"{log_prefix}[hasLogin合并]"
            )

        # 2. 调用 silentHasLogin.do
        has_login_result = await self._call_has_login_api(current_cookies_str, log_prefix)
        set_cookie_headers: list[str] = has_login_result["set_cookie_headers"]
        api_success: bool = has_login_result["api_success"]
        api_message: str = has_login_result["api_message"]
        response_text: str = has_login_result["response_text"]
        if set_cookie_headers:
            all_set_cookie_headers.extend(set_cookie_headers)
            # 合并到当前 Cookie，供后续接口使用
            current_cookies_str, _ = self._merge_set_cookies(
                current_cookies_str, set_cookie_headers, f"{log_prefix}[silentHasLogin合并]"
            )

        # 3. 调用 setLoginSettings.do（长登录续期）
        long_login_set_cookies = await self._call_set_login_settings(current_cookies_str, log_prefix)
        long_login_has_cookies = len(long_login_set_cookies) > 0
        if long_login_set_cookies:
            all_set_cookie_headers.extend(long_login_set_cookies)

        # 4. 最终合并所有 Set-Cookie 到原始Cookie
        new_cookies_str, updated_cookie_names = self._merge_set_cookies(
            cookies_str, all_set_cookie_headers, log_prefix
        )

        return {
            "new_cookies_str": new_cookies_str,
            "updated_cookie_names": updated_cookie_names,
            "long_login_has_cookies": long_login_has_cookies,
            "api_success": api_success,
            "api_message": api_message,
            "response_text": response_text,
        }

    # ==================== 内部方法 ====================

    async def _call_has_login_web_api(
        self,
        cookies_str: str,
        log_prefix: str,
    ) -> dict[str, Any]:
        """调用 hasLogin.do 接口（Web端登录态确认续期）。

        该接口会返回 sgcookie、tracknick、csg、unb、last_u_xianyu_web、last_cc 等 Set-Cookie。
        请求需要从 Cookie 中提取 XSRF-TOKEN、unb、cookie2 等参数。

        Returns:
            dict: 包含 set_cookie_headers, api_success, api_message
        """
        result: dict[str, Any] = {
            "set_cookie_headers": [],
            "api_success": False,
            "api_message": "",
        }

        try:
            # 从 Cookie 中提取必要参数
            cookie_dict = trans_cookies(cookies_str) if cookies_str else {}
            xsrf_token = cookie_dict.get("XSRF-TOKEN", "")
            hid = cookie_dict.get("unb", "")
            hsiz = cookie_dict.get("cookie2", "")
            # umidToken: 设备指纹，从 _uab_collina 或 cna 中获取
            umid_token = cookie_dict.get("_uab_collina", "") or cookie_dict.get("cna", "")
            # _csrf_token: 从 _tb_token_ Cookie 中获取
            csrf_token = cookie_dict.get("_tb_token_", "")

            if not hid:
                result["api_message"] = "Cookie中缺少unb字段，跳过hasLogin.do"
                logger.info(f"{log_prefix} Cookie中缺少unb，跳过hasLogin.do")
                return result

            # 生成 pageTraceId（格式：前缀 + 时间戳毫秒 + 随机后缀）
            import time as _time
            import random as _random
            _now_ms = str(int(_time.time() * 1000))
            _rand_suffix = str(_random.randint(100000, 999999))
            page_trace_id = f"21504{_now_ms}{_rand_suffix}"

            # 生成随机 rnd（referer 中使用）
            rnd_value = str(_random.random())

            # 构建请求参数
            params = {
                "appName": "xianyu",
                "fromSite": "77",
            }
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN",
                "content-type": "application/x-www-form-urlencoded",
                "sec-ch-ua": '"Chromium";v="145", "Not:A-Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "bx-v": "2.5.31",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
                ),
                "referer": f"https://passport.goofish.com/mini_login.htm?lang=zh_cn&appName=xianyu&appEntrance=web&styleType=vertical&bizParams=&notLoadSsoView=false&notKeepLogin=false&isMobile=false&qrCodeFirst=false&stie=77&rnd={rnd_value}",
                "cookie": cookies_str.replace("\n", "").replace("\r", ""),
            }
            # 如果有 XSRF-TOKEN，加入请求头
            if xsrf_token:
                headers["x-xsrf-token"] = xsrf_token

            # 构建 POST body（包含服务端必需的核心参数）
            post_data = (
                f"hid={hid}"
                f"&ltl=true"
                f"&appName=xianyu"
                f"&appEntrance=web"
                f"&_csrf_token={csrf_token}"
                f"&umidToken={umid_token}"
                f"&hsiz={hsiz}"
                f"&bizParams=taobaoBizLoginFrom%3Dweb%26renderRefer%3Dhttps%253A%252F%252Fwww.goofish.com%252F"
                f"&mainPage=false"
                f"&isMobile=false"
                f"&lang=zh_CN"
                f"&returnUrl="
                f"&fromSite=77"
                f"&isIframe=true"
                f"&documentReferer=https%3A%2F%2Fwww.goofish.com%2F"
                f"&defaultView=hasLogin"
                f"&umidTag=SERVER"
                f"&deviceId="
                f"&pageTraceId={page_trace_id}"
            )

            async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as http_session:
                async with http_session.post(
                    _HAS_LOGIN_URL_WEB,
                    params=params,
                    data=post_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
                    allow_redirects=False,
                ) as response:
                    result["set_cookie_headers"] = list(
                        response.headers.getall("Set-Cookie", [])
                    )
                    logger.info(
                        f"{log_prefix} hasLogin.do 收到 "
                        f"{len(result['set_cookie_headers'])} 个 Set-Cookie 头"
                    )

                    if response.status not in (200, 302, 303):
                        result["api_message"] = f"hasLogin.do HTTP状态异常：{response.status}"
                        logger.warning(f"{log_prefix} hasLogin.do HTTP状态异常：{response.status}")
                        return result

                    # 解析响应JSON判断业务层成功
                    response_text = await response.text()
                    try:
                        res_json = json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError:
                        result["api_message"] = "hasLogin.do 返回内容无法解析为JSON"
                        logger.warning(f"{log_prefix} hasLogin.do 返回非JSON内容")
                        return result

                    content = res_json.get("content") if isinstance(res_json, dict) else None
                    is_success = False
                    if isinstance(content, dict):
                        is_success = bool(content.get("success", False))
                    result["api_success"] = is_success

                    if is_success:
                        result["api_message"] = "hasLogin.do 调用成功"
                        logger.info(f"{log_prefix} hasLogin.do 业务成功")
                    else:
                        result["api_message"] = "hasLogin.do 业务返回失败"
                        logger.info(f"{log_prefix} hasLogin.do 业务失败: {response_text[:200]}")

                    return result

        except asyncio.TimeoutError:
            result["api_message"] = f"hasLogin.do 请求超时（超过 {_REQUEST_TIMEOUT_SECONDS} 秒）"
            logger.warning(f"{log_prefix} hasLogin.do 请求超时")
            return result
        except aiohttp.ClientError as exc:
            result["api_message"] = f"hasLogin.do 网络请求失败：{exc}"
            logger.warning(f"{log_prefix} hasLogin.do 网络请求失败: {exc}")
            return result
        except Exception as exc:
            result["api_message"] = f"hasLogin.do 请求异常：{exc}"
            logger.error(f"{log_prefix} hasLogin.do 请求异常: {exc}")
            return result

    async def _call_has_login_api(
        self,
        cookies_str: str,
        log_prefix: str,
    ) -> dict[str, Any]:
        """调用 silentHasLogin.do 接口。

        Returns:
            dict: 包含 set_cookie_headers, response_text, api_success, api_message
        """
        params = {
            "documentReferer": "https://www.goofish.com/",
            "appName": "xianyu",
            "appEntrance": "xianyu_sdkSilent",
            "fromSite": "0",
            "ltl": "true",
        }
        headers = {
            "accept": "*/*",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,ru;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="146", "Not=A?Brand";v="8", "Not/A)Brand";v="146"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Win32"',
            "sec-ch-ua-platform-version": '"10.0.0"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "Referer": "https://www.goofish.com/",
            "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        }

        result: dict[str, Any] = {
            "set_cookie_headers": [],
            "response_text": "",
            "api_success": False,
            "api_message": "",
        }

        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as http_session:
                async with http_session.post(
                    _HAS_LOGIN_URL,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
                    allow_redirects=False,
                ) as response:
                    result["set_cookie_headers"] = list(
                        response.headers.getall("Set-Cookie", [])
                    )
                    logger.info(
                        f"{log_prefix} silentHasLogin 收到 "
                        f"{len(result['set_cookie_headers'])} 个 Set-Cookie 头"
                    )
                    response_text = await response.text()
                    result["response_text"] = response_text or ""

                    if response.status not in (200, 302, 303):
                        result["api_message"] = f"接口HTTP状态异常：{response.status}"
                        logger.warning(f"{log_prefix} 接口HTTP状态异常：{response.status}")
                        return result

                    # 解析响应JSON判断业务层成功
                    try:
                        res_json = json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError:
                        result["api_message"] = "接口返回内容无法解析为JSON"
                        logger.warning(f"{log_prefix} 接口返回非JSON内容")
                        return result

                    content = res_json.get("content") if isinstance(res_json, dict) else None
                    is_success = False
                    if isinstance(content, dict):
                        is_success = bool(content.get("success", False))
                    result["api_success"] = is_success

                    if is_success:
                        result["api_message"] = "接口调用成功"
                    else:
                        message = ""
                        if isinstance(content, dict):
                            message = str(
                                content.get("titleMsg")
                                or content.get("retMsg")
                                or content.get("msg")
                                or content.get("code")
                                or ""
                            )
                        if not message and isinstance(res_json, dict):
                            ret_value = res_json.get("ret")
                            if isinstance(ret_value, list) and ret_value:
                                message = str(ret_value[0])
                            elif isinstance(ret_value, str):
                                message = ret_value
                        if not message:
                            message = "接口返回业务失败"
                        result["api_message"] = message

                    return result

        except asyncio.TimeoutError:
            result["api_message"] = f"接口请求超时（超过 {_REQUEST_TIMEOUT_SECONDS} 秒）"
            logger.warning(f"{log_prefix} silentHasLogin 请求超时")
            return result
        except aiohttp.ClientError as exc:
            result["api_message"] = f"网络请求失败：{exc}"
            logger.warning(f"{log_prefix} silentHasLogin 网络请求失败: {exc}")
            return result
        except Exception as exc:
            result["api_message"] = f"请求异常：{exc}"
            logger.error(f"{log_prefix} silentHasLogin 请求异常: {exc}")
            return result

    async def _call_set_login_settings(
        self,
        cookies_str: str,
        log_prefix: str,
    ) -> list[str]:
        """调用 setLoginSettings.do 续期长登录token。

        通过 status=0 开启/续期长登录，服务端会下发新的 havana_lgc2_77 等cookie，
        有效期30天。每次调用都会生成新token，相当于续期。

        Returns:
            有效的 Set-Cookie 响应头列表（已过滤 Max-Age=0 的删除操作）
        """
        params = {
            "fromSite": "77",
            "appName": "xianyu",
            "bizEntrance": "web",
        }
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": '"Google Chrome";v="146", "Not=A?Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        }

        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as http_session:
                async with http_session.post(
                    _SET_LOGIN_SETTINGS_URL,
                    params=params,
                    data="status=0",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
                    allow_redirects=False,
                ) as response:
                    set_cookies = list(response.headers.getall("Set-Cookie", []))

                    if set_cookies:
                        # 过滤掉 Max-Age=0 的删除操作
                        valid_cookies = [
                            sc for sc in set_cookies
                            if "Max-Age=0" not in sc and "1970" not in sc
                        ]
                        if valid_cookies:
                            cookie_names = [
                                sc.split(";")[0].split("=", 1)[0].strip()
                                for sc in valid_cookies if "=" in sc
                            ]
                            logger.info(
                                f"{log_prefix} 长登录续期成功，"
                                f"收到 {len(valid_cookies)} 个 cookie: {', '.join(cookie_names)}"
                            )
                            return valid_cookies
                        else:
                            logger.info(
                                f"{log_prefix} 长登录续期返回空值（可能已是最新）"
                            )
                    else:
                        logger.info(f"{log_prefix} 长登录续期未返回 Set-Cookie")
                    return []

        except Exception as exc:
            logger.warning(f"{log_prefix} 长登录续期异常（不影响主流程）: {exc}")
            return []

    def _merge_set_cookies(
        self,
        original_cookies_str: str,
        set_cookie_headers: list[str],
        log_prefix: str,
    ) -> tuple[str, list[str]]:
        """将 Set-Cookie 响应头与原始Cookie字符串合并。

        Args:
            original_cookies_str: 原始Cookie字符串
            set_cookie_headers: 响应头中的所有 Set-Cookie 值
            log_prefix: 日志前缀

        Returns:
            (new_cookies_str, updated_cookie_names)
        """
        if not set_cookie_headers:
            return original_cookies_str, []

        try:
            original_cookies = trans_cookies(original_cookies_str) if original_cookies_str else {}
        except Exception as exc:
            logger.warning(f"{log_prefix} 解析原始Cookie失败: {exc}，以空字典作为基准")
            original_cookies = {}

        merged_cookies: dict[str, str] = dict(original_cookies)
        updated_cookie_names: list[str] = []

        for raw_cookie in set_cookie_headers:
            parsed = self._parse_single_set_cookie(raw_cookie)
            if not parsed:
                continue
            name, value = parsed
            if merged_cookies.get(name) != value:
                if name not in updated_cookie_names:
                    updated_cookie_names.append(name)
                merged_cookies[name] = value

        if not updated_cookie_names:
            return original_cookies_str, []

        new_cookies_str = "; ".join(f"{name}={value}" for name, value in merged_cookies.items())
        return new_cookies_str, updated_cookie_names

    @staticmethod
    def _parse_single_set_cookie(raw_cookie: str) -> tuple[str, str] | None:
        """解析单个 Set-Cookie 响应头，返回 (name, value)。"""
        if not raw_cookie or "=" not in raw_cookie:
            return None
        cookie_pair = raw_cookie.split(";", 1)[0].strip()
        if "=" not in cookie_pair:
            return None
        name, value = cookie_pair.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            return None
        return name, value


# 全局单例
cookie_renew_api_service = CookieRenewApiService()
