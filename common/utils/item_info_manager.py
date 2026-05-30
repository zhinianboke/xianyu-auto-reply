"""
商品信息管理模块

提供商品信息的获取、保存等功能（不依赖 WebSocket）
"""
import asyncio
import json
import time
from typing import Optional, Dict, Any, List

from loguru import logger

from common.utils.text_utils import safe_str


class ItemInfoManager:
    """商品信息管理器
    
    管理商品信息的获取、保存等操作（纯 HTTP API 调用，不需要 WebSocket）
    """
    
    def __init__(self, cookie_id: str, cookies_str: str, session=None):
        """初始化商品信息管理器
        
        Args:
            cookie_id: 账号ID
            cookies_str: Cookie字符串
            session: aiohttp session（可选）
        """
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str
        self.cookies = self._parse_cookies(cookies_str)
        self.session = session
        self._own_session = False
    
    def _parse_cookies(self, cookies_str: str) -> dict:
        """解析Cookie字符串为字典"""
        from common.utils.xianyu_utils import trans_cookies
        return trans_cookies(cookies_str)
    
    def _safe_str(self, e) -> str:
        """安全地将异常转换为字符串（委托公共实现）"""
        return safe_str(e)
    
    def update_cookies(self, cookies_str: str):
        """更新Cookie"""
        self.cookies_str = cookies_str
        self.cookies = self._parse_cookies(cookies_str)
    
    async def _ensure_session(self):
        """确保session已创建
        
        参照旧框架backend/app/services/xianyu/xianyu_async.py的create_session方法
        """
        if not self.session:
            import aiohttp
            headers = {
                'accept': 'application/json',
                'accept-encoding': 'gzip, deflate, br',  # 排除zstd，aiohttp不支持
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://www.goofish.com',
                'pragma': 'no-cache',
                'referer': 'https://www.goofish.com/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'cookie': self.cookies_str
            }
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                connector=connector
            )
            self._own_session = True
    
    async def close(self):
        """关闭session"""
        if self._own_session and self.session:
            await self.session.close()
            self.session = None
            self._own_session = False

    async def get_item_list_info(self, page_number=1, page_size=20, retry_count=0, 
                                  update_config_cookies_callback=None, myid=None):
        """获取商品列表信息，自动处理token失效的情况

        Args:
            page_number (int): 页码，从1开始
            page_size (int): 每页数量，默认20
            retry_count (int): 重试次数，内部使用
            update_config_cookies_callback: 更新Cookie的回调函数
            myid: 用户ID

        Returns:
            dict: 包含商品列表的字典
        """
        from common.utils.xianyu_utils import trans_cookies, generate_sign
        
        if retry_count >= 4:
            logger.error("获取商品信息失败，重试次数过多")
            return {"success": False, "error": "获取商品信息失败，重试次数过多"}

        # 确保session已创建
        await self._ensure_session()

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.idle.web.xyh.item.list',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            'spm_pre': 'a21ybx.collection.menu.1.272b5141NafCNK'
        }

        data = {
            'needGroupInfo': False,
            'pageNumber': page_number,
            'pageSize': page_size,
            'groupName': '在售',
            'groupId': '58877261',
            'defaultGroup': True,
            "userId": myid or self.cookie_id
        }

        # 从cookies中获取token
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

        # 生成签名
        data_val = json.dumps(data, separators=(',', ':'))
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            headers = {
                'Cookie': self.cookies_str,
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.goofish.com/',
                'Origin': 'https://www.goofish.com'
            }
            
            # 打印请求参数和请求头
            logger.info(f"【{self.cookie_id}】请求参数 params: {params}")
            logger.info(f"【{self.cookie_id}】请求数据 data: {data}")
            logger.info(f"【{self.cookie_id}】请求数据 data_val: {data_val}")
            logger.info(f"【{self.cookie_id}】请求头 headers: {dict(headers)}")
            
            async with self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.idle.web.xyh.item.list/1.0/',
                params=params,
                data={'data': data_val},
                headers=headers
            ) as response:
                res_json = await response.json()

                # 检查并更新Cookie
                if 'set-cookie' in response.headers:
                    new_cookies = {}
                    for cookie in response.headers.getall('set-cookie', []):
                        if '=' in cookie:
                            name, value = cookie.split(';')[0].split('=', 1)
                            new_cookies[name.strip()] = value.strip()

                    if new_cookies:
                        self.cookies.update(new_cookies)
                        self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                        if update_config_cookies_callback:
                            await update_config_cookies_callback()

                # 检查响应是否成功
                if res_json.get('ret') and res_json['ret'][0] == 'SUCCESS::调用成功':
                    items_data = res_json.get('data', {})
                    card_list = items_data.get('cardList', [])

                    # 解析cardList中的商品信息
                    items_list = []
                    for card in card_list:
                        card_data = card.get('cardData', {})
                        if card_data:
                            item_info = {
                                'id': card_data.get('id', ''),
                                'title': card_data.get('title', ''),
                                'price': card_data.get('priceInfo', {}).get('price', ''),
                                'price_text': card_data.get('priceInfo', {}).get('preText', '') + card_data.get('priceInfo', {}).get('price', ''),
                                'category_id': card_data.get('categoryId', ''),
                                'auction_type': card_data.get('auctionType', ''),
                                'item_status': card_data.get('itemStatus', 0),
                                'detail_url': card_data.get('detailUrl', ''),
                                'pic_info': card_data.get('picInfo', {}),
                                'detail_params': card_data.get('detailParams', {}),
                                'track_params': card_data.get('trackParams', {}),
                                'item_label_data': card_data.get('itemLabelDataVO', {}),
                                'card_type': card.get('cardType', 0)
                            }
                            items_list.append(item_info)

                    logger.info(f"成功获取到 {len(items_list)} 个商品")

                    return {
                        "success": True,
                        "page_number": page_number,
                        "page_size": page_size,
                        "current_count": len(items_list),
                        "items": items_list,
                        "raw_data": items_data
                    }
                else:
                    error_msg = res_json.get('ret', [''])[0] if res_json.get('ret') else ''
                    if 'FAIL_SYS_TOKEN_EXOIRED' in error_msg or 'token' in error_msg.lower():
                        logger.warning(f"Token失效，准备重试: {error_msg}")
                        await asyncio.sleep(0.5)
                        return await self.get_item_list_info(page_number, page_size, retry_count + 1, update_config_cookies_callback, myid)
                    else:
                        logger.error(f"获取商品信息失败: {res_json}")
                        return {"success": False, "error": f"获取商品信息失败: {error_msg}"}

        except Exception as e:
            logger.error(f"商品信息API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(0.5)
            return await self.get_item_list_info(page_number, page_size, retry_count + 1, update_config_cookies_callback, myid)

    async def get_all_items(self, page_size=20, max_pages=None, update_config_cookies_callback=None, myid=None):
        """获取所有商品信息（自动分页）

        Args:
            page_size (int): 每页数量，默认20
            max_pages (int): 最大页数限制，None表示无限制
            update_config_cookies_callback: 更新Cookie的回调函数
            myid: 用户ID

        Returns:
            dict: 包含所有商品信息的字典
        """
        all_items = []
        page_number = 1

        logger.info(f"开始获取所有商品信息，每页{page_size}条")

        while True:
            if max_pages and page_number > max_pages:
                logger.info(f"达到最大页数限制 {max_pages}，停止获取")
                break

            logger.info(f"正在获取第 {page_number} 页...")
            result = await self.get_item_list_info(page_number, page_size, 0, update_config_cookies_callback, myid)

            if not result.get("success"):
                logger.error(f"获取第 {page_number} 页失败: {result}")
                break

            current_items = result.get("items", [])
            if not current_items:
                logger.info(f"第 {page_number} 页没有数据，获取完成")
                break

            all_items.extend(current_items)

            logger.info(f"第 {page_number} 页获取到 {len(current_items)} 个商品")

            if len(current_items) < page_size:
                logger.info(f"第 {page_number} 页商品数量少于页面大小，获取完成")
                break

            page_number += 1
            await asyncio.sleep(1)

        logger.info(f"所有商品获取完成，共 {len(all_items)} 个商品")

        return {
            "success": True,
            "total_pages": page_number,
            "total_count": len(all_items),
            "items": all_items
        }
