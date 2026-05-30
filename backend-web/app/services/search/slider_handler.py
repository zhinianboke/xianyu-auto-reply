"""
滑块验证处理器

处理闲鱼搜索时的滑块验证（刮刮乐类型）
"""
from __future__ import annotations

import asyncio
import os
import random
import socket
from typing import Any, Optional

from loguru import logger

try:
    from playwright.async_api import Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    BrowserContext = Any


class SliderHandler:
    """滑块验证处理器"""

    # 滑块选择器列表
    SLIDER_SELECTORS = [
        # 阿里云盾 nc 系列滑块
        '#nc_1_n1z', '.nc-container', '.nc_scale', '.nc-wrapper',
        '[class*="nc_"]', '[id*="nc_"]',
        # 刮刮乐 (scratch-captcha) 类型滑块
        '#nocaptcha', '.scratch-captcha-container', '.scratch-captcha-slider',
        '#scratch-captcha-btn', '[class*="scratch-captcha"]',
        'div[id="nocaptcha"]', 'div.scratch-captcha-container',
        # 其他常见滑块类型
        '.captcha-slider', '.slider-captcha',
        '[class*="captcha"]', '[id*="captcha"]'
    ]

    # 刮刮乐按钮选择器
    SCRATCH_BUTTON_SELECTORS = [
        '#scratch-captcha-btn', '.button#scratch-captcha-btn',
        'div#scratch-captcha-btn', '.scratch-captcha-slider .button',
        '#nocaptcha .button', '#nocaptcha .scratch-captcha-slider .button',
        '.button'
    ]

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id

    async def detect_slider(self, page: Page) -> tuple[bool, Optional[str]]:
        """检测页面是否有滑块验证"""
        try:
            # 检查页面HTML中是否包含滑块关键词
            page_content = await page.content()
            has_captcha_keyword = any(
                keyword in page_content.lower()
                for keyword in ['nocaptcha', 'scratch-captcha', 'captcha', 'slider', '滑块', '验证']
            )

            if has_captcha_keyword:
                logger.warning("⚠️ 页面HTML中包含滑块相关关键词")

            # 检测滑块元素
            found_elements = []
            for selector in self.SLIDER_SELECTORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        found_elements.append(selector)
                        is_visible = await element.is_visible()
                        if is_visible:
                            logger.info(f"✅ 检测到滑块验证元素: {selector}")
                            return True, selector
                except Exception:
                    continue

            # 检查iframe中的滑块
            if not found_elements:
                try:
                    frames = page.frames
                    for frame in frames:
                        if frame != page.main_frame:
                            try:
                                iframe_content = await frame.content()
                                has_scratch = 'scratch-captcha' in iframe_content or \
                                             ('nocaptcha' in iframe_content and 'scratch' in iframe_content)
                                if has_scratch:
                                    logger.warning("🎯 在iframe中检测到刮刮乐滑块！")
                                    return True, "iframe-scratch-captcha"
                            except Exception:
                                continue
                except Exception as e:
                    logger.debug(f"检查iframe时出错: {e}")

            # 如果找到元素但不可见，仍然尝试处理
            if found_elements:
                logger.warning(f"🔍 找到滑块元素（可能不可见）: {', '.join(found_elements)}")
                return True, found_elements[0]

            return False, None

        except Exception as e:
            logger.error(f"检测滑块时出错: {e}")
            return False, None

    def _is_scratch_captcha(self, selector: str, page_html: str = "") -> bool:
        """判断是否为刮刮乐类型滑块"""
        if 'scratch' in selector.lower():
            return True

        if selector in ['#nocaptcha', 'iframe-scratch-captcha']:
            has_scratch_features = (
                'scratch-captcha' in page_html or
                'Release the slider' in page_html or
                'fully appears' in page_html
            )
            return has_scratch_features

        return False

    async def handle_scratch_captcha_manual(
        self,
        page: Page,
        max_retries: int = 3,
        wait_for_completion: bool = True
    ) -> bool | str:
        """人工处理刮刮乐滑块（远程控制）"""
        logger.warning("=" * 60)
        logger.warning("🎨 检测到刮刮乐验证，需要人工处理！")
        logger.warning("=" * 60)

        try:
            from app.utils.captcha_remote_control import captcha_controller

            # 创建远程控制会话
            logger.warning(f"🌐 启动远程控制会话: {self.user_id}")
            await captcha_controller.create_session(self.user_id, page)

            # 获取控制页面URL
            local_ip = self._get_server_ip()
            control_url = f"http://{local_ip}:8000/api/captcha/control/{self.user_id}"

            logger.warning("=" * 60)
            logger.warning(f"🌐 远程控制已启动！")
            logger.warning(f"📱 请访问以下网址进行验证：")
            logger.warning(f"   {control_url}")
            logger.warning("=" * 60)

            if not wait_for_completion:
                logger.warning("⚠️ 不等待验证完成，立即返回给前端处理")
                return 'need_captcha'

            # 等待用户完成验证
            logger.warning("⏳ 等待用户通过网页完成验证...")
            max_wait_time = 90
            check_interval = 1
            elapsed_time = 0

            while elapsed_time < max_wait_time:
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval

                if captcha_controller.is_completed(self.user_id):
                    logger.success("✅ 远程验证成功！")
                    await captcha_controller.close_session(self.user_id)
                    return True

                if elapsed_time % 10 == 0:
                    logger.info(f"⏳ 仍在等待...已等待 {elapsed_time} 秒")

            logger.error(f"❌ 远程验证超时（{max_wait_time}秒）")
            await captcha_controller.close_session(self.user_id)
            return False

        except Exception as e:
            logger.error(f"远程控制启动失败: {e}")
            return False

    def _get_server_ip(self) -> str:
        """获取服务器IP"""
        local_ip = os.getenv('SERVER_HOST') or os.getenv('PUBLIC_IP')

        if not local_ip:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()

                if local_ip.startswith('172.') or local_ip.startswith('10.'):
                    logger.warning(f"⚠️ 检测到Docker内网IP: {local_ip}")
                    local_ip = None
            except Exception:
                pass

        if not local_ip:
            local_ip = "localhost"
            logger.warning("⚠️ 无法获取外网IP，使用 localhost")

        return local_ip

    async def handle_scratch_captcha_auto(
        self,
        page: Page,
        max_retries: int = 15
    ) -> bool:
        """自动处理刮刮乐滑块（模拟滑动）"""
        original_page = page

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🎨 刮刮乐滑块处理尝试 {attempt}/{max_retries}")
                page = original_page

                if attempt == 1:
                    await asyncio.sleep(0.3)
                else:
                    await asyncio.sleep(0.5)

                # 查找滑块按钮
                slider_button = await self._find_slider_button(page)
                if not slider_button:
                    logger.error("❌ 未找到刮刮乐滑块按钮")
                    await asyncio.sleep(random.uniform(0.5, 1))
                    continue

                # 获取按钮位置
                button_box = await slider_button.bounding_box()
                if not button_box:
                    button_box = await self._get_button_box_by_js(page)
                    if not button_box:
                        logger.error("❌ 无法获取滑块按钮位置")
                        continue

                # 执行滑动
                success = await self._perform_slide(page, button_box)
                if success:
                    # 检查是否成功
                    await asyncio.sleep(0.8)
                    if await self._check_captcha_passed(page):
                        logger.success(f"✅ 刮刮乐验证成功！（第{attempt}次尝试）")
                        return True

            except Exception as e:
                logger.error(f"❌ 刮刮乐处理异常: {str(e)}")
                await asyncio.sleep(random.uniform(0.5, 1))

        logger.error(f"❌ 刮刮乐验证失败，已达到最大重试次数 {max_retries}")
        return False

    async def _find_slider_button(self, page: Page):
        """查找滑块按钮"""
        for selector in self.SCRATCH_BUTTON_SELECTORS:
            try:
                button = await page.wait_for_selector(selector, timeout=800, state='visible')
                if button:
                    logger.info(f"✅ 找到刮刮乐滑块按钮: {selector}")
                    return button
            except Exception:
                try:
                    button = await page.wait_for_selector(selector, timeout=300, state='attached')
                    if button:
                        return button
                except Exception:
                    continue

        # 尝试在iframe中查找
        try:
            frames = page.frames
            for frame in frames:
                if frame == page.main_frame:
                    continue
                for selector in self.SCRATCH_BUTTON_SELECTORS:
                    try:
                        button = await frame.wait_for_selector(selector, timeout=500, state='visible')
                        if button:
                            logger.info(f"✅ 在iframe中找到滑块按钮: {selector}")
                            return button
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    async def _get_button_box_by_js(self, page: Page) -> Optional[dict]:
        """通过JavaScript获取按钮位置"""
        try:
            js_box = await page.evaluate("""
                () => {
                    const btn = document.getElementById('scratch-captcha-btn');
                    if (btn) {
                        const rect = btn.getBoundingClientRect();
                        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                    }
                    return null;
                }
            """)
            if js_box:
                logger.info(f"✅ JavaScript获取到按钮位置: {js_box}")
            return js_box
        except Exception:
            return None

    async def _perform_slide(self, page: Page, button_box: dict) -> bool:
        """执行滑动操作"""
        try:
            # 计算滑动距离（25-35%）
            estimated_track_width = 300
            scratch_ratio = random.uniform(0.25, 0.35)
            slide_distance = estimated_track_width * scratch_ratio

            logger.warning(f"🎨 刮刮乐模式：计划滑动{scratch_ratio*100:.1f}%距离 ({slide_distance:.2f}px)")

            start_x = button_box['x'] + button_box['width'] / 2
            start_y = button_box['y'] + button_box['height'] / 2

            # 移动到滑块
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(random.uniform(0.1, 0.2))

            # 按下鼠标
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.1))

            # 模拟人类化滑动轨迹
            steps = random.randint(10, 15)
            for i in range(steps):
                progress = (i + 1) / steps
                current_distance = slide_distance * progress
                y_jitter = random.uniform(-2, 2)

                await page.mouse.move(start_x + current_distance, start_y + y_jitter)
                await asyncio.sleep(random.uniform(0.005, 0.015))

            # 停顿观察
            await asyncio.sleep(random.uniform(0.2, 0.3))

            # 释放鼠标
            await page.mouse.up()
            await asyncio.sleep(random.uniform(0.3, 0.5))

            return True

        except Exception as e:
            logger.error(f"滑动操作失败: {e}")
            return False

    async def _check_captcha_passed(self, page: Page) -> bool:
        """检查验证是否通过"""
        try:
            # 检查主页面的滑块容器
            captcha_in_main = await page.query_selector('#nocaptcha')
            main_visible = False
            if captcha_in_main:
                try:
                    main_visible = await captcha_in_main.is_visible()
                except Exception:
                    pass

            # 检查iframe中的滑块
            iframe_visible = False
            try:
                for frame in page.frames:
                    if frame != page.main_frame:
                        captcha_in_iframe = await frame.query_selector('#nocaptcha')
                        if captcha_in_iframe:
                            try:
                                if await captcha_in_iframe.is_visible():
                                    iframe_visible = True
                                    break
                            except Exception:
                                pass
            except Exception:
                pass

            return not main_visible and not iframe_visible

        except Exception as e:
            logger.warning(f"检查验证结果时出错: {e}")
            return False

    async def handle_verification(
        self,
        page: Page,
        context: Optional[BrowserContext] = None,
        max_retries: int = 5,
        allow_manual: bool = True,
    ) -> bool:
        """通用滑块验证处理入口"""
        try:
            await asyncio.sleep(1)
            logger.info("🔍 开始检测滑块验证...")

            has_slider, detected_selector = await self.detect_slider(page)

            if not has_slider:
                logger.info("✅ 未检测到滑块验证，继续执行")
                return True

            logger.warning(f"⚠️ 检测到滑块验证（{detected_selector}），开始处理...")

            # 判断滑块类型
            page_html = await page.content()
            is_scratch = self._is_scratch_captcha(detected_selector, page_html)

            if is_scratch:
                logger.warning("🎨 检测到刮刮乐类型滑块，优先尝试自动处理")
                auto_ok = await self.handle_scratch_captcha_auto(page, max_retries=max_retries)
                if auto_ok:
                    logger.success("✅ 刮刮乐滑块自动处理成功！")
                    return True
                if not allow_manual:
                    logger.error("❌ 刮刮乐滑块自动处理失败（已禁用人工处理）")
                    return False
                logger.warning("🧑‍💻 刮刮乐滑块自动处理失败，进入人工处理流程")
                return await self.handle_scratch_captcha_manual(page, max_retries=3, wait_for_completion=True)
            else:
                # 普通滑块使用PlaywrightSliderService处理
                try:
                    from app.services.captcha import PlaywrightSliderService
                    slider_service = PlaywrightSliderService(
                        user_id=self.user_id,
                        enable_learning=True,
                        headless=True
                    )
                    slider_service.page = page
                    slider_service.context = context

                    success = slider_service.solve_slider(max_retries=max_retries)

                    slider_service.page = None
                    slider_service.context = None

                    if success:
                        logger.success("✅ 滑块验证成功！")
                        return True
                    else:
                        logger.error("❌ 滑块验证失败")
                        return False

                except ImportError:
                    logger.warning("PlaywrightSliderService不可用，尝试自动处理")
                    return await self.handle_scratch_captcha_auto(page, max_retries)

        except Exception as e:
            logger.error(f"❌ 滑块检测过程异常: {str(e)}")
            return False
