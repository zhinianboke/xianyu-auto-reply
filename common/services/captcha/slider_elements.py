"""
滑块元素查找器

负责在页面中查找滑块验证相关元素
复刻原始 utils/xianyu_slider_stealth.py 中的元素查找逻辑
"""
from __future__ import annotations

import time
from typing import Any, Optional, Tuple

from loguru import logger

try:
    from playwright.sync_api import Page, ElementHandle, Frame
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    ElementHandle = Any
    Frame = Any


class SliderElementFinder:
    """滑块元素查找器"""

    # 滑块容器选择器
    CONTAINER_SELECTORS = [
        "#nc_1_wrapper",
        ".nc-container",
        "#nocaptcha",
        ".nc_scale",
        "#nc_1__scale_text",
        ".nc-wrapper",
        "[class*='nc-container']",
        "[class*='nc_wrapper']",
        "[id*='nocaptcha']"
    ]

    # 滑块按钮选择器
    BUTTON_SELECTORS = [
        "#nc_1_n1z",
        ".nc_iconfont",
        ".btn_slide",
        "#scratch-captcha-btn",
        ".scratch-captcha-slider .button",
        "[class*='slider']",
        "[class*='btn']",
        "[role='button']"
    ]

    # 滑块轨道选择器
    TRACK_SELECTORS = [
        "#nc_1_n1t",
        ".nc_scale",
        ".nc_1_n1t",
        "[class*='track']",
        "[class*='scale']"
    ]

    def __init__(self, page: Page, user_id: str = "default"):
        """
        初始化元素查找器
        
        Args:
            page: Playwright页面对象
            user_id: 用户ID，用于日志标识
        """
        self.page = page
        self.user_id = user_id
        self.pure_user_id = self._extract_pure_user_id(user_id)
        self._detected_slider_frame: Optional[Frame] = None

    def _extract_pure_user_id(self, user_id: str) -> str:
        """提取纯用户ID"""
        if '_' in user_id:
            parts = user_id.split('_')
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) >= 10:
                return '_'.join(parts[:-1])
        return user_id

    def find_slider_elements(
        self, 
        fast_mode: bool = False
    ) -> Tuple[Optional[ElementHandle], Optional[ElementHandle], Optional[ElementHandle]]:
        """查找滑块元素（容器、按钮、轨道）
        
        Args:
            fast_mode: 是否使用快速模式（不等待）
            
        Returns:
            (容器元素, 按钮元素, 轨道元素)
        """
        try:
            slider_container = None
            slider_button = None
            slider_track = None
            found_frame: Optional[Any] = None

            # 快速等待页面稳定（快速模式下跳过）
            if not fast_mode:
                time.sleep(0.1)

            # ===== 【优化】优先在 frames 中快速查找最常见的滑块组合 =====
            # 根据实际日志，滑块按钮和轨道通常在同一个 frame 中
            # 按钮: #nc_1_n1z, 轨道: #nc_1_n1t
            logger.debug(f"【{self.pure_user_id}】优先在frames中快速查找常见滑块组合...")
            try:
                frames = self.page.frames
                for idx, frame in enumerate(frames):
                    try:
                        # 优先查找最常见的按钮选择器
                        button_element = frame.query_selector("#nc_1_n1z")
                        if button_element and button_element.is_visible():
                            # 在同一个 frame 中查找轨道
                            track_element = frame.query_selector("#nc_1_n1t")
                            if track_element and track_element.is_visible():
                                # 找到容器（可以用按钮或其他选择器）
                                container_element = frame.query_selector("#baxia-dialog-content")
                                if not container_element:
                                    container_element = frame.query_selector(".nc-container")
                                if not container_element:
                                    container_element = frame.query_selector("#nc_1_wrapper")
                                if not container_element:
                                    # 如果找不到容器，用按钮作为容器标识
                                    container_element = button_element
                                
                                logger.info(f"【{self.pure_user_id}】✅ 在Frame {idx} 快速找到完整滑块组合！")
                                logger.info(f"【{self.pure_user_id}】  - 按钮: #nc_1_n1z")
                                logger.info(f"【{self.pure_user_id}】  - 轨道: #nc_1_n1t")
                                
                                # 保存frame引用
                                self._detected_slider_frame = frame
                                return container_element, button_element, track_element
                    except Exception as e:
                        logger.debug(f"【{self.pure_user_id}】Frame {idx} 快速查找失败: {e}")
                        continue
            except Exception as e:
                logger.debug(f"【{self.pure_user_id}】frames 快速查找出错: {e}")

            # ===== 如果快速查找失败，使用原来的完整查找逻辑 =====
            logger.debug(f"【{self.pure_user_id}】快速查找未成功，使用完整查找逻辑...")

            # 如果已知滑块位置，优先在已知位置查找
            if hasattr(self, '_detected_slider_frame') and self._detected_slider_frame is not None:
                target_frame = self._detected_slider_frame
                logger.info(f"【{self.pure_user_id}】在已知Frame中查找滑块...")
                
                for selector in self.CONTAINER_SELECTORS:
                    try:
                        element = target_frame.query_selector(selector)
                        if element:
                            try:
                                if element.is_visible():
                                    logger.info(f"【{self.pure_user_id}】在已知Frame中找到滑块容器: {selector}")
                                    slider_container = element
                                    found_frame = target_frame
                                    break
                            except Exception:
                                logger.info(f"【{self.pure_user_id}】在已知Frame中找到滑块容器（无法检查可见性）: {selector}")
                                slider_container = element
                                found_frame = target_frame
                                break
                    except Exception:
                        continue
            elif hasattr(self, '_detected_slider_frame') and self._detected_slider_frame is None:
                # _detected_slider_frame 是 None，表示在主页面
                logger.info(f"【{self.pure_user_id}】已知滑块在主页面，直接在主页面查找...")
                for selector in self.CONTAINER_SELECTORS:
                    try:
                        element = self.page.wait_for_selector(selector, timeout=1000)
                        if element:
                            logger.info(f"【{self.pure_user_id}】在已知主页面找到滑块容器: {selector}")
                            slider_container = element
                            found_frame = self.page
                            break
                    except Exception:
                        continue

            # 如果已知位置中没找到，先尝试在主页面查找
            if not slider_container:
                for selector in self.CONTAINER_SELECTORS:
                    try:
                        element = self.page.wait_for_selector(selector, timeout=1000)
                        if element:
                            logger.info(f"【{self.pure_user_id}】在主页面找到滑块容器: {selector}")
                            slider_container = element
                            found_frame = self.page
                            break
                    except Exception:
                        continue

            # 如果主页面没找到，在所有frame中查找
            if not slider_container and self.page:
                try:
                    frames = self.page.frames
                    logger.info(f"【{self.pure_user_id}】主页面未找到滑块，开始在所有frame中查找（共{len(frames)}个frame）...")
                    for idx, frame in enumerate(frames):
                        try:
                            for selector in self.CONTAINER_SELECTORS:
                                try:
                                    element = frame.query_selector(selector)
                                    if element:
                                        try:
                                            if element.is_visible():
                                                logger.info(f"【{self.pure_user_id}】在Frame {idx} 找到滑块容器: {selector}")
                                                slider_container = element
                                                found_frame = frame
                                                break
                                        except Exception:
                                            logger.info(f"【{self.pure_user_id}】在Frame {idx} 找到滑块容器（无法检查可见性）: {selector}")
                                            slider_container = element
                                            found_frame = frame
                                            break
                                except Exception:
                                    continue
                            if slider_container:
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not slider_container:
                logger.error(f"【{self.pure_user_id}】未找到任何滑块容器")
                return None, None, None

            # 查找滑块按钮
            slider_button = self._find_button(found_frame, fast_mode)
            if not slider_button:
                logger.error(f"【{self.pure_user_id}】未找到任何滑块按钮")
                return slider_container, None, None

            # 查找滑块轨道
            slider_track = self._find_track(found_frame, fast_mode)
            if not slider_track:
                logger.error(f"【{self.pure_user_id}】未找到任何滑块轨道")
                return slider_container, slider_button, None

            # 保存找到滑块的frame引用
            if found_frame and found_frame != self.page:
                self._detected_slider_frame = found_frame
                logger.info(f"【{self.pure_user_id}】保存滑块frame引用，供后续验证使用")
            elif found_frame == self.page:
                self._detected_slider_frame = None

            return slider_container, slider_button, slider_track

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】查找滑块元素时出错: {str(e)}")
            return None, None, None

    def _find_button(
        self, 
        found_frame: Optional[Any], 
        fast_mode: bool
    ) -> Optional[ElementHandle]:
        """查找滑块按钮"""
        search_frame = found_frame if found_frame and found_frame != self.page else self.page

        for selector in self.BUTTON_SELECTORS:
            try:
                element = None
                if fast_mode:
                    element = search_frame.query_selector(selector)
                else:
                    if search_frame == self.page:
                        element = self.page.wait_for_selector(selector, timeout=3000)
                    else:
                        try:
                            element = search_frame.wait_for_selector(selector, timeout=3000)
                        except Exception:
                            time.sleep(0.5)
                            element = search_frame.query_selector(selector)

                if element:
                    try:
                        is_visible = element.is_visible()
                        if not is_visible:
                            element = None
                    except Exception:
                        pass

                if element:
                    frame_info = "主页面" if search_frame == self.page else "Frame"
                    logger.info(f"【{self.pure_user_id}】在{frame_info}找到滑块按钮: {selector}")
                    return element
            except Exception:
                continue

        return None

    def _find_track(
        self, 
        found_frame: Optional[Any], 
        fast_mode: bool
    ) -> Optional[ElementHandle]:
        """查找滑块轨道"""
        track_search_frame = found_frame if found_frame and found_frame != self.page else self.page

        for selector in self.TRACK_SELECTORS:
            try:
                element = None
                if fast_mode:
                    element = track_search_frame.query_selector(selector)
                else:
                    if track_search_frame == self.page:
                        element = self.page.wait_for_selector(selector, timeout=3000)
                    else:
                        element = track_search_frame.query_selector(selector)

                if element:
                    try:
                        if not element.is_visible():
                            element = None
                    except Exception:
                        pass

                if element:
                    frame_info = "主页面" if track_search_frame == self.page else "Frame"
                    logger.info(f"【{self.pure_user_id}】在{frame_info}找到滑块轨道: {selector}")
                    return element
            except Exception:
                continue

        return None

    def get_detected_frame(self) -> Optional[Frame]:
        """获取检测到的滑块frame"""
        return self._detected_slider_frame

    def set_detected_frame(self, frame: Optional[Frame]):
        """设置检测到的滑块frame"""
        self._detected_slider_frame = frame

