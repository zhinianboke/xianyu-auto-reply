"""
闲鱼评价服务

功能：
1. 自动评价买家
2. 更新订单评价状态
3. 根据账号配置获取评价内容
4. 检查商品是否属于指定账号
"""
import asyncio
import json
import time
from typing import Optional, Dict, Any

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_sign


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


class RateService:
    """闲鱼评价服务"""
    
    def __init__(self, cookie_string: str, account_id: str = None):
        """初始化评价服务
        
        Args:
            cookie_string: 账号Cookie字符串
            account_id: 账号ID，用于日志记录（可选）
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
    
    async def rate_buyer(self, trade_id: str, feedback: str = "不错的买家", retry_count: int = 0) -> Dict[str, Any]:
        """评价买家
        
        支持令牌过期时存储set-cookie并重试（参照发货服务模式）
        
        Args:
            trade_id: 订单ID
            feedback: 评价内容，默认"不错的买家"
            retry_count: 当前重试次数
            
        Returns:
            评价结果字典，包含success和message
        """
        max_retry = 3
        log_prefix = f"【{self.account_id}】" if self.account_id else ""
        
        try:
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
                    
                    # 处理响应中的set-cookie，更新本地cookie并写入数据库
                    await self._handle_response_cookies(response)
                    
                    ret = result.get('ret', [])
                    ret_str = ret[0] if ret else str(result)
                    
                    if 'SUCCESS' in ret_str:
                        logger.info(f"{log_prefix}评价成功: trade_id={trade_id}, feedback={feedback}")
                        return {"success": True, "message": "评价成功"}
                    else:
                        logger.warning(f"{log_prefix}评价失败: trade_id={trade_id}, ret={ret_str}")
                        
                        # 令牌过期时，用更新后的cookie重试
                        if any('TOKEN_EXOIRED' in r or 'TOKEN_EXPIRED' in r for r in ret):
                            if retry_count < max_retry - 1:
                                logger.info(f"{log_prefix}评价令牌过期，已更新Cookie，准备重试({retry_count + 1}/{max_retry - 1})...")
                                await asyncio.sleep(0.5)
                                return await self.rate_buyer(trade_id, feedback, retry_count + 1)
                        
                        return {"success": False, "message": ret_str}
                        
        except Exception as e:
            logger.error(f"{log_prefix}评价异常: trade_id={trade_id}, error={e}")
            return {"success": False, "message": str(e)}
    
    async def _handle_response_cookies(self, response) -> None:
        """处理响应中的set-cookie，更新本地cookie并写入数据库
        
        令牌过期时服务端会在响应头中返回新的cookie（包含新的_m_h5_tk），
        存储后重试请求即可使用新的token签名
        
        Args:
            response: HTTP响应对象
        """
        try:
            if 'set-cookie' in response.headers:
                new_cookies = {}
                for cookie in response.headers.getall('set-cookie', []):
                    if '=' in cookie:
                        name, value = cookie.split(';')[0].split('=', 1)
                        new_cookies[name.strip()] = value.strip()
                
                if new_cookies:
                    self.cookies_dict.update(new_cookies)
                    self.cookie_string = '; '.join([f"{k}={v}" for k, v in self.cookies_dict.items()])
                    log_prefix = f"【{self.account_id}】" if self.account_id else ""
                    logger.info(f"{log_prefix}已从响应中更新Cookie（含{len(new_cookies)}个字段）")
                    # 写入数据库
                    if self.account_id:
                        try:
                            from common.utils.cookie_refresh import update_account_cookies_in_db
                            await update_account_cookies_in_db(self.account_id, self.cookie_string)
                            logger.info(f"{log_prefix}已将刷新后的Cookie写入数据库")
                        except Exception as db_e:
                            logger.warning(f"{log_prefix}写入数据库失败: {db_e}")
        except Exception as e:
            logger.warning(f"处理响应Cookie失败: {e}")


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
