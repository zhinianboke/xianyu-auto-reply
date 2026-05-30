"""
发货服务基类

功能:
1. 提供发货相关的公共方法和属性
2. 账号信息加载和管理
3. Cookie更新和管理
4. Token管理
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from common.utils.text_utils import safe_str
from common.models.xy_catalog_item import XYCatalogItem
from common.utils.cookie_refresh import clear_cookie_refresh_snapshot
from common.utils.xianyu_utils import trans_cookies, generate_sign


class BaseShippingService:
    """发货服务基类
    
    提供发货服务的通用功能:
    - 账号信息管理
    - Cookie管理
    - Token管理
    - 通用工具方法
    """

    def __init__(
        self,
        db_session: AsyncSession,
        http_session: aiohttp.ClientSession,
        account_pk: int,
    ):
        """
        初始化发货服务

        Args:
            db_session: 异步数据库会话
            http_session: aiohttp会话对象
            account_pk: 账号主键ID
        """
        self.db_session = db_session
        self.http_session = http_session
        self.account_pk = account_pk
        
        # 账号相关属性(延迟加载)
        self._account: Optional[XYAccount] = None
        self._cookies_str: Optional[str] = None
        self._cookies_dict: Optional[Dict[str, str]] = None
        
        # Token相关属性
        self.current_token: Optional[str] = None
        self.last_token_refresh_time: float = 0
        self.token_refresh_interval: int = 3600  # 1小时

    def _safe_str(self, obj: Any) -> str:
        """安全字符串转换（委托公共实现）

        Args:
            obj: 需要转换的对象

        Returns:
            字符串表示
        """
        return safe_str(obj)

    async def _load_account(self) -> bool:
        """加载账号信息
        
        Returns:
            是否加载成功
        """
        try:
            stmt = select(XYAccount).where(XYAccount.id == self.account_pk)
            result = await self.db_session.execute(stmt)
            self._account = result.scalars().first()
            
            if not self._account:
                logger.error(f"账号不存在: {self.account_pk}")
                return False
            
            self._cookies_str = self._account.cookie
            self._cookies_dict = trans_cookies(self._cookies_str) if self._cookies_str else {}
            
            logger.debug(f"【{self._account.account_id}】账号信息加载成功")
            return True
            
        except Exception as e:
            logger.error(f"加载账号信息失败: {self._safe_str(e)}")
            return False

    @property
    def account_id(self) -> str:
        """获取账号ID"""
        return self._account.account_id if self._account else str(self.account_pk)

    @property
    def cookies_str(self) -> str:
        """获取Cookie字符串"""
        return self._cookies_str or ""

    @property
    def cookies_dict(self) -> Dict[str, str]:
        """获取Cookie字典"""
        return self._cookies_dict or {}


    async def _get_real_item_id(self) -> Optional[str]:
        """从数据库中获取一个真实的商品ID
        
        Returns:
            商品ID或None
        """
        try:
            if not self._account:
                await self._load_account()
            
            if not self._account:
                return None
            
            # 获取该账号的商品列表
            stmt = select(XYCatalogItem).where(
                XYCatalogItem.account_pk == self.account_pk
            ).limit(1)
            result = await self.db_session.execute(stmt)
            item = result.scalars().first()
            
            if item:
                logger.debug(f"【{self.account_id}】获取到真实商品ID: {item.item_id}")
                return item.item_id
            
            # 如果该账号没有商品,尝试获取任意一个商品ID
            stmt = select(XYCatalogItem).limit(1)
            result = await self.db_session.execute(stmt)
            item = result.scalars().first()
            
            if item:
                logger.debug(f"【{self.account_id}】使用其他账号的商品ID: {item.item_id}")
                return item.item_id
            
            logger.warning(f"【{self.account_id}】数据库中没有找到任何商品ID")
            return None
            
        except Exception as e:
            logger.error(f"【{self.account_id}】获取真实商品ID失败: {self._safe_str(e)}")
            return None

    async def _update_account_cookies(self, new_cookies_str: str) -> bool:
        """更新数据库中的Cookie
        
        Args:
            new_cookies_str: 新的Cookie字符串
            
        Returns:
            是否更新成功
        """
        try:
            stmt = select(XYAccount).where(XYAccount.id == self.account_pk)
            result = await self.db_session.execute(stmt)
            account = result.scalars().first()
            if not account:
                logger.warning(f"【{self.account_id}】未找到账号记录，无法更新数据库Cookie")
                return False

            account.cookie = new_cookies_str
            account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
            self.db_session.add(account)
            await self.db_session.commit()
            
            # 更新本地缓存
            self._cookies_str = new_cookies_str
            self._cookies_dict = trans_cookies(new_cookies_str)
            
            logger.debug(f"【{self.account_id}】已更新数据库中的Cookie")
            return True
            
        except Exception as e:
            logger.error(f"【{self.account_id}】更新数据库Cookie失败: {self._safe_str(e)}")
            await self.db_session.rollback()
            return False

    def _get_token_from_cookies(self) -> str:
        """从Cookie中获取Token
        
        Returns:
            Token字符串
        """
        cookies = trans_cookies(self.cookies_str)
        m_h5_tk = cookies.get('_m_h5_tk', '')
        if m_h5_tk:
            return m_h5_tk.split('_')[0]
        return ''

    async def _handle_response_cookies(self, response: aiohttp.ClientResponse) -> None:
        """处理响应中的Cookie更新
        
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
                    # 合并新Cookie
                    merged_cookies = self.cookies_dict.copy()
                    merged_cookies.update(new_cookies)
                    
                    # 生成新的cookie字符串
                    new_cookies_str = '; '.join([f"{k}={v}" for k, v in merged_cookies.items()])
                    
                    # 更新数据库
                    await self._update_account_cookies(new_cookies_str)
                    logger.debug("已更新Cookie到数据库")
                    
        except Exception as e:
            logger.warning(f"处理响应Cookie失败: {self._safe_str(e)}")
