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

                    return precise_distance + random.uniform(-2.0, 2.0)
            except Exception as e:
                logger.info(f"【{self.pure_user_id}】JavaScript精确计算失败，使用后备方案: {e}")

            # 后备方案：使用bounding_box计算
            slide_distance = track_box["width"] - button_box["width"]

            if is_scratch:
                scratch_ratio = random.uniform(0.25, 0.35)
                slide_distance = slide_distance * scratch_ratio
                logger.warning(f"【{self.pure_user_id}】🎨 刮刮乐模式：滑动{scratch_ratio*100:.1f}%距离 ({slide_distance:.2f}px)")
            else:
                slide_distance += random.uniform(-0.5, 0.5)

            logger.info(f"【{self.pure_user_id}】计算滑动距离: {slide_distance:.2f}px")
            return slide_distance

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】计算滑动距离时出错: {str(e)}")
            return 0

    def check_verification_success_fast(self, slider_button: ElementHandle) -> bool:
        """严格判定本次滑动是否真正通过风控

        判定流程：
        1. 容器消失 / Frame 已 detach（必要但不充分条件）
        2. 当前主页 URL 不在 punish/x5step=2/pureCaptcha 路径上
        3. x5sec 已被新下发（旧值变化 / 从无到有）

        Args:
            slider_button: 滑块按钮元素

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
                        return self._confirm_success_after_visual()
            else:
                target_frame = self.page
                logger.info(f"【{self.pure_user_id}】在主页面检查验证结果")

            # 等待验证结果出现
            time.sleep(0.3)

            # 检查容器状态
            container_exists, container_visible = self._check_container_status(target_frame)

            if not container_exists or not container_visible:
                logger.info(f"【{self.pure_user_id}】✓ 滑块容器已消失，进入二次确认")
                return self._confirm_success_after_visual()

            # 容器还在，等待更长时间
            logger.info(f"【{self.pure_user_id}】滑块容器仍存在，等待验证结果...")
            time.sleep(1.2)

            # 再次检查容器状态
            container_exists, container_visible = self._check_container_status(target_frame)

            if not container_exists or not container_visible:
                logger.info(f"【{self.pure_user_id}】✓ 滑块容器已消失，进入二次确认")
                return self._confirm_success_after_visual()

            # 检查成功标志
            for selector in self.SUCCESS_SELECTORS:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        logger.info(f"【{self.pure_user_id}】✓ 检测到成功标志: {selector}")
                        return self._confirm_success_after_visual()
                except Exception:
                    continue

            # 检查滑块是否消失
            try:
                slider = self.page.query_selector("#nc_1_n1z")
                if not slider or not slider.is_visible():
                    logger.info(f"【{self.pure_user_id}】✓ 滑块按钮消失，进入二次确认")
                    return self._confirm_success_after_visual()
            except Exception:
                pass

            logger.warning(f"【{self.pure_user_id}】验证结果不明确")
            return False

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】检查验证结果时出错: {e}")
            return False

    def _confirm_success_after_visual(self) -> bool:
        """视觉通过后再做一次"风控真通过"二次确认

        - 最多等 8 秒，每 0.3 秒轮询一次
        - 任一时刻满足 URL 不在 punish 且 x5sec 已新下发 即返回 True
        - 若超时后 URL 仍在 x5step=2/punish/pureCaptcha 则返回 False
        - 若超时后 URL 离开了 punish 但 x5sec 未更新，也按 True 处理
          （部分场景下 x5sec 通过 Service Worker 异步写入，可能稍迟）
        """
        max_wait = 2.0
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

        # URL 已离开 punish，但 x5sec 没更新（可能 SW 异步写入），保守按通过
        if x5sec_seen_new:
            logger.info(f"【{self.pure_user_id}】✅ 真通过：x5sec 已新下发")
            return True

        logger.warning(
            f"【{self.pure_user_id}】⚠️  URL 已离开 punish 但 x5sec 未变更（{last_url[:120]}），按通过处理"
        )
        return True

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

    def check_success_simple(self) -> bool:
        """简单检查滑块验证是否成功（兜底方法）"""
        try:
            for selector in self.SUCCESS_SELECTORS:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return True
                except Exception:
                    continue

            slider = self.page.query_selector("#nc_1_n1z")
            if not slider or not slider.is_visible():
                return True

            return False
        except Exception:
            return False
