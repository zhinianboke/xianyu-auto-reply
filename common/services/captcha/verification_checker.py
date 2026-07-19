"""
验证结果检查器

负责两件事：
1. 滑动前：基于按钮/轨道 bounding box 估算滑动距离（兼容刮刮乐），并对接 JS
   精确尺寸读取以提高精度；
2. 滑动后：综合多种特征判定本次是否通过：
   - 滑块容器整体消失或被 detach
   - 出现 .nc_ok_icon 等成功标志
   - #nc_1_n1z 滑块按钮被隐藏
   - 严格二次确认：URL 是否离开 punish 页 + x5sec 是否真正被新下发
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger

try:
    from playwright.sync_api import Page, ElementHandle, Frame
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    ElementHandle = Any
    Frame = Any


class VerificationChecker:
    """验证结果检查器"""

    # NC 滑块"已通过"的常见标志
    SUCCESS_SELECTORS = [
        ".nc_ok_icon",
        ".nc-lang-cnt .nc_ok",
        "#nc_1_n1z.nc_ok",
    ]

    # 仍未通过的 URL 关键字 —— 出现任一即视为风控未放行
    PUNISH_URL_KEYWORDS: Tuple[str, ...] = (
        "punish",
        "x5step=2",
        "action=captcha",
        "pureCaptcha",
        "/captcha",
    )

    def __init__(self, page: Page, user_id: str = "default"):
        """
        初始化验证检查器

        Args:
            page: Playwright页面对象
            user_id: 用户ID，用于日志标识
        """
        self.page = page
        self.user_id = user_id
        self.pure_user_id = self._extract_pure_user_id(user_id)
        self._detected_slider_frame: Optional[Frame] = None
        # 由 slider_stealth 在滑动前注入：滑动前的 x5sec 值（用于对比是否真下发）
        self._pre_x5sec_value: Optional[str] = None
        # 由 slider_stealth 注入：上下文 cookies 读取回调（返回 dict）
        self._cookies_reader: Optional[Callable[[], Dict[str, str]]] = None

    def _extract_pure_user_id(self, user_id: str) -> str:
        """提取纯用户ID"""
        if '_' in user_id:
            parts = user_id.split('_')
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) >= 10:
                return '_'.join(parts[:-1])
        return user_id

    def set_detected_frame(self, frame: Optional[Frame]):
        """设置检测到的滑块frame"""
        self._detected_slider_frame = frame

    def set_pre_x5sec(self, value: Optional[str]) -> None:
        """由上层注入：滑动前的 x5sec 值快照，用于事后对比。"""
        self._pre_x5sec_value = value

    def set_cookies_reader(self, reader: Optional[Callable[[], Dict[str, str]]]) -> None:
        """由上层注入读取当前 context.cookies 的回调（() -> dict）。"""
        self._cookies_reader = reader

    def _read_current_cookies(self) -> Dict[str, str]:
        """安全读取当前浏览器 cookies；reader 未注入时返回空 dict。"""
        if not callable(self._cookies_reader):
            return {}
        try:
            res = self._cookies_reader() or {}
            if isinstance(res, dict):
                return res
            return {}
        except Exception as e:
            logger.info(f"【{self.pure_user_id}】读取 cookies 失败: {e}")
            return {}

    def _is_punish_url(self, url: str) -> bool:
        """判断 URL 是否仍在风控页（punish/二阶段验证/captcha 等）。"""
        if not url:
            return False
        return any(k in url for k in self.PUNISH_URL_KEYWORDS)

    def is_scratch_captcha(self) -> bool:
        """检测是否为刮刮乐类型验证码"""
        try:
            page_content = self.page.content()
            scratch_required = ['scratch-captcha', 'scratch-captcha-btn', 'scratch-captcha-slider']
            has_scratch_feature = any(keyword in page_content for keyword in scratch_required)

            scratch_instructions = ['Release the slider', 'pillows', 'fully appears', 'after', 'appears']
            has_scratch_instruction = sum(1 for keyword in scratch_instructions if keyword in page_content) >= 2

            is_scratch = has_scratch_feature or has_scratch_instruction

            if is_scratch:
                logger.info(f"【{self.pure_user_id}】🎨 检测到刮刮乐类型验证码")

            return is_scratch
        except Exception as e:
            logger.info(f"【{self.pure_user_id}】检测刮刮乐类型时出错: {e}")
            return False

    def calculate_slide_distance(
        self,
        slider_button: ElementHandle,
        slider_track: ElementHandle
    ) -> float:
        """计算滑动距离 - 增强精度，支持刮刮乐

        Args:
            slider_button: 滑块按钮元素
            slider_track: 滑块轨道元素

        Returns:
            滑动距离（像素）
        """
        try:
            button_box = slider_button.bounding_box()
            if not button_box:
                logger.error(f"【{self.pure_user_id}】无法获取滑块按钮位置")
                return 0

            track_box = slider_track.bounding_box()
            if not track_box:
                logger.error(f"【{self.pure_user_id}】无法获取滑块轨道位置")
                return 0

            is_scratch = self.is_scratch_captcha()

            # 使用JavaScript获取更精确的尺寸
            try:
                precise_distance = self.page.evaluate("""
                    () => {
                        const button = document.querySelector('#nc_1_n1z') || document.querySelector('.nc_iconfont');
                        const track = document.querySelector('#nc_1_n1t') || document.querySelector('.nc_scale');
                        if (button && track) {
                            const buttonRect = button.getBoundingClientRect();
                            const trackRect = track.getBoundingClientRect();
                            return trackRect.width - buttonRect.width;
                        }
                        return null;
                    }
                """)

                if precise_distance and precise_distance > 0:
                    logger.info(f"【{self.pure_user_id}】使用JavaScript精确计算滑动距离: {precise_distance:.2f}px")

                    if is_scratch:
                        scratch_ratio = random.uniform(0.25, 0.35)
                        final_distance = precise_distance * scratch_ratio
                        logger.warning(f"【{self.pure_user_id}】🎨 刮刮乐模式：滑动{scratch_ratio*100:.1f}%距离 ({final_distance:.2f}px)")
                        return final_distance

                    # 普通 NC 滑块必须精确到达轨道终点。历史上的 ±2px 随机偏移会让
                    # 视觉状态变化，但服务端仍可能按距离不足/越界拒绝。
                    return precise_distance
            except Exception as e:
                logger.info(f"【{self.pure_user_id}】JavaScript精确计算失败，使用后备方案: {e}")

            # 后备方案：使用bounding_box计算
            slide_distance = track_box["width"] - button_box["width"]

            if is_scratch:
                scratch_ratio = random.uniform(0.25, 0.35)
                slide_distance = slide_distance * scratch_ratio
                logger.warning(f"【{self.pure_user_id}】🎨 刮刮乐模式：滑动{scratch_ratio*100:.1f}%距离 ({slide_distance:.2f}px)")
            logger.info(f"【{self.pure_user_id}】计算滑动距离: {slide_distance:.2f}px")
            return slide_distance

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】计算滑动距离时出错: {str(e)}")
            return 0

    def check_verification_success_fast(
        self,
        slider_button: ElementHandle,
        max_confirm_wait: Optional[float] = None,
    ) -> bool:
        """严格判定本次滑动是否真正通过风控

        判定流程：
        1. 容器消失 / Frame 已 detach（必要但不充分条件）
        2. 当前主页 URL 不在 punish/x5step=2/pureCaptcha 路径上
        3. x5sec 已被新下发（旧值变化 / 从无到有）

        Args:
            slider_button: 滑块按钮元素
            max_confirm_wait: 二次确认（等待 x5sec 落盘）的最长等待秒数。
                由上层按"距浏览器超时的剩余预算"传入，避免二次确认等待过久
                被超时守护强杀；为 None 时使用 _confirm_success_after_visual
                的默认值。

        Returns:
            True 真正验证通过；False 视觉通过但风控未放行 / 不明确
        """
        try:
            logger.info(f"【{self.pure_user_id}】检查验证结果（严格模式）...")

            # 确定滑块所在的frame
            target_frame = None
            if self._detected_slider_frame is not None:
                target_frame = self._detected_slider_frame
                logger.info(f"【{self.pure_user_id}】在已知Frame中检查验证结果")
                try:
                    _ = target_frame.url if hasattr(target_frame, 'url') else None
                except Exception as frame_check_error:
                    error_msg = str(frame_check_error).lower()
                    if 'detached' in error_msg or 'disconnected' in error_msg:
                        logger.info(f"【{self.pure_user_id}】✓ Frame已被分离，进入二次确认")
                        return self._confirm_success_after_visual(max_confirm_wait)
            else:
                target_frame = self.page
                logger.info(f"【{self.pure_user_id}】在主页面检查验证结果")

            # 等待验证结果出现
            time.sleep(0.3)

            # 检查容器状态
            container_exists, container_visible = self._check_container_status(target_frame)

            if not container_exists or not container_visible:
                logger.info(f"【{self.pure_user_id}】✓ 滑块容器已消失，进入二次确认")
                return self._confirm_success_after_visual(max_confirm_wait)

            # 容器还在，等待更长时间
            logger.info(f"【{self.pure_user_id}】滑块容器仍存在，等待验证结果...")
            time.sleep(1.2)

            # 再次检查容器状态
            container_exists, container_visible = self._check_container_status(target_frame)

            if not container_exists or not container_visible:
                logger.info(f"【{self.pure_user_id}】✓ 滑块容器已消失，进入二次确认")
                return self._confirm_success_after_visual(max_confirm_wait)

            # 检查成功标志
            for selector in self.SUCCESS_SELECTORS:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        logger.info(f"【{self.pure_user_id}】✓ 检测到成功标志: {selector}")
                        return self._confirm_success_after_visual(max_confirm_wait)
                except Exception:
                    continue

            # 检查滑块是否消失
            try:
                slider = self.page.query_selector("#nc_1_n1z")
                if not slider or not slider.is_visible():
                    logger.info(f"【{self.pure_user_id}】✓ 滑块按钮消失，进入二次确认")
                    return self._confirm_success_after_visual(max_confirm_wait)
            except Exception:
                pass

            logger.warning(f"【{self.pure_user_id}】验证结果不明确")
            return False

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】检查验证结果时出错: {e}")
            return False

    def _confirm_success_after_visual(self, max_confirm_wait: Optional[float] = None) -> bool:
        """视觉通过后再做一次"风控真通过"二次确认

        判定以"是否已新下发 x5sec"为唯一充分条件，与最终取 cookie 阶段
        （_get_cookies_after_success 要求 cookie 必须含 x5sec）保持语义一致，
        避免"视觉像过了但风控未真正放行"的假阳性提前结束重试：

        - 在等待窗口内每 0.3 秒轮询一次（给 x5sec 经 Service Worker 异步写入留时间）
        - 任一时刻满足 URL 不在 punish 且 x5sec 已新下发 → 立即返回 True
        - 超时后仍在 punish/x5step=2/pureCaptcha → 返回 False（肯定没过）
        - 超时后 URL 已离开 punish 但整个窗口内从未见到新 x5sec → 返回 False
          （宁可判失败让上层继续重试，也不放过无 x5sec 的假通过）

        Args:
            max_confirm_wait: 最长等待秒数。由上层按"距浏览器超时的剩余预算"
                传入，避免固定长等待被超时守护强杀；为 None 时用默认 3 秒。
                下限保护为 1 秒，确保 x5sec 至少有一点异步写入时间。
        """
        # 等待窗口自适应：默认 3 秒；上层传入剩余预算时按预算走，但不低于 1 秒。
        # x5sec 常经 Service Worker 异步写入，窗口过短（历史上为 2 秒）会等不到
        # 落盘而误判为未下发；窗口过长又会被浏览器超时守护强杀，故由上层按剩余
        # 预算动态给定最稳妥。
        if max_confirm_wait is None:
            max_wait = 3.0
        else:
            max_wait = max(1.0, float(max_confirm_wait))
        interval = 0.3
        waited = 0.0
        last_url = ""
        x5sec_seen_new = False

        while waited < max_wait:
            time.sleep(interval)
            waited += interval

            try:
                last_url = self.page.url or ""
            except Exception:
                last_url = ""

            in_punish = self._is_punish_url(last_url)
            cookies = self._read_current_cookies()
            current_x5sec = cookies.get("x5sec") or ""
            if current_x5sec and current_x5sec != (self._pre_x5sec_value or ""):
                x5sec_seen_new = True

            logger.info(
                f"【{self.pure_user_id}】二次确认 t={waited:.1f}s: "
                f"in_punish={in_punish}, x5sec_new={x5sec_seen_new}, url={last_url[:120]}"
            )

            if not in_punish and x5sec_seen_new:
                logger.info(
                    f"【{self.pure_user_id}】✅ 真通过：URL离开punish + x5sec已新下发"
                )
                return True

        # 超时后仍在 punish：肯定没过
        if self._is_punish_url(last_url):
            logger.warning(
                f"【{self.pure_user_id}】❌ 视觉通过但风控未放行，URL 仍在 punish: {last_url[:120]}"
            )
            return False

        # URL 已离开 punish，且窗口内确实见到新 x5sec：真通过
        if x5sec_seen_new:
            logger.info(f"【{self.pure_user_id}】✅ 真通过：x5sec 已新下发")
            return True

        # URL 离开了 punish 但整个窗口内从未下发新 x5sec：判失败。
        # 最终取 cookie 阶段同样要求必须含 x5sec，这里提前判失败可让
        # 上层继续重试，而非因假阳性提前结束、白白耗掉一次重试机会。
        logger.warning(
            f"【{self.pure_user_id}】❌ URL 已离开 punish 但始终未下发新 x5sec"
            f"（{last_url[:120]}），判定未通过，交由上层重试"
        )
        return False

    def _check_container_status(self, target_frame: Any) -> Tuple[bool, bool]:
        """检查容器状态

        Returns:
            (存在, 可见)
        """
        try:
            if target_frame == self.page:
                container = self.page.query_selector(".nc-container")
            else:
                try:
                    _ = target_frame.url if hasattr(target_frame, 'url') else None
                    container = target_frame.query_selector(".nc-container")
                except Exception as frame_error:
                    error_msg = str(frame_error).lower()
                    if 'detached' in error_msg or 'disconnected' in error_msg:
                        logger.info(f"【{self.pure_user_id}】Frame已被分离，容器不存在")
                        return (False, False)
                    raise frame_error

            if container is None:
                return (False, False)

            try:
                is_visible = container.is_visible()
                return (True, is_visible)
            except Exception as vis_error:
                vis_error_msg = str(vis_error).lower()
                if 'detached' in vis_error_msg or 'disconnected' in vis_error_msg:
                    return (False, False)
                return (True, True)
        except Exception as e:
            error_msg = str(e).lower()
            if 'detached' in error_msg or 'disconnected' in error_msg:
                return (False, False)
            logger.warning(f"【{self.pure_user_id}】检查容器状态时出错: {e}")
            return (True, True)
