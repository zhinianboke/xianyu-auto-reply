"""
商品搜索服务

基于Playwright实现闲鱼商品搜索
复刻原始 utils/item_search.py 的逻辑
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from app.services.search.browser import BrowserManager, PLAYWRIGHT_AVAILABLE
from app.services.search.parser import ItemParser
from app.services.search.slider_handler import SliderHandler


class ItemSearchService:
    """商品搜索服务"""

    # 搜索相关选择器
    SEARCH_INPUT_SELECTORS = [
        'input[class*="search-input"]',
        'input[placeholder*="搜索"]',
        'input[type="text"]',
        '.search-input',
        '#search-input'
    ]

    NEXT_PAGE_SELECTORS = [
        '.search-page-tiny-arrow-right--oXVFaRao',
        '[class*="search-page-tiny-arrow-right"]',
        'button[aria-label="下一页"]',
        'button:has-text("下一页")',
        'a:has-text("下一页")',
        '.ant-pagination-next',
        'li.ant-pagination-next a',
        'a[aria-label="下一页"]'
    ]

    def __init__(self, db_session: Optional[AsyncSession] = None, user_id: str = "default"):
        """
        初始化搜索服务
        
        Args:
            db_session: 异步数据库会话（可选，用于获取Cookie）
            user_id: 用户ID，用于滑块验证会话
        """
        self.db_session = db_session
        self.user_id = user_id
        self.browser = BrowserManager()
        self.parser = ItemParser()
        self.slider_handler = SliderHandler(user_id)
        self.api_responses: List[Dict] = []
        self.data_list: List[Dict] = []

    async def get_first_valid_cookie(self) -> Optional[Dict[str, str]]:
        """获取第一个有效的cookie"""
        if not self.db_session:
            logger.error("数据库会话未初始化")
            return None

        try:
            conditions = [XYAccount.status == "active"]
            # 尽量只使用当前登录用户自己的账号 Cookie（避免跨用户取到别人的 Cookie）
            if isinstance(self.user_id, str) and self.user_id.isdigit():
                conditions.append(XYAccount.owner_id == int(self.user_id))

            stmt = select(XYAccount).where(*conditions).limit(1)
            result = await self.db_session.execute(stmt)
            account = result.scalars().first()

            if account and account.cookie and len(account.cookie) > 50:
                logger.info(f"找到有效cookie: {account.account_id}")
                return {
                    'id': account.account_id,
                    'value': account.cookie
                }

            return None

        except Exception as e:
            logger.error(f"获取cookie失败: {str(e)}")
            return None

    async def _on_response(self, response):
        """处理API响应"""
        if "h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search" in response.url:
            try:
                if response.status != 200:
                    logger.warning(f"API响应状态异常: {response.status}")
                    return

                try:
                    result_json = await response.json()
                except Exception:
                    logger.warning("无法解析响应JSON")
                    return

                self.api_responses.append(result_json)
                logger.info(f"捕获到API响应")

                items = result_json.get("data", {}).get("resultList", [])
                logger.info(f"从API获取到 {len(items)} 条原始数据")

                parsed_items = await self.parser.parse_items_batch(items)
                self.data_list.extend(parsed_items)

            except Exception as e:
                logger.warning(f"响应处理异常: {str(e)}")

    async def search_items(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        搜索闲鱼商品
        
        Args:
            keyword: 搜索关键词
            page: 页码，从1开始
            page_size: 每页数量
            
        Returns:
            搜索结果字典
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright 不可用")
            return {'items': [], 'total': 0, 'error': 'Playwright 不可用'}

        logger.info(f"搜索闲鱼商品: 关键词='{keyword}', 页码={page}")

        try:
            await self.browser.init_browser()
            self.api_responses = []
            self.data_list = []

            # 获取并设置cookies
            cookie_data = await self.get_first_valid_cookie()
            if not cookie_data:
                raise Exception("未找到有效的cookies账户")

            logger.info(f"使用账户: {cookie_data.get('id', 'unknown')}")

            # 访问闲鱼首页
            await self.browser.navigate_to("https://www.goofish.com")
            await self.browser.set_cookies(cookie_data.get('value', ''))

            # 刷新页面应用cookies
            if self.browser.page:
                await self.browser.page.reload()
                await asyncio.sleep(2)

            await self.browser.wait_for_network_idle(timeout=10000)

            # 搜索
            logger.info(f"正在搜索关键词: {keyword}")
            search_input = await self._find_search_input()
            if not search_input:
                raise Exception("未找到搜索框元素")

            await search_input.fill(keyword)

            # 注册响应监听
            self.browser.on_response(self._on_response)

            await self.browser.click('button[type="submit"]')
            await self.browser.wait_for_network_idle(timeout=15000)

            # 等待API响应
            await asyncio.sleep(2)

            # 处理弹窗
            try:
                await self.browser.press_key('Escape')
                await asyncio.sleep(0.5)
            except Exception:
                pass

            # 处理滑块验证
            slider_result = await self.slider_handler.handle_verification(
                page=self.browser.page,
                context=self.browser.context,
                max_retries=5
            )

            if not slider_result:
                logger.error("❌ 滑块验证失败")
                return {'items': [], 'total': 0, 'error': '滑块验证失败'}

            await asyncio.sleep(3)

            # 如果需要翻页
            if page > 1:
                self.data_list.clear()
                await self._navigate_to_page(page)

            # 排序
            sorted_items = self.parser.sort_by_want_count(self.data_list)

            logger.info(f"搜索完成，获取到 {len(sorted_items)} 条数据")

            return {
                'items': sorted_items,
                'total': len(sorted_items),
                'is_real_data': True,
                'source': 'playwright'
            }

        except Exception as e:
            error_msg = self._format_error_message(str(e))
            logger.error(f"搜索失败: {error_msg}")
            return {'items': [], 'total': 0, 'error': f'搜索失败: {error_msg}'}

        finally:
            await self.browser.close_browser()

    async def search_multiple_pages(
        self,
        keyword: str,
        total_pages: int = 1
    ) -> Dict[str, Any]:
        """
        搜索多页闲鱼商品
        
        Args:
            keyword: 搜索关键词
            total_pages: 总页数
            
        Returns:
            搜索结果字典
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {'items': [], 'total': 0, 'error': 'Playwright 不可用'}

        logger.info(f"多页搜索: 关键词='{keyword}', 总页数={total_pages}")

        try:
            await self.browser.init_browser()
            self.api_responses = []
            self.data_list = []

            # 获取并设置cookies
            cookie_data = await self.get_first_valid_cookie()
            if not cookie_data:
                raise Exception("未找到有效的cookies账户")

            # 访问闲鱼首页
            await self.browser.navigate_to("https://www.goofish.com")
            await self.browser.set_cookies(cookie_data.get('value', ''))

            if self.browser.page:
                await self.browser.page.reload()
                await asyncio.sleep(2)

            await self.browser.wait_for_network_idle(timeout=15000)

            # 搜索
            search_input = await self._find_search_input()
            if not search_input:
                raise Exception("未找到搜索框元素")

            await search_input.fill(keyword)
            self.browser.on_response(self._on_response)

            await self.browser.click('button[type="submit"]')
            await self.browser.wait_for_network_idle(timeout=15000)

            await asyncio.sleep(3)

            # 处理弹窗和滑块
            try:
                await self.browser.press_key('Escape')
            except Exception:
                pass

            slider_result = await self.slider_handler.handle_verification(
                page=self.browser.page,
                context=self.browser.context,
                max_retries=5
            )

            if not slider_result:
                return {'items': [], 'total': 0, 'error': '滑块验证失败'}

            await asyncio.sleep(3)

            first_page_count = len(self.data_list)
            logger.info(f"第1页完成，获取到 {first_page_count} 条数据")

            # 获取更多页
            if total_pages > 1:
                for page_num in range(2, total_pages + 1):
                    success = await self._click_next_page(page_num)
                    if not success:
                        logger.warning(f"无法获取第 {page_num} 页，停止翻页")
                        break

            # 排序
            sorted_items = self.parser.sort_by_want_count(self.data_list)

            logger.info(f"多页搜索完成，共获取 {len(sorted_items)} 条数据")

            return {
                'items': sorted_items,
                'total': len(sorted_items),
                'is_real_data': True,
                'source': 'playwright'
            }

        except Exception as e:
            error_msg = self._format_error_message(str(e))
            logger.error(f"多页搜索失败: {error_msg}")
            return {'items': [], 'total': 0, 'error': f'搜索失败: {error_msg}'}

        finally:
            await self.browser.close_browser()

    async def _find_search_input(self):
        """查找搜索输入框"""
        if not self.browser.page:
            return None

        for selector in self.SEARCH_INPUT_SELECTORS:
            try:
                element = await self.browser.page.wait_for_selector(selector, timeout=5000)
                if element:
                    logger.info(f"✅ 找到搜索框: {selector}")
                    return element
            except Exception:
                continue

        return None

    async def _navigate_to_page(self, target_page: int):
        """导航到指定页面"""
        try:
            logger.info(f"正在导航到第 {target_page} 页...")
            await asyncio.sleep(2)

            for current_page in range(2, target_page + 1):
                success = await self._click_next_page(current_page)
                if not success:
                    break

        except Exception as e:
            logger.error(f"导航失败: {str(e)}")

    async def _click_next_page(self, page_num: int) -> bool:
        """点击下一页"""
        if not self.browser.page:
            return False

        logger.info(f"正在获取第 {page_num} 页...")
        await asyncio.sleep(2)

        before_count = len(self.data_list)

        for selector in self.NEXT_PAGE_SELECTORS:
            try:
                next_button = self.browser.page.locator(selector).first

                if await next_button.is_visible(timeout=3000):
                    is_disabled = await next_button.get_attribute("disabled")
                    has_disabled_class = await next_button.evaluate(
                        "el => el.classList.contains('ant-pagination-disabled') || el.classList.contains('disabled')"
                    )

                    if not is_disabled and not has_disabled_class:
                        await next_button.scroll_into_view_if_needed()
                        await asyncio.sleep(1)
                        await next_button.click()
                        await self.browser.wait_for_network_idle(timeout=15000)
                        await asyncio.sleep(5)

                        after_count = len(self.data_list)
                        new_items = after_count - before_count

                        if new_items > 0:
                            logger.info(f"第 {page_num} 页成功，新增 {new_items} 条数据")
                            return True
                        else:
                            logger.warning(f"第 {page_num} 页没有新数据")
                            return False

            except Exception:
                continue

        logger.warning(f"无法找到下一页按钮")
        return False

    def _format_error_message(self, error_msg: str) -> str:
        """格式化错误信息"""
        if "Executable doesn't exist" in error_msg or "playwright install" in error_msg:
            return "浏览器未安装。请运行: playwright install chromium"
        elif "BrowserType.launch" in error_msg:
            return "浏览器启动失败"
        elif "Target page, context or browser has been closed" in error_msg:
            return "浏览器页面被意外关闭"
        elif "Timeout" in error_msg:
            return "页面加载超时"
        return error_msg


# 便捷函数
async def search_xianyu_items(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    db_session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """搜索闲鱼商品的便捷函数"""
    max_retries = 2
    retry_delay = 5

    for attempt in range(max_retries + 1):
        try:
            service = ItemSearchService(db_session)
            logger.info(f"搜索尝试: {attempt + 1}/{max_retries + 1}")
            result = await service.search_items(keyword, page, page_size)

            if result.get('items') or not result.get('error'):
                return result

        except Exception as e:
            logger.error(f"搜索失败 (尝试 {attempt + 1}): {str(e)}")

            if attempt == max_retries:
                return {'items': [], 'total': 0, 'error': f"搜索失败: {str(e)}"}

            await asyncio.sleep(retry_delay)

    return {'items': [], 'total': 0, 'error': "未知错误"}


async def search_multiple_pages_xianyu(
    keyword: str,
    total_pages: int = 1,
    db_session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """搜索多页闲鱼商品的便捷函数"""
    try:
        service = ItemSearchService(db_session)
        return await service.search_multiple_pages(keyword, total_pages)
    except Exception as e:
        logger.error(f"多页搜索失败: {str(e)}")
        return {'items': [], 'total': 0, 'error': f"搜索失败: {str(e)}"}
