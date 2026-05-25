"""
返佣系统专用闲鱼发布器

功能：
1. 为返佣系统提供独立的闲鱼发布器实现
2. 使用 seller.goofish.com 卖家发布页面注入 Cookie 并发布商品
3. 默认使用无头模式发布商品
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any

from loguru import logger

from common.services.promotion_address_selector import set_promotion_item_address
from common.services.xianyu_publish_service import get_xianyu_publisher_class


BaseXianyuPublisher: type[Any] = get_xianyu_publisher_class()


class PromotionXianyuPublisher(BaseXianyuPublisher):
    """返佣系统专用闲鱼发布器。"""

    SELLER_HOME_URL = "https://seller.goofish.com"
    PROMOTION_PUBLISH_URL = (
        "https://seller.goofish.com/?site=COMMONPRO&spm=a21107h.42826273.0.0#/seller-item/publish"
    )

    async def _open_publish_page_with_cookie(self) -> None:
        """按旧逻辑在写入 Cookie 后进入返佣系统卖家发布页面。"""
        if not self.page:
            raise Exception("浏览器页面未初始化")

        logger.info("\n[准备] 🌐 先访问返佣卖家首页，触发 Cookie 初始化...")
        await self.page.goto(
            self.SELLER_HOME_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(1)

        logger.info("\n[准备] 🌐 访问登录页面...")
        await self.page.goto(
            "https://login.taobao.com/member/login.jhtml",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(1)

        logger.info(f"\n[步骤1] 🌐 访问返佣专用卖家发布页面: {self.PROMOTION_PUBLISH_URL}")
        await self.page.goto(
            self.PROMOTION_PUBLISH_URL,
            wait_until="networkidle",
            timeout=60000,
        )
        await asyncio.sleep(3)

    async def _set_item_address(self, item_data: dict):
        return await set_promotion_item_address(
            publisher=self,
            item_data=item_data,
            fallback_set_item_address=super()._set_item_address,
        )

    async def _fill_stock(self, item_data: dict) -> None:
        """填写库存（返佣卖家页专用）。"""
        if not self.page:
            raise Exception("浏览器页面未初始化")

        stock = int(item_data.get("stock", 999) or 999)
        if stock <= 0:
            stock = 999

        logger.info("\n[新增字段] 📦 输入库存...")
        logger.info(f"库存: {stock}")

        stock_selectors = [
            'input[placeholder*="库存"]',
            'input[aria-label*="库存"]',
            'input[placeholder*="数量"]',
            'input[aria-label*="数量"]',
            'input[name*="stock"]',
            'input[id*="stock"]',
            '[class*="stock"] input',
            '[class*="inventory"] input',
            'xpath=//*[contains(normalize-space(.), "库存")]/following::input[1]',
            'xpath=//*[contains(normalize-space(.), "数量")]/following::input[1]',
        ]

        stock_input = None
        for selector in stock_selectors:
            try:
                candidate = await self.page.wait_for_selector(selector, timeout=2000)
                if candidate and await candidate.is_visible() and await candidate.is_enabled():
                    stock_input = candidate
                    logger.info(f"✅ 找到库存输入框: {selector}")
                    break
            except Exception:
                continue

        if not stock_input:
            raise Exception("未找到库存输入框，无法填写素材库存")

        try:
            await stock_input.click()
            await asyncio.sleep(0.2)
        except Exception:
            pass

        try:
            await stock_input.fill("")
        except Exception:
            try:
                await stock_input.press("Control+A")
                await stock_input.press("Backspace")
            except Exception:
                pass

        await stock_input.fill(str(stock))
        logger.info("✅ 库存已输入")

    async def _dismiss_ant_modal(self) -> None:
        """检测页面是否存在 ant-modal-close 关闭按钮，如果有则点击关闭弹窗。"""
        if not self.page:
            return
        try:
            close_btn = await self.page.query_selector(".ant-modal-close")
            if close_btn and await close_btn.is_visible():
                logger.info("⚠️ 检测到 ant-modal 弹窗，自动关闭...")
                await close_btn.click()
                await asyncio.sleep(0.5)
                logger.info("✅ ant-modal 弹窗已关闭")
        except Exception:
            pass

    async def publish_item(
        self,
        item_data: dict,
        cookie_data: dict,
        reuse_browser: bool = False,
        should_close: bool = True,
    ) -> dict:
        """使用返佣系统专用卖家页面发布商品。"""
        result = {
            "success": False,
            "message": "",
            "item_url": None,
            "item_id": None,
            "screenshot": None,
        }

        try:
            logger.info("=" * 80)
            logger.info("📝 开始返佣专用发布商品")
            logger.info("=" * 80)
            logger.info(f"商品信息: {item_data.get('description', '')[:50]}...")
            logger.info(f"浏览器复用模式: {reuse_browser}")

            headless = True
            logger.info("🖥️ 使用无头模式发布")

            if reuse_browser and self.is_initialized and self.current_cookie == cookie_data["cookie"]:
                logger.info("🔄 复用现有浏览器，重新创建页面...")
                await self.reinitialize_page()
            else:
                await self.initialize(headless=headless)

            logger.info("\n[准备] 🍪 先写入返佣专用页面 Cookie...")
            await self.set_cookies(cookie_data["cookie"])

            await self._open_publish_page_with_cookie()

            current_url = self.page.url
            logger.info("✅ 页面已加载")
            logger.info(f"当前URL: {current_url}")

            if "login" in current_url or "auth" in current_url:
                raise Exception("Cookie已失效，页面跳转到登录页")

            page_title = await self.page.title()
            logger.info(f"页面标题: {page_title}")

            page_text = await self.page.evaluate("() => document.body.innerText")

            if "登录后可以" in page_text or ("立即登录" in page_text and "扫码登录" not in page_text):
                logger.error("Cookie已失效，页面内容包含未登录提示")
                raise Exception("Cookie已失效，页面显示未登录状态")

            if "添加首图" not in page_text and "宝贝图片" not in page_text:
                logger.info("⏳ 等待React渲染发布页面...")
                await asyncio.sleep(5)
                page_text = await self.page.evaluate("() => document.body.innerText")

                if "添加首图" not in page_text and "宝贝图片" not in page_text:
                    logger.error("页面可能不是发布页面，或者Cookie无效")
                    logger.error(f"页面内容: {page_text[:500]}")
                    raise Exception("页面可能不是发布页面，或者Cookie无效")

            screenshot = await self.page.screenshot(full_page=True)
            result["screenshot"] = base64.b64encode(screenshot).decode()

            logger.info("✅ 登录状态正常")
            logger.info("\n⏳ 等待React应用渲染表单元素...")
            try:
                initial_inputs = await self.page.query_selector_all("input")
                logger.info(f"   初始状态: 找到 {len(initial_inputs)} 个input元素")

                if len(initial_inputs) == 0:
                    logger.info("   React应用可能还在渲染，等待表单元素出现...")
                    await self.page.wait_for_selector("input, button, textarea", timeout=30000)
                    logger.info("   ✅ 表单元素已渲染")
                else:
                    logger.info("   ✅ 表单元素已存在")

                all_inputs = await self.page.query_selector_all("input")
                all_buttons = await self.page.query_selector_all("button")
                all_textareas = await self.page.query_selector_all("textarea")
                logger.info(
                    f"   验证结果: {len(all_inputs)} 个input, {len(all_buttons)} 个button, {len(all_textareas)} 个textarea"
                )

            except Exception as e:
                logger.warning(f"   方法1失败，尝试方法2: {e}")
                await self.page.wait_for_function(
                    """
                    () => {
                        const inputs = document.querySelectorAll('input, button, textarea');
                        return inputs.length > 0;
                    }
                    """,
                    timeout=30000,
                )
                logger.info("   ✅ 表单元素已渲染（通过JavaScript）")

                all_inputs = await self.page.query_selector_all("input")
                all_buttons = await self.page.query_selector_all("button")
                all_textareas = await self.page.query_selector_all("textarea")
                logger.info(
                    f"   验证结果: {len(all_inputs)} 个input, {len(all_buttons)} 个button, {len(all_textareas)} 个textarea"
                )

            logger.info("✅ React应用渲染完成")

            captcha_selectors = [".nc-container", "#nc_1_n1z", ".captcha-container"]
            has_captcha = False
            for selector in captcha_selectors:
                captcha = await self.page.query_selector(selector)
                if captcha:
                    logger.warning(f"\n⚠️ 检测到滑块验证: {selector}")
                    logger.warning("需要通过滑块验证才能继续")
                    has_captcha = True
                    break

            if has_captcha:
                logger.warning("提示：可以集成滑块验证工具来自动处理")

            await self._dismiss_ant_modal()
            logger.info("\n[步骤4] 📷 上传商品图片...")
            images = item_data.get("images", [])
            if not images:
                raise Exception("❌ 未提供商品图片，无法发布")

            logger.info(f"共有 {len(images)} 张图片需要上传")
            await self._upload_images(images)

            logger.info("\n[步骤5] ⏳ 等待图片上传和分类自动识别...")
            await asyncio.sleep(5)

            try:
                category_elements = await self.page.query_selector_all('[class*="category"], [class*="分类"]')
                if category_elements:
                    logger.info(f"✅ 检测到 {len(category_elements)} 个分类相关元素")
            except Exception:
                pass

            await self._dismiss_ant_modal()
            logger.info("\n[步骤6] 📝 填写宝贝描述...")
            await self._fill_description(item_data)

            logger.info("\n[步骤7] ⏳ 等待分类自动变化...")
            await asyncio.sleep(3)

            await self._dismiss_ant_modal()
            await self._select_category()

            logger.info("\n[步骤8] ⏭️ 跳过商品规格...")
            await asyncio.sleep(1)

            await self._dismiss_ant_modal()
            await self._fill_price(item_data)

            await self._dismiss_ant_modal()
            await self._fill_stock(item_data)

            logger.info("\n[步骤9] ⏭️ 跳过服务选择...")
            await asyncio.sleep(1)
            logger.info("\n[步骤10] ⏭️ 跳过服务选择...")
            await asyncio.sleep(1)
            logger.info("\n[步骤11] ⏭️ 跳过服务选择...")
            await asyncio.sleep(1)

            await self._dismiss_ant_modal()
            await self._set_free_shipping()

            await self._dismiss_ant_modal()
            await self._set_item_address(item_data)

            await self._dismiss_ant_modal()
            await self._click_publish_button(result)

            logger.info("\n" + "=" * 80)
            logger.info("📝 返佣专用发布流程完成")
            logger.info("=" * 80)
            await asyncio.sleep(3)

        except Exception as e:
            error_msg = f"发布失败: {str(e)}"
            result["message"] = error_msg
            logger.error(f"❌ {error_msg}")
            logger.error(f"错误详情: {type(e).__name__}: {str(e)}")

            if self.page:
                try:
                    screenshot = await self.page.screenshot(full_page=True)
                    result["screenshot"] = base64.b64encode(screenshot).decode()
                except Exception:
                    pass

        finally:
            if should_close:
                await self.close()

        return result
