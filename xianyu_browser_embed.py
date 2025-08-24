#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
闲鱼浏览器界面嵌入模块
"""

import asyncio
import base64
import json
import time
from playwright.async_api import async_playwright
from typing import Optional, Dict, Any
from loguru import logger

class XianyuBrowserEmbed:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.websocket_connections = set()
        self.is_logged_in = False
        self.current_cookies = ""
        
    async def start_browser(self, headless: bool = False):
        """启动浏览器"""
        try:
            self.playwright = await async_playwright().start()
            
            # 启动Chromium浏览器
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=[
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
                ]
            )
            
            # 创建新页面
            self.page = await self.browser.new_page()
            
            # 设置视窗大小
            await self.page.set_viewport_size({"width": 1200, "height": 800})
            
            logger.info("浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            return False
    
    async def login_with_cookies(self, cookies_str: str):
        """使用Cookie登录闲鱼"""
        try:
            if not self.page:
                await self.start_browser()
            
            # 先访问闲鱼首页
            await self.page.goto("https://www.goofish.com")
            
            # 解析并设置Cookie
            cookies = []
            for cookie in cookies_str.split("; "):
                if "=" in cookie:
                    name, value = cookie.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".goofish.com",
                        "path": "/"
                    })
            
            # 添加Cookie到浏览器
            await self.page.context.add_cookies(cookies)
            
            # 刷新页面验证登录状态
            await self.page.reload()
            await self.page.wait_for_load_state('networkidle')
            
            # 检查是否登录成功
            try:
                # 查找用户头像或用户名元素
                user_element = await self.page.wait_for_selector(
                    '[data-testid="user-avatar"], .user-info, .login-user',
                    timeout=5000
                )
                if user_element:
                    self.is_logged_in = True
                    self.current_cookies = cookies_str
                    logger.info("Cookie登录成功")
                    return True
            except:
                pass
            
            logger.warning("Cookie登录失败或未检测到登录状态")
            return False
            
        except Exception as e:
            logger.error(f"Cookie登录异常: {e}")
            return False
    
    async def navigate_to_xianyu_page(self, page_type: str = "home"):
        """导航到闲鱼特定页面"""
        urls = {
            "home": "https://www.goofish.com",
            "publish": "https://www.goofish.com/publish",
            "messages": "https://www.goofish.com/messages",
            "my_items": "https://www.goofish.com/my/items",
            "orders": "https://www.goofish.com/my/orders"
        }
        
        url = urls.get(page_type, urls["home"])
        
        try:
            await self.page.goto(url)
            await self.page.wait_for_load_state('networkidle')
            logger.info(f"导航到闲鱼页面: {page_type}")
            return await self.capture_screenshot()
        except Exception as e:
            logger.error(f"导航到闲鱼页面失败: {e}")
            return None
    
    async def capture_screenshot(self, full_page: bool = False):
        """捕获页面截图"""
        if not self.page:
            return None
        
        try:
            screenshot_bytes = await self.page.screenshot(
                type='png',
                full_page=full_page
            )
            
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            return f"data:image/png;base64,{screenshot_base64}"
            
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None
    
    async def auto_publish_item(self, item_data: Dict[str, Any]):
        """自动发布商品"""
        try:
            # 导航到发布页面
            await self.navigate_to_xianyu_page("publish")
            
            # 填写商品标题
            if "title" in item_data:
                title_selector = 'input[placeholder*="标题"], input[name="title"]'
                await self.page.fill(title_selector, item_data["title"])
                logger.info(f"填写标题: {item_data['title']}")
            
            # 填写商品描述
            if "description" in item_data:
                desc_selector = 'textarea[placeholder*="描述"], textarea[name="description"]'
                await self.page.fill(desc_selector, item_data["description"])
                logger.info(f"填写描述: {item_data['description'][:50]}...")
            
            # 设置价格
            if "price" in item_data:
                price_selector = 'input[placeholder*="价格"], input[name="price"]'
                await self.page.fill(price_selector, str(item_data["price"]))
                logger.info(f"设置价格: {item_data['price']}")
            
            # 上传图片（如果有图片路径）
            if "images" in item_data and item_data["images"]:
                try:
                    file_input = await self.page.query_selector('input[type="file"]')
                    if file_input:
                        await file_input.set_input_files(item_data["images"])
                        logger.info(f"上传图片: {len(item_data['images'])} 张")
                except Exception as e:
                    logger.warning(f"上传图片失败: {e}")
            
            # 返回当前页面截图
            return await self.capture_screenshot()
            
        except Exception as e:
            logger.error(f"自动发布商品失败: {e}")
            return None
    
    async def get_messages(self):
        """获取消息列表"""
        try:
            await self.navigate_to_xianyu_page("messages")
            
            # 等待消息列表加载
            await self.page.wait_for_selector('.message-list, .chat-list', timeout=10000)
            
            # 提取消息数据
            messages = await self.page.evaluate("""
                () => {
                    const messageElements = document.querySelectorAll('.message-item, .chat-item');
                    return Array.from(messageElements).map(el => ({
                        sender: el.querySelector('.sender, .username')?.textContent?.trim() || '',
                        content: el.querySelector('.content, .message')?.textContent?.trim() || '',
                        time: el.querySelector('.time, .timestamp')?.textContent?.trim() || '',
                        unread: el.classList.contains('unread') || el.querySelector('.unread-badge')
                    }));
                }
            """)
            
            logger.info(f"获取到 {len(messages)} 条消息")
            return messages
            
        except Exception as e:
            logger.error(f"获取消息失败: {e}")
            return []
    
    async def send_message(self, chat_id: str, message: str):
        """发送消息"""
        try:
            # 这里需要根据实际的闲鱼界面结构来实现
            # 点击对应的聊天
            await self.page.click(f'[data-chat-id="{chat_id}"]')
            
            # 等待聊天界面加载
            await self.page.wait_for_selector('.message-input, .chat-input')
            
            # 输入消息
            await self.page.fill('.message-input, .chat-input', message)
            
            # 发送消息
            await self.page.click('.send-button, button[type="submit"]')
            
            logger.info(f"发送消息成功: {message[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def execute_custom_script(self, script: str):
        """执行自定义JavaScript脚本"""
        try:
            result = await self.page.evaluate(script)
            logger.info(f"执行脚本成功: {script[:100]}...")
            return result
        except Exception as e:
            logger.error(f"执行脚本失败: {e}")
            return None
    
    async def start_live_stream(self, interval: float = 1.0):
        """开始实时截图流"""
        while True:
            if self.page and self.websocket_connections:
                try:
                    screenshot = await self.capture_screenshot()
                    if screenshot:
                        message = {
                            "type": "screenshot",
                            "data": screenshot,
                            "timestamp": time.time(),
                            "logged_in": self.is_logged_in
                        }
                        
                        # 发送给所有连接的客户端
                        disconnected = set()
                        for ws in self.websocket_connections:
                            try:
                                await ws.send_text(json.dumps(message))
                            except:
                                disconnected.add(ws)
                        
                        # 移除断开的连接
                        self.websocket_connections -= disconnected
                
                except Exception as e:
                    logger.error(f"实时截图流异常: {e}")
            
            await asyncio.sleep(interval)
    
    async def close(self):
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器异常: {e}")

# 全局实例
xianyu_browser = XianyuBrowserEmbed()
