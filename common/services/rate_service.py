"""
闲鱼评价服务（公共模块）

功能：
1. 自动评价买家
2. 更新订单评价状态
3. 根据账号配置获取评价内容
4. 检查商品是否属于指定账号

说明：
此模块放在common目录下，供scheduler和websocket共同使用
"""
import json
import time
import asyncio
from typing import Optional, Dict, Any

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_sign


class RateService:
    """闲鱼评价服务
    
    支持令牌过期自动刷新Cookie并重试
    """
    
    def __init__(self, cookie_string: str, account_id: str = None):
        """初始化评价服务
        
        Args:
            cookie_string: 账号Cookie字符串
            account_id: 账号ID，用于令牌过期时更新数据库Cookie（可选）
        """
        self.cookie_string = cookie_string
        self.account_id = account_id
        self.cookies_dict = self._parse_cookies(cookie_string)
    
    def _parse_cookies(self, cookies_str: str) -> dict:
        """解析Cookie字符串为字典"""
        if not cookies_str:
            return {}
        cookies = {}
        for cookie in cookies_str.split("; "):
            if "=" in cookie:
                key, value = cookie.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies
    
    async def rate_buyer(self, trade_id: str, feedback: str = "不错的买家", is_retry: bool = False) -> Dict[str, Any]:
        """评价买家
        
        支持令牌过期自动刷新Cookie并重试一次
        
        Args:
            trade_id: 订单ID
            feedback: 评价内容，默认"不错的买家"
            is_retry: 是否为令牌过期后的重试请求
            
        Returns:
            评价结果字典，包含success和message
        """
        try:
            from common.utils.cookie_refresh import (
                is_token_expired_error, handle_token_expired_response,
                update_account_cookies_in_db,
                is_session_expired_error, trigger_password_login_async,
                mark_account_session_expired
            )
            
            m_h5_tk = self.cookies_dict.get('_m_h5_tk', '')
            token = m_h5_tk.split('_')[0] if m_h5_tk else ''
            timestamp = str(int(time.time() * 1000))
            
            # 构建请求数据
            data_obj = {
                "tradeId": trade_id,
                "rate": 1,  # 好评
                "feedback": feedback,
                "createOrAppend": 0
            }
            data_val = json.dumps(data_obj, separators=(',', ':'), ensure_ascii=False)
            sign = generate_sign(timestamp, token, data_val)
            
            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": timestamp,
                "sign": sign,
                "v": "4.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": "mtop.taobao.idle.rate.create",
                "sessionOption": "AutoLoginOnly"
            }
            
            headers = {
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "referer": "https://www.goofish.com/",
                "origin": "https://www.goofish.com",
                "cookie": self.cookie_string
            }
            
            url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.rate.create/4.0/"
            
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, params=params, headers=headers, data={"data": data_val}) as response:
                    result = await response.json()
                    
                    ret = result.get('ret', [])
                    ret_str = ret[0] if ret else str(result)
                    retry_tag = '[令牌过期重试] ' if is_retry else ''
                    
                    if 'SUCCESS' in ret_str:
                        logger.info(
                            f"账号 {self.account_id or '未知账号'} {retry_tag}评价成功: "
                            f"trade_id={trade_id}, feedback={feedback}, 接口返回: ret={ret}"
                        )
                        return {"success": True, "message": "评价成功"}
                    
                    # 检测令牌过期，尝试刷新Cookie并重试
                    if not is_retry and is_token_expired_error(ret):
                        logger.warning(
                            f"账号 {self.account_id or '未知账号'} 评价订单 {trade_id} 令牌过期，"
                            f"接口返回: ret={ret}，准备刷新Cookie后重试"
                        )
                        has_new, new_cookies_str = handle_token_expired_response(
                            response, self.cookie_string
                        )
                        if has_new:
                            if self.account_id:
                                await update_account_cookies_in_db(self.account_id, new_cookies_str)
                            # 更新本地Cookie并重试
                            self.cookie_string = new_cookies_str
                            self.cookies_dict = self._parse_cookies(new_cookies_str)
                            return await self.rate_buyer(trade_id, feedback, is_retry=True)
                        else:
                            logger.warning(f"账号 {self.account_id or '未知账号'} 评价订单 {trade_id} 令牌过期，但响应中没有Set-Cookie，无法重试")
                    
                    # 检测Session过期，标记账号冷却并触发后台异步密码登录（不阻塞、不重试）
                    if is_session_expired_error(ret):
                        logger.warning(
                            f"账号 {self.account_id or '未知账号'} 评价订单 {trade_id} Session过期，"
                            f"接口返回: ret={ret}，触发后台异步密码登录"
                        )
                        if self.account_id:
                            mark_account_session_expired(self.account_id)
                            trigger_password_login_async(self.account_id)
                    
                    logger.warning(
                        f"账号 {self.account_id or '未知账号'} {retry_tag}评价失败: "
                        f"trade_id={trade_id}, 接口返回: ret={ret}, response={result}"
                    )
                    return {"success": False, "message": ret_str}
                        
        except Exception as e:
            logger.error(f"账号 {self.account_id or '未知账号'} 评价异常: trade_id={trade_id}, error={e}")
            return {"success": False, "message": str(e)}


async def fetch_merchant_rate_list(cookie_string: str, account_id: str = None, page: int = 1, page_size: int = 20, max_retries: int = 3) -> Dict[str, Any]:
    """获取商家待评价订单列表
    
    调用 mtop.taobao.idle.merchant.rate.list 接口获取待评价订单
    
    Args:
        cookie_string: 账号Cookie字符串
        account_id: 账号ID（用于日志和令牌刷新）
        page: 页码，默认1
        page_size: 每页数量，默认20
        max_retries: 最大重试次数，默认3
        
    Returns:
        {
            'success': bool,
            'items': list,  # 待评价订单列表
            'total_count': int,
            'message': str,
            'cookies_str': str  # 可能刷新后的cookie
        }
    """
    from common.utils.cookie_refresh import (
        is_token_expired_error, handle_token_expired_response,
        update_account_cookies_in_db,
        is_session_expired_error, trigger_password_login_async,
        mark_account_session_expired
    )
    
    current_cookie = cookie_string
    
    for attempt in range(max_retries):
        try:
            cookies_dict = {}
            for cookie in current_cookie.split("; "):
                if "=" in cookie:
                    key, value = cookie.split("=", 1)
                    cookies_dict[key.strip()] = value.strip()
            
            m_h5_tk = cookies_dict.get('_m_h5_tk', '')
            token = m_h5_tk.split('_')[0] if m_h5_tk else ''
            timestamp = str(int(time.time() * 1000))
            
            # 构建请求数据
            data_obj = {
                "pageNumber": page,
                "rowsPerPage": page_size,
                "queryType": "ORDER",
                "rateSearchParam": {
                    "sellerRateStatus": "5"  # 待评价
                }
            }
            data_val = json.dumps(data_obj, separators=(',', ':'), ensure_ascii=False)
            
            # 生成签名
            app_key = "34839810"
            sign = generate_sign(timestamp, token, data_val)
            
            params = {
                "jsv": "2.7.2",
                "appKey": app_key,
                "t": timestamp,
                "sign": sign,
                "v": "1.0",
                "type": "json",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": "mtop.taobao.idle.merchant.rate.list",
                "valueType": "string",
                "sessionOption": "AutoLoginOnly",
            }
            
            headers = {
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "referer": "https://seller.goofish.com/?site=COMMONPRO",
                "origin": "https://seller.goofish.com",
                "cookie": current_cookie,
            }
            
            url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.merchant.rate.list/1.0/"
            
            timeout_cfg = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.post(url, params=params, headers=headers, data={"data": data_val}) as response:
                    result = await response.json()
                    
                    ret = result.get('ret', [])
                    ret_str = ret[0] if ret else str(result)
                    
                    if 'SUCCESS' in ret_str:
                        module = result.get('data', {}).get('module', {})
                        items = module.get('items', [])
                        total_count = int(module.get('totalCount', '0'))
                        logger.info(
                            f"账号 {account_id or '未知'} 获取待评价列表成功: "
                            f"共 {total_count} 条，本页 {len(items)} 条"
                        )
                        return {
                            'success': True,
                            'items': items,
                            'total_count': total_count,
                            'message': '获取成功',
                            'cookies_str': current_cookie,
                        }
                    
                    # 检测令牌过期
                    if is_token_expired_error(ret):
                        logger.warning(
                            f"账号 {account_id or '未知'} 获取待评价列表令牌过期 (尝试 {attempt+1}/{max_retries})"
                        )
                        has_new, new_cookies_str = handle_token_expired_response(
                            response, current_cookie
                        )
                        if has_new:
                            current_cookie = new_cookies_str
                            if account_id:
                                await update_account_cookies_in_db(account_id, new_cookies_str)
                            continue  # 重试
                        else:
                            if attempt < max_retries - 1:
                                continue
                            return {
                                'success': False,
                                'items': [],
                                'total_count': 0,
                                'message': f'令牌过期且无法刷新: {ret_str}',
                                'cookies_str': current_cookie,
                            }
                    
                    # 检测Session过期
                    if is_session_expired_error(ret):
                        logger.warning(
                            f"账号 {account_id or '未知'} 获取待评价列表Session过期"
                        )
                        if account_id:
                            mark_account_session_expired(account_id)
                            trigger_password_login_async(account_id)
                        return {
                            'success': False,
                            'items': [],
                            'total_count': 0,
                            'message': f'Session过期: {ret_str}',
                            'cookies_str': current_cookie,
                        }
                    
                    # 其他错误，重试
                    logger.warning(
                        f"账号 {account_id or '未知'} 获取待评价列表失败 "
                        f"(尝试 {attempt+1}/{max_retries}): {ret_str}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    
                    return {
                        'success': False,
                        'items': [],
                        'total_count': 0,
                        'message': ret_str,
                        'cookies_str': current_cookie,
                    }
                    
        except Exception as e:
            logger.error(
                f"账号 {account_id or '未知'} 获取待评价列表异常 "
                f"(尝试 {attempt+1}/{max_retries}): {e}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            return {
                'success': False,
                'items': [],
                'total_count': 0,
                'message': str(e),
                'cookies_str': current_cookie,
            }
    
    return {
        'success': False,
        'items': [],
        'total_count': 0,
        'message': '重试次数已用尽',
        'cookies_str': current_cookie,
    }


async def get_rate_feedback_content(account_id: str) -> Optional[str]:
    """根据账号配置获取评价内容
    
    Args:
        account_id: 账号ID
        
    Returns:
        评价内容，如果未启用或获取失败返回None
    """
    try:
        from common.db.session import async_session_maker
        from common.models.auto_rate_config import AutoRateConfig
        from sqlalchemy import select
        
        async with async_session_maker() as session:
            stmt = select(AutoRateConfig).where(AutoRateConfig.account_id == account_id)
            result = await session.execute(stmt)
            config = result.scalars().first()
            
            if not config or not config.enabled:
                logger.info(f"账号 {account_id} 未启用自动评价")
                return None
            
            if config.rate_type == "text":
                # 固定文字
                content = config.text_content or "不错的买家"
                logger.info(f"账号 {account_id} 使用固定评价内容: {content}")
                return content
            elif config.rate_type == "api":
                # API获取
                if not config.api_url:
                    logger.warning(f"账号 {account_id} 未配置API地址")
                    return None
                
                logger.info(f"账号 {account_id} 从API获取评价内容: {config.api_url}")
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as http_session:
                    async with http_session.get(config.api_url) as response:
                        if response.status == 200:
                            content = await response.text()
                            content = content.strip()
                            if content:
                                logger.info(f"账号 {account_id} API返回评价内容: {content[:50]}...")
                                return content
                            else:
                                logger.warning(f"账号 {account_id} API返回内容为空")
                                return None
                        else:
                            logger.warning(f"账号 {account_id} API请求失败: status={response.status}")
                            return None
            else:
                logger.warning(f"账号 {account_id} 未知的评价类型: {config.rate_type}")
                return None
                
    except Exception as e:
        logger.error(f"获取评价内容失败: account_id={account_id}, error={e}")
        return None


async def update_order_rated_status(order_no: str, is_rated: bool = True) -> bool:
    """更新订单评价状态
    
    Args:
        order_no: 订单号
        is_rated: 是否已评价
        
    Returns:
        是否更新成功
    """
    try:
        from common.db.session import async_session_maker
        from common.models.xy_order import XYOrder
        from sqlalchemy import update
        
        async with async_session_maker() as session:
            stmt = update(XYOrder).where(XYOrder.order_no == order_no).values(is_rated=is_rated)
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount > 0:
                logger.info(f"订单 {order_no} 评价状态已更新为: {is_rated}")
                return True
            else:
                logger.warning(f"订单 {order_no} 不存在，无法更新评价状态")
                return False
                
    except Exception as e:
        logger.error(f"更新订单评价状态失败: order_no={order_no}, error={e}")
        return False


async def check_item_belongs_to_account(account_id: str, item_id: str) -> bool:
    """检查商品是否属于指定账号
    
    通过查询xy_catalog_items表，判断商品是否属于当前账号
    
    Args:
        account_id: 账号ID（cookie_id）
        item_id: 商品ID
        
    Returns:
        True表示商品属于该账号，False表示不属于
    """
    if not account_id or not item_id:
        logger.warning(f"检查商品归属失败: account_id={account_id}, item_id={item_id} 参数为空")
        return False
    
    try:
        from common.db.session import async_session_maker
        from common.models.xy_catalog_item import XYCatalogItem
        from common.models.xy_account import XYAccount
        from sqlalchemy import select
        
        async with async_session_maker() as session:
            # 先查询账号的主键ID
            account_stmt = select(XYAccount.id).where(XYAccount.account_id == account_id)
            account_result = await session.execute(account_stmt)
            account_pk = account_result.scalar_one_or_none()
            
            if not account_pk:
                logger.warning(f"检查商品归属: 账号 {account_id} 不存在")
                return False
            
            # 查询商品是否属于该账号
            item_stmt = select(XYCatalogItem).where(
                XYCatalogItem.account_pk == account_pk,
                XYCatalogItem.item_id == item_id
            )
            item_result = await session.execute(item_stmt)
            item = item_result.scalars().first()
            
            if item:
                logger.debug(f"商品 {item_id} 属于账号 {account_id}")
                return True
            else:
                logger.info(f"商品 {item_id} 不属于账号 {account_id}，跳过评价")
                return False
                
    except Exception as e:
        logger.error(f"检查商品归属失败: account_id={account_id}, item_id={item_id}, error={e}")
        return False
